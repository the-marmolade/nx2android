# axml.py: the binary XML (AXML) and resources.arsc that mkapk.py writes, and their reading back (decode), shared by mkapk.py (a new port) and apkdriver.py
# (an installed port's APK changed in place: --game-modes). Standard library only.
import struct

ANDROID_NS = 'http://schemas.android.com/apk/res/android'

# ---------------- binary XML ----------------
ATTR_IDS = {  # android: attribute resource IDs (frameworks/base/core/res/res/values/public.xml)
    'label': 0x01010001, 'icon': 0x01010002, 'name': 0x01010003, 'hasCode': 0x0101000c, 'debuggable': 0x0101000f, 'exported': 0x01010010,
    'configChanges': 0x0101001f, 'screenOrientation': 0x0101001e, 'value': 0x01010024, 'minSdkVersion': 0x0101020c, 'versionCode': 0x0101021b,
    'versionName': 0x0101021c, 'targetSdkVersion': 0x01010270, 'maxSdkVersion': 0x01010271, 'isGame': 0x010103f4, 'extractNativeLibs': 0x010104ea, 'appCategory': 0x01010545,
    'requestLegacyExternalStorage': 0x01010603, 'enableOnBackInvokedCallback': 0x0101066c, 'drawable': 0x01010199,   # (maxSdkVersion and requestLegacyExternalStorage read from android-36's android.jar, R$attr)
    'resource': 0x01010025, 'supportsBatteryGameMode': 0x01010656, 'supportsPerformanceGameMode': 0x01010657, 'allowGameDownscaling': 0x01010659, 'allowGameFpsOverride': 0x0101065a}   # (android-36's R$attr)
T_REF, T_STRING, T_INT_DEC, T_INT_HEX, T_BOOL = 0x01, 0x03, 0x10, 0x11, 0x12

def axml(root):
    # string pool: attribute names that carry resource IDs come first, in resource-map order
    res_names = sorted({n for _, n, _ in walk_attrs(root) if n in ATTR_IDS}, key=lambda n: ATTR_IDS[n])
    strings = list(res_names)
    def s(x):
        if x not in strings: strings.append(x)
        return strings.index(x)
    s('android'); s(ANDROID_NS)
    body = []
    def chunk(t, hsize, payload): return struct.pack('<HHI', t, hsize, 8 + len(payload)) + payload
    def node(n, line=[1]):
        tag, attrs, kids = n
        enc = []
        for is_ns, name, v in attrs:
            ns = s(ANDROID_NS) if is_ns else 0xffffffff
            if isinstance(v, bool): raw, dt, data = 0xffffffff, T_BOOL, 0xffffffff if v else 0
            elif isinstance(v, int): raw, dt, data = 0xffffffff, T_INT_DEC, v
            elif isinstance(v, tuple): raw, dt, data = 0xffffffff, T_REF if v[0] == 'ref' else T_INT_HEX, v[1]
            else: raw, dt, data = s(v), T_STRING, s(v)
            enc.append((ATTR_IDS.get(name, 0xffffffff) if is_ns else 0xffffffff, struct.pack('<IIIHBBI', ns, s(name), raw, 8, 0, dt, data)))
        enc.sort(key=lambda a: a[0])   # resource-ID attributes ascending, plain ones (package) last
        a = b''.join(e for _, e in enc)
        body.append(chunk(0x0102, 16, struct.pack('<II', line[0], 0xffffffff) + struct.pack('<IIHHHHHH', 0xffffffff, s(tag), 20, 20, len(attrs), 0, 0, 0) + a))
        line[0] += 1
        for k in kids: node(k)
        body.append(chunk(0x0103, 16, struct.pack('<IIII', line[0], 0xffffffff, 0xffffffff, s(tag)))); line[0] += 1
    ns = struct.pack('<IIII', 1, 0xffffffff, s('android'), s(ANDROID_NS))
    node(root)
    nodes = chunk(0x0100, 16, ns) + b''.join(body) + chunk(0x0101, 16, ns)
    # UTF-16 string pool
    offs, data = [], b''
    for x in strings:
        offs.append(len(data)); u = x.encode('utf-16-le'); data += struct.pack('<H', len(x)) + u + b'\0\0'
    data += b'\0' * (-len(data) % 4)
    hdr = struct.pack('<IIIII', len(strings), 0, 0, 28 + 4 * len(strings), 0)
    pool = chunk(0x0001, 28, hdr + b''.join(struct.pack('<I', o) for o in offs) + data)
    rmap = chunk(0x0180, 8, b''.join(struct.pack('<I', ATTR_IDS[n]) for n in res_names))
    return chunk(0x0003, 8, pool + rmap + nodes)

def decode(data):
    """A binary XML axml() wrote, back as its tree (tag, [(ns_android?, name, value)], children): the values as axml() takes them (bool, int, str, ('ref', id),
    ('hex', n)). For a file not of axml()'s kind: ValueError"""
    t, hs, size = struct.unpack_from('<HHI', data, 0)
    if t != 0x0003 or hs != 8: raise ValueError('not a binary XML file')
    pt, phs, psize = struct.unpack_from('<HHI', data, 8)
    if pt != 0x0001 or phs != 28: raise ValueError('no UTF-16 string pool first')
    n, _, flags, start, _ = struct.unpack_from('<IIIII', data, 16)
    if flags & 0x100: raise ValueError('a UTF-8 string pool (not written by axml)')
    strings = []
    for i in range(n):
        o = 8 + start + struct.unpack_from('<I', data, 36 + 4 * i)[0]; ln = struct.unpack_from('<H', data, o)[0]
        strings.append(data[o + 2:o + 2 + 2 * ln].decode('utf-16-le'))
    o, stack, root = 8 + psize, [], None
    while o + 8 <= len(data):
        t, hs, csize = struct.unpack_from('<HHI', data, o)
        if t == 0x0102:
            name, _, _, count = struct.unpack_from('<IHHH', data, o + 20)
            attrs = []
            for k in range(count):
                ns, an, raw, _, _, dt, v = struct.unpack_from('<IIIHBBI', data, o + 36 + 20 * k)
                val = (v != 0 if dt == T_BOOL else v if dt == T_INT_DEC else ('hex', v) if dt == T_INT_HEX else ('ref', v) if dt == T_REF
                       else strings[raw] if dt == T_STRING else None)
                if val is None: raise ValueError(f'attribute {strings[an]}: value type {dt:#x} axml() does not write')
                attrs.append((ns != 0xffffffff, strings[an], val))
            node = (strings[name], attrs, [])
            if stack: stack[-1][2].append(node)
            else: root = node
            stack.append(node)
        elif t == 0x0103: stack.pop()
        if csize < 8: break
        o += csize
    if root is None or stack: raise ValueError('no element, or one not closed')
    return root

# Android's game modes (Android 12+; GameManager): without android.game_mode_config, Android 13 lists a game with Standard only (`cmd game mode battery` answers "not
# supported"), so the AYN Thor's game assistant and the game dashboard cannot set Battery or Performance for it. The port follows the mode itself (front_android.c
# gm_watch), so Android's own downscaling and frame-rate interventions stay off
GAME_MODE_CONFIG = ('game-mode-config', [(True, 'supportsBatteryGameMode', True), (True, 'supportsPerformanceGameMode', True), (True, 'allowGameDownscaling', False),
                                         (True, 'allowGameFpsOverride', False)], [])
GAME_MODE_XML = 'res/xml/game_mode_config.xml'
def game_mode_meta(ref):   # the <application>'s meta-data naming the config (ref: xml/game_mode_config's resource ID, game_mode_id)
    return ('meta-data', [(True, 'name', 'android.game_mode_config'), (True, 'resource', ('ref', ref))], [])
def game_mode_id(drawables): return 0x7f020000 if drawables else 0x7f010000   # the xml type follows the drawables' (type 1) when there are any
def has_game_modes(tree): return any(k[0] == 'meta-data' and ('name' , 'android.game_mode_config') in [(n, v) for _, n, v in k[1]] for app in tree[2] if app[0] == 'application' for k in app[2])
def manifest_with_game_modes(data, ref):
    """A binary AndroidManifest.xml (axml()'s) with the game mode meta-data in its <application>, written again whole; unchanged when it has it"""
    tree = decode(data)
    if has_game_modes(tree): return data
    apps = [k for k in tree[2] if k[0] == 'application']
    if len(apps) != 1: raise ValueError('no single <application> element')
    apps[0][2].append(game_mode_meta(ref))
    out = axml(tree)
    if decode(out) != tree: raise ValueError('the manifest does not read back as written')
    return out

def icon_drawables(adaptive):   # mkapk.py --icon (with --icon-fg / --icon-bg: adaptive): the drawables and their files, as res_table takes them
    icon = [(NODPI, 'res/drawable-nodpi-v4/icon.png')] + ([(ANYDPI_V26, 'res/drawable-anydpi-v26/icon.xml')] if adaptive else [])
    return [('icon', icon)] + ([('icon_fg', [(NODPI, 'res/drawable-nodpi-v4/icon_fg.png')]), ('icon_bg', [(NODPI, 'res/drawable-nodpi-v4/icon_bg.png')])] if adaptive else [])

# ---------------- resources.arsc: the icon's drawables, the game mode config ----------------
def rchunk(t, hsize, header, body=b''): return struct.pack('<HHI', t, hsize, hsize + len(body)) + header + body
def string_pool(strings):   # UTF-16 string pool chunk
    offs, data = [], b''
    for x in strings:
        offs.append(len(data)); data += struct.pack('<H', len(x)) + x.encode('utf-16-le') + b'\0\0'
    data += b'\0' * (-len(data) % 4)
    return rchunk(0x0001, 28, struct.pack('<IIIII', len(strings), 0, 0, 28 + 4 * len(strings), 0), b''.join(struct.pack('<I', o) for o in offs) + data)
NODPI = struct.pack('<I', 64) + b'\0' * 10 + struct.pack('<H', 0xffff) + b'\0' * 48                                       # ResTable_config: density nodpi, the rest any
ANYDPI_V26 = struct.pack('<I', 64) + b'\0' * 10 + struct.pack('<H', 0xfffe) + b'\0' * 8 + struct.pack('<HH', 26, 0) + b'\0' * 36   # density anydpi, sdkVersion 26
ANY = struct.pack('<I', 64) + b'\0' * 60   # ResTable_config: any
def res_table(pkg_name, types):   # [(type name, [(name, [(config, path)])])]: type t's entry i is resource 0x7f000000 | (t + 1) << 16 | i, a file per config
    paths = [p for _, ents in types for _, files in ents for _, p in files]
    names = [n for _, ents in types for n, _ in ents]   # (the key pool: every type's names, in order)
    tpool, keys = string_pool([t for t, _ in types]), string_pool(names)
    body, key0 = b'', 0
    for tid, (_, ents) in enumerate(types, 1):
        # an entry with files for more than one config varies by density and SDK version (ResTable_config CONFIG_DENSITY | CONFIG_VERSION)
        body += rchunk(0x0202, 16, struct.pack('<BBHI', tid, 0, 0, len(ents)), b''.join(struct.pack('<I', 0x0500 if len(f) > 1 else 0) for _, f in ents))
        for config in dict.fromkeys(c for _, files in ents for c, _ in files):
            offs, entries = [], b''
            for i, (_, files) in enumerate(ents):
                path = dict(files).get(config)
                if path is None: offs.append(0xffffffff); continue   # NO_ENTRY: no file for this config
                offs.append(len(entries)); entries += struct.pack('<HHI', 8, 0, key0 + i) + struct.pack('<HBBI', 8, 0, T_STRING, paths.index(path))   # its key -> the file's path
            body += rchunk(0x0201, 20 + 64, struct.pack('<BBHII', tid, 0, 0, len(ents), 20 + 64 + 4 * len(ents)) + config, b''.join(struct.pack('<I', o) for o in offs) + entries)
        key0 += len(ents)
    name = pkg_name.encode('utf-16-le')[:254].ljust(256, b'\0')
    pkg = rchunk(0x0200, 288, struct.pack('<I', 0x7f) + name + struct.pack('<IIIII', 288, len(types), 288 + len(tpool), len(names), 0), tpool + keys + body)
    return rchunk(0x0002, 12, struct.pack('<I', 1), string_pool(paths) + pkg)
def app_res_table(pkg_name, drawables):   # a port's resources.arsc: its icon's drawables (none without an icon), then xml/game_mode_config
    return res_table(pkg_name, ([('drawable', drawables)] if drawables else []) + [('xml', [('game_mode_config', [(ANY, GAME_MODE_XML)])])])

def walk_attrs(n):
    for a in n[1]: yield a
    for k in n[2]: yield from walk_attrs(k)
