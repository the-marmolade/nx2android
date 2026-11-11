#!/usr/bin/env python3
# apkdriver.py: an installed port's APK again with another Vulkan driver library (DM_VK_DRIVER, gfx_vk_core.c vk_init), or with none (the device's own driver), and/or with its
# host library built again (--host: porter host), without the game's files: every other entry is kept as it is, the ZIP is written and signed again by apksign.py with the
# player's key (the same signer, so it installs over the app and keeps its saves). --asset NAME=FILE puts FILE in as assets/NAME, replacing an entry of that name (porter host: the
# overlay's font, which an APK ported before it came lacks).
# The driver is loaded through libadrenotools and its hook libraries, which only an APK ported with a driver carries (porter port --vulkan-driver): one without them is refused.
# Usage: apkdriver.py <in.apk> <out.apk> <key.json> [--driver <lib.so> | --system] [--host <libdmhost.so>] [--asset NAME=FILE ...]   → prints the driver library's name in the APK ('' with --system)
#        apkdriver.py <in.apk> <out.apk> <key.json> --set-drivers [--set-driver LIB=FILE ...] [--loader FILE ...]   → the driver set replaced, in order (porter drivers: the
#        GUI's Drivers window); --loader adds libadrenotools and its hooks to an APK ported without them
#        apkdriver.py <in.apk> <out.apk> <key.json> --external-dex <classes.dex> | --native-activity   → the external-display activity put in or taken out (porter tv)
import argparse, json, os, sys, zipfile

from apksign import build_zip, sign_v2

ABI = 'lib/arm64-v8a/'
OWN = {'libdmhost.so', 'libadrenotools.so', 'libhook_impl.so', 'libmain_hook.so', 'libfile_redirect_hook.so', 'libgsl_alloc_hook.so'}   # nx2android's own libraries; any other is the driver
NEEDS = {'libadrenotools.so', 'libhook_impl.so', 'libmain_hook.so', 'libfile_redirect_hook.so', 'libgsl_alloc_hook.so'}   # what loads a driver (porter/pipeline.py ADRENOTOOLS_LIBS)


def lib_name(path):   # the package manager extracts only lib*.so from lib/<abi>/ (porter/pipeline.py driver_lib_name)
    n = os.path.basename(path)
    return n if n.startswith('lib') else 'lib' + n


KEEP = object()   # rebuild(driver=KEEP): the driver library the APK has stays

NATIVE, EXTERNAL = 'android.app.NativeActivity', 'org.nx2a.ExternalActivity'   # the port's activity: Android's own, or the one that moves the game to an external display


def manifest_activity(data):   # the activity class a binary AndroidManifest.xml written by mkapk.py names (its string pool has one of the two)
    strings, _, _ = _pool(data)
    return next((a for a in (EXTERNAL, NATIVE) if a in strings), None)


def _pool(data):   # mkapk.py axml(): the file chunk (0x0003), then the UTF-16 string pool (0x0001): (strings, the pool's end, the pool's flags)
    import struct
    t, hs, _ = struct.unpack_from('<HHI', data, 0); pt, phs, psize = struct.unpack_from('<HHI', data, 8)
    if t != 0x0003 or hs != 8 or pt != 0x0001 or phs != 28: raise SystemExit('AndroidManifest.xml: not a binary manifest as mkapk.py writes it')
    n, _, flags, start, _ = struct.unpack_from('<IIIII', data, 16)
    if flags & 0x100: raise SystemExit('AndroidManifest.xml: a UTF-8 string pool (not an APK made by mkapk.py)')
    out = []
    for i in range(n):
        o = 8 + start + struct.unpack_from('<I', data, 36 + 4 * i)[0]; ln = struct.unpack_from('<H', data, o)[0]
        out.append(data[o + 2:o + 2 + 2 * ln].decode('utf-16-le'))
    return out, 8 + psize, flags


def manifest_with_activity(data, activity):
    """A binary AndroidManifest.xml (mkapk.py's) naming activity (NATIVE or EXTERNAL) and with application hasCode to match: the string pool is written again with the
    class name replaced (the nodes name strings by index, so they stay), and the hasCode attribute's value set in place"""
    import struct
    strings, end, _ = _pool(data)
    cur = next((a for a in (EXTERNAL, NATIVE) if a in strings), None)
    if cur is None or 'hasCode' not in strings: raise SystemExit('AndroidManifest.xml: no activity of nx2android\'s and hasCode attribute in it')
    strings = [activity if s == cur else s for s in strings]
    offs, body = [], b''
    for s in strings:
        offs.append(len(body)); body += struct.pack('<H', len(s)) + s.encode('utf-16-le') + b'\0\0'
    body += b'\0' * (-len(body) % 4)
    pool = struct.pack('<IIIII', len(strings), 0, 0, 28 + 4 * len(strings), 0) + b''.join(struct.pack('<I', o) for o in offs) + body
    pool = struct.pack('<HHI', 0x0001, 28, 8 + len(pool)) + pool
    rest = bytearray(data[end:]); o, name, done = 0, strings.index('hasCode'), False
    while o + 8 <= len(rest):   # the chunks after the pool: the resource map, the namespace, the elements
        t, hs, size = struct.unpack_from('<HHI', rest, o)
        if t == 0x0102:   # a start element: 16 bytes of header, 20 of element, then 20 per attribute (ns, name, raw, size, 0, type, data)
            count = struct.unpack_from('<H', rest, o + 28)[0]
            for k in range(count):
                a = o + 36 + 20 * k
                if struct.unpack_from('<I', rest, a + 4)[0] == name and rest[a + 15] == 0x12: struct.pack_into('<I', rest, a + 16, 0xffffffff if activity != NATIVE else 0); done = True
        if size < 8: break
        o += size
    if not done: raise SystemExit('AndroidManifest.xml: no hasCode attribute to set')
    return struct.pack('<HHI', 0x0003, 8, 8 + len(pool) + len(rest)) + pool + bytes(rest)


def with_activity(entries, dex):
    """entries with the external-display activity (dex: its classes.dex, a path) or, with dex None, Android's NativeActivity again: the manifest names it and classes.dex
    comes or goes. → (entries, the activity's class)"""
    activity = EXTERNAL if dex else NATIVE; out = []
    for name, data, align in entries:
        if name == 'classes.dex': continue
        out.append((name, manifest_with_activity(data, activity) if name == 'AndroidManifest.xml' else data, align))
    if dex: out.append(('classes.dex', open(dex, 'rb').read(), 4))
    return out, activity


def with_game_modes(entries):
    """entries with Android's Battery and Performance game modes declared (axml.py GAME_MODE_CONFIG: the manifest's meta-data, resources.arsc's xml/game_mode_config
    and its file), for a port made before mkapk.py wrote them: (entries, whether it changed). Only for an APK whose resources.arsc is exactly the icon table
    mkapk.py writes (rebuilt here from the icon files the APK has): anything else is left as it is"""
    from axml import GAME_MODE_CONFIG, GAME_MODE_XML, app_res_table, axml, decode, game_mode_id, has_game_modes, icon_drawables, manifest_with_game_modes, res_table
    names = {n for n, _, _ in entries}; byname = {n: d for n, d, _ in entries}
    tree = decode(byname['AndroidManifest.xml'])
    if has_game_modes(tree): return entries, False
    pkg = next(v for ns, n, v in tree[1] if n == 'package')
    drawables = icon_drawables('res/drawable-nodpi-v4/icon_fg.png' in names) if 'res/drawable-nodpi-v4/icon.png' in names else []
    if drawables and byname.get('resources.arsc') != res_table(pkg, [('drawable', drawables)]): raise SystemExit('resources.arsc: not the icon table mkapk.py writes: game modes not added')
    if not drawables and 'resources.arsc' in names: raise SystemExit('resources.arsc without an icon: not an APK made by mkapk.py: game modes not added')
    man = manifest_with_game_modes(byname['AndroidManifest.xml'], game_mode_id(drawables)); arsc = app_res_table(pkg, drawables)
    out = [(n, man if n == 'AndroidManifest.xml' else arsc if n == 'resources.arsc' else d, a) for n, d, a in entries]
    if 'resources.arsc' not in names: out.append(('resources.arsc', arsc, 4))
    out.append((GAME_MODE_XML, axml(GAME_MODE_CONFIG), 4))
    return out, True


def rebuild_set(src, drivers, loader=(), host=None, assets=None):
    """src's entries with every driver library replaced by drivers ([(lib name, path)], in that order: the pause menu's Driver tab lists up to three) and loader
    (libadrenotools and its hooks, paths) added where src lacks them, so a port made without --vulkan-driver can take one: ([(name, data, align)], dropped names)"""
    entries, dropped, _ = rebuild(src, None, host, assets)
    have = {os.path.basename(e) for e, _, _ in entries if e.startswith(ABI)}
    at = next(n for n, (e, _, _) in enumerate(entries) if e == ABI + 'libdmhost.so') + 1
    for f in loader:
        if os.path.basename(f) not in NEEDS: raise SystemExit(f'{f}: not one of the driver loader\'s libraries ({", ".join(sorted(NEEDS))})')
        if os.path.basename(f) not in have: entries.insert(at, (ABI + os.path.basename(f), open(f, 'rb').read(), 16384)); have.add(os.path.basename(f))
    if drivers and not NEEDS <= have:
        raise SystemExit(f'{src} has no libadrenotools and no --loader was given: the driver could not be loaded')
    seen = set()
    for lib, path in drivers:
        if not lib.startswith('lib') or not lib.endswith('.so') or '/' in lib or '\\' in lib or lib in OWN or lib in seen: raise SystemExit(f'{lib}: not a usable driver library name')
        seen.add(lib); entries.insert(at, (ABI + lib, open(path, 'rb').read(), 16384)); at += 1
    return entries, [d for d in dropped if d not in seen]


def rebuild(src, driver=KEEP, host=None, assets=None):
    """src's entries with every driver library dropped and driver (a path, or None for the device's own) added, libdmhost.so replaced by host (a path) when given, and
    assets ({name: path}) put in as assets/<name>, an entry of that name replaced, the others added after the APK's own:
    ([(name, data, align)], dropped names, the driver library's name)"""
    z = zipfile.ZipFile(src)
    if any(i.compress_type != zipfile.ZIP_STORED for i in z.infolist()): raise SystemExit(f'{src}: not an APK made by mkapk.py (a compressed entry)')
    libs = {os.path.basename(i.filename) for i in z.infolist() if i.filename.startswith(ABI)}
    if 'libdmhost.so' not in libs: raise SystemExit(f'{src}: not an nx2android port (no {ABI}libdmhost.so)')
    if driver not in (KEEP, None) and not NEEDS <= libs:
        raise SystemExit(f'{src} has no libadrenotools (it was ported without --vulkan-driver): port the game again with --vulkan-driver once; later driver changes need no game files')
    assets = dict(assets or {}); entries, dropped, kept = [], [], ''
    for i in z.infolist():
        base = os.path.basename(i.filename)
        if i.filename.startswith(ABI) and base not in OWN:
            if driver is KEEP: kept = base
            else: dropped.append(base); continue
        data = open(host, 'rb').read() if host and i.filename == ABI + 'libdmhost.so' else z.read(i)   # the host library built again (porter host)
        if i.filename.startswith('assets/') and i.filename[7:] in assets: data = open(assets[i.filename[7:]], 'rb').read()
        entries.append((i.filename, data, 16384 if i.filename.startswith(ABI) else 4))   # libraries page-aligned, as mkapk.py writes them (extracted, or mapped in place)
    have = {e for e, _, _ in entries}
    entries += [(f'assets/{n}', open(f, 'rb').read(), 4) for n, f in assets.items() if f'assets/{n}' not in have]   # stored, as mkapk.py writes them: AAsset reads them in place
    if driver is KEEP: return entries, dropped, kept
    added = ''
    if driver:
        added = lib_name(driver)
        if added in OWN: raise SystemExit(f'{driver}: named like one of nx2android\'s own libraries')
        at = next(n for n, (e, _, _) in enumerate(entries) if e == ABI + 'libdmhost.so') + 1
        entries.insert(at, (ABI + added, open(driver, 'rb').read(), 16384))
    return entries, dropped, added


def main():
    p = argparse.ArgumentParser(description='an installed port\'s APK with another Vulkan driver library, signed again with the same key')
    p.add_argument('src'); p.add_argument('out'); p.add_argument('key')
    g = p.add_mutually_exclusive_group(); g.add_argument('--driver', help='the driver library (.so, such as Mesa\'s Turnip)'); g.add_argument('--system', action='store_true', help='no driver library: the device\'s own')
    p.add_argument('--host', help='libdmhost.so built again from this checkout (porter host); the driver stays unless --driver / --system is given')
    p.add_argument('--asset', action='append', default=[], metavar='NAME=FILE', help='FILE as assets/NAME, replacing an entry of that name (porter host: the overlay font)')
    p.add_argument('--set-drivers', action='store_true', help='replace the APK\'s driver set with the --set-driver ones (none: no driver library)')
    p.add_argument('--set-driver', action='append', default=[], metavar='LIB=FILE', help='with --set-drivers: FILE as lib/<abi>/LIB, in this order')
    p.add_argument('--loader', action='append', default=[], metavar='FILE', help='with --set-drivers: libadrenotools or one of its hooks, added when the APK lacks it')
    p.add_argument('--external-dex', metavar='DEX', help='the external-display activity (org.nx2a.ExternalActivity): its classes.dex goes in and the manifest names it; the rest stays')
    p.add_argument('--native-activity', action='store_true', help='Android\'s NativeActivity again: the external-display activity and its classes.dex go')
    p.add_argument('--game-modes', action='store_true', help='with any of the above, or alone: Android\'s Battery and Performance game modes declared where the APK lacks them (porter host)')
    a = p.parse_args()
    if any('=' not in x or x.startswith('=') for x in a.asset): p.error('--asset takes NAME=FILE')
    assets = {n: f for n, _, f in (x.partition('=') for x in a.asset)}
    if a.external_dex or a.native_activity:
        if a.external_dex and a.native_activity: p.error('--external-dex or --native-activity, not both')
        if a.set_drivers or a.driver or a.system: p.error('the activity is changed on its own, or with --host / --asset')
        entries, dropped, _ = rebuild(a.src, KEEP, a.host, assets)
        entries, activity = with_activity(entries, a.external_dex)
        result = {'activity': activity}
    elif a.set_drivers:
        if a.driver or a.system: p.error('--set-drivers replaces --driver / --system')
        if any('=' not in x or x.startswith('=') for x in a.set_driver): p.error('--set-driver takes LIB=FILE')
        entries, dropped = rebuild_set(a.src, [tuple(x.split('=', 1)) for x in a.set_driver], a.loader, a.host, assets)
        result = {'drivers': [x.split('=', 1)[0] for x in a.set_driver], 'dropped': dropped}
    else:
        if a.set_driver or a.loader: p.error('--set-driver and --loader go with --set-drivers')
        if not (a.driver or a.system or a.host or a.asset or a.game_modes): p.error('give --driver, --system, --host, --asset or --game-modes')
        entries, dropped, added = rebuild(a.src, None if a.system else a.driver or KEEP, a.host, assets)
        result = {'driver': added, 'dropped': dropped}
    if a.game_modes: entries, result['game_modes_added'] = with_game_modes(entries)
    kj = json.load(open(a.key)); k = {n: int(v) for n, v in kj.items() if n != 'cert'}; crt = bytes.fromhex(kj['cert'])
    z, cd, eocd = build_zip(entries)
    open(a.out, 'wb').write(sign_v2(z, cd, eocd, k, crt))
    print(json.dumps(result))


if __name__ == '__main__': sys.exit(main())
