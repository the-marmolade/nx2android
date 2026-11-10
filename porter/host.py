# A port on the device brought to this nx2android checkout's host (python -m porter host …), without the game's files: libdmhost.so is built again from the repository's
# profile (dm/android/build.py, as the port's host stage builds it: a debug build for a debuggable app) and put in place of the installed APK's by
# nxnative/dm/android/apk/apkdriver.py --host (with the overlay's font, assets/font/, which an APK ported before it came lacks), signed with the player's key (the same signer: it installs over the app, its saves stay). The data on the device is not touched.
# The game's rewritten modules on the device (mods/) must still fit the host: mods/build_src.sha256 holds the hashes of the rewriter and the patch files that made them
# (patch_nso.py), and any of them changed since (the rewriter, the SDK's patches, the game's own) needs a port again from the game's files. Other games' patch files do not matter,
# being keyed by their own build IDs. The host is built from the repository's profile, so the port must have been made from it too: its version one the profile registers and the
# hash of the game_profile.h it was built with (nx2a-data.json profile_h, which porter port writes) this checkout's. A derived profile (a version the profile does not register, with
# its automatic alias headroom) or --alias-headroom compiled another DM_GAME_MEM_ALIAS into libdmhost.so, and the repository's would give the game a smaller alias region. Nor does a change in sdk_patches.py for other SDK builds: the cuts and observation gates it and the game's patches.py give the build IDs of
# the port's modules are checked against those mods/<module>.cuts.tsv and .obs.tsv list. A changed shader translator or data pack is not carried over either: a port again does that.
import hashlib, json, os, re, shlex, subprocess, sys, tempfile, time
from pathlib import Path

from porter import datapack, paths, toolchain
from porter.adb import AdbError
from porter.driver import installed_apk
from porter.paths import DM, REPO, user_dir
from porter.upstream import BuildError, say


def module_tables(cuts_tsv, obs_tsv):
    """A rewritten module's build ID, cuts and observation gates from its mods/<module>.cuts.tsv and .obs.tsv (patch_nso.py). → {'build_id', 'cuts', 'obs'}"""
    bid, rows = '', {'cuts': [], 'obs': []}
    for kind, text in (('cuts', cuts_tsv), ('obs', obs_tsv)):
        for ln in text.splitlines():
            f = ln.rstrip('\r').split('\t')
            if f[0] == '# BUILD_ID' and len(f) > 1: bid = bid or f[1].strip().lower()
            elif len(f) >= 3 and not f[0].startswith('#'): rows[kind].append((int(f[0], 16), f[1].strip().lower(), f[2].strip().lower()))
    return {'build_id': bid, **rows}


def _tables(path):   # CUTS, OBS and FRAME_STEP of a patch file, as patch_nso.py load_patches reads them
    import importlib.util
    spec = importlib.util.spec_from_file_location(f'nx2a_host_{abs(hash(str(path)))}', path); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return {k: getattr(m, k, {}) for k in ('CUTS', 'OBS', 'FRAME_STEP')}


def sdk_patches_fit(modules, title_id, extra, tools=DM / 'tools'):
    """True when this checkout's sdk_patches.py, with the game's own patches.py, gives each of the port's modules the cuts and observation gates it was rewritten with.
    modules: module_tables() of every module; extra: the port had patch files outside the repository (--fps60 cuts after the registered ones of main)."""
    if not modules or any(not m['build_id'] for m in modules): return False
    files = [tools / 'sdk_patches.py'] + [p for p in [DM / 'games' / title_id / 'patches.py'] if p.is_file()]
    try: tables = [_tables(p) for p in files]
    except Exception: return False
    for m in modules:
        bid = m['build_id']
        if any(bid in t['FRAME_STEP'] for t in tables[:1]): return False   # a frame step the SDK's patches now give it
        cuts = [(o, ob.lower(), nb.lower()) for t in tables for o, ob, nb, _ in t['CUTS'].get(bid, [])]
        obs = [(o, str(n).lower(), str(w).lower()) for t in tables for o, n, w, _ in t['OBS'].get(bid, [])]
        if m['obs'] != obs: return False
        if m['cuts'] != cuts and not (extra and m['cuts'][:len(cuts)] == cuts): return False
    return True


def stale_sources(record, title_id, tools=DM / 'tools', modules=None):
    """The rewriter's sources that changed since the port: record is mods/build_src.sha256 ("<sha256>  <path from dm/tools>" per line); another game's patches.py is left out,
    and so is a file outside the repository (a --fps60 port's patches.py in its build folder). A changed sdk_patches.py is left out too when modules (module_tables() of the
    port's modules) show it gives them what they were rewritten with (sdk_patches_fit). → [path]"""
    out = []
    for ln in record.splitlines():
        h, _, rel = ln.strip().partition('  ')
        if not h or not rel: continue
        p = (tools / rel).resolve()
        if p.name == 'patches.py' and p.parent.parent == (DM / 'games').resolve() and p.parent.name.upper() != title_id.upper(): continue
        if DM.resolve() not in p.parents: continue
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest() != h: out.append(rel)
    if 'sdk_patches.py' in out and modules is not None:
        extra = any(DM.resolve() not in (tools / ln.strip().partition('  ')[2]).resolve().parents for ln in record.splitlines() if ln.strip().partition('  ')[2])
        if sdk_patches_fit(modules, title_id, extra, tools): out.remove('sdk_patches.py')
    own = DM / 'games' / title_id / 'patches.py'
    if own.is_file() and not any(Path(ln.strip().partition('  ')[2]).name == 'patches.py' and title_id.upper() in ln.upper() for ln in record.splitlines()):
        out.append(Path(os.path.relpath(own, tools)).as_posix())   # patches registered for the game since the port: its modules on the device lack them
    return out


TITLE_ID = re.compile(r'[0-9A-Fa-f]{16}')


def clean_env():   # the environment without DM_GAMES_DIR / DM_GAMES_FIRST: the host and its profile header come from the repository's profile only
    return {k: v for k, v in os.environ.items() if k not in ('DM_GAMES_DIR', 'DM_GAMES_FIRST')}


def profile_hash(title_id):
    """sha256 of the game_profile.h the repository's profile of title_id makes (dm/games/game.py header, as dm/android/build.py makes it)"""
    with tempfile.TemporaryDirectory(prefix='nx2a_profile_') as t:
        h = Path(t) / 'game_profile.h'
        r = subprocess.run([sys.executable, str(DM / 'games/game.py'), 'header', title_id, str(h)], capture_output=True, text=True, errors='replace', env=clean_env())
        if r.returncode or not h.is_file(): raise BuildError(f'{title_id}: the profile header did not build: ' + ((r.stderr.strip() or r.stdout.strip()).splitlines() or ['no output'])[-1])
        return hashlib.sha256(h.read_bytes()).hexdigest()


STAMP = 'nx2a-host.json'   # in the app's files folder: the host an update put there, {'version', 'fingerprint', 'made', 'forced'}
_FP_SKIP_DIRS = {'games', 'tools', 'out', '__pycache__', '.git', 'tests', 'docs', 'apk'}   # (android/apk: the tools that pack an APK, not what goes in it)


def checkout_version():   # the bundle's VERSION (packaging/build_bundle.py), else git describe of the checkout
    v = REPO / 'VERSION'
    if v.is_file(): return v.read_text(encoding='utf-8').strip() or 'dev'
    try: return subprocess.run(['git', '-C', str(REPO), 'describe', '--always', '--dirty'], capture_output=True, text=True, timeout=20).stdout.strip() or 'dev'
    except (OSError, subprocess.SubprocessError): return 'dev'


_fp_base = None
def host_fingerprint(title_id):
    """sha256 over the sources a game's libdmhost.so and the APK's assets come from: nxnative/dm without its games, tools, tests and build output, plus the game's own profile
    folder. The same commit gives the same value in a checkout and in a bundle (both have the committed files), and a docs-only commit leaves it alone"""
    global _fp_base
    if _fp_base is None:
        # a checkout: its committed files only (git ls-files), as the bundle has them; ignored build output (obj/, out/) would make the two differ
        names = None
        if (REPO / '.git').exists():
            try:
                r = subprocess.run(['git', '-C', str(REPO), 'ls-files', '-z', '--', DM.relative_to(REPO).as_posix()], capture_output=True, timeout=60)
                if r.returncode == 0: names = [Path(REPO / n.decode()).relative_to(DM).as_posix() for n in r.stdout.split(b'\0') if n]
            except (OSError, subprocess.SubprocessError, ValueError): names = None
        if names is None: names = [(Path(d) / f).relative_to(DM).as_posix() for d, _, fs in os.walk(DM) for f in fs]
        _fp_base = sorted(n for n in names if not n.endswith(('.md', '.pyc', '.d', '.o')) and not set(n.split('/')[:-1]) & _FP_SKIP_DIRS
                          and not any(p.startswith('.') for p in n.split('/')[:-1]) and (DM / n).is_file())
    own = [n for n in _fp_base]
    g = DM / 'games' / title_id
    if g.is_dir(): own += sorted((Path(d) / f).relative_to(DM).as_posix() for d, _, fs in os.walk(g) for f in fs if not f.endswith('.pyc') and '__pycache__' not in d)
    own += [n for n in ('games/game.py',) if (DM / n).is_file()]
    return hashlib.sha256('\n'.join(f'{hashlib.sha256((DM / n).read_bytes()).hexdigest()}  {n}' for n in own).encode()).hexdigest()


# ---- build folders (<game folder>/<title ID>_build, porter port): a derived profile lives there, and the header the port's host was built with
def _folders_file(): return user_dir() / 'build_folders.json'


def remembered_folders():
    try: d = json.loads(_folders_file().read_text(encoding='utf-8'))
    except (OSError, ValueError): d = {}
    return d if isinstance(d, dict) else {}


def remember_folder(title_id, folder):
    d = remembered_folders(); d[title_id.upper()] = str(folder)
    f = _folders_file(); f.parent.mkdir(parents=True, exist_ok=True); t = f.with_suffix('.tmp'); t.write_text(json.dumps(d, indent=2), encoding='utf-8'); t.replace(f)


def _as_build_folder(p, title_id):   # p: the build folder, or the game folder that holds it
    p = Path(p)
    for q in (p, p / f'{title_id}_build'):
        if (q / 'android').is_dir() or (q / 'profile-derived').is_dir(): return q
    return None


def find_build_folder(title_id, hint=''):
    """The port's build folder: hint, the one remembered for the game, else a look one level down the usual places (Downloads, Desktop, Documents, the output folder)"""
    for c in [hint, remembered_folders().get(title_id.upper(), '')]:
        if c:
            q = _as_build_folder(c, title_id)
            if q: return q
    home = Path.home(); roots = [home / 'Downloads', home / 'Desktop', home / 'Documents']
    try:
        from porter import config
        out = config.load().get('out')
        if out: roots.append(Path(out))
    except Exception: pass
    for r in roots:
        try: ds = [r] + [x for x in r.iterdir() if x.is_dir()]
        except OSError: continue
        for d in ds:
            q = d / f'{title_id}_build'
            if q.is_dir() and _as_build_folder(q, title_id): return q
    return None


def _built_header(folder, title_id):   # the game_profile.h the port's host was built with (build.py writes it under the host's gen/)
    for sub in ('host', 'host-debug'):
        h = Path(folder) / 'android' / sub / 'gen' / title_id / 'game_profile.h'
        if h.is_file(): return h.read_text(encoding='utf-8', errors='replace')
    return None


def _defines(text): return dict(m.groups() for m in re.finditer(r'^#define\s+(\w+)\s+(.*?)\s*$', text or '', re.M))


def profile_header(title_id, games_dir=None):   # the bytes of the game_profile.h this checkout makes for the game (games_dir: a derived profile's folder, first)
    env = clean_env()
    if games_dir: env.update(DM_GAMES_DIR=str(games_dir), DM_GAMES_FIRST='1')
    with tempfile.TemporaryDirectory(prefix='nx2a_profile_') as t:
        h = Path(t) / 'game_profile.h'
        r = subprocess.run([sys.executable, str(DM / 'games/game.py'), 'header', title_id, str(h)], capture_output=True, text=True, errors='replace', env=env)
        if r.returncode or not h.is_file(): raise BuildError(f'{title_id}: the profile header did not build: ' + ((r.stderr.strip() or r.stdout.strip()).splitlines() or ['no output'])[-1])
        return h.read_bytes()


def same_layout(old, new):
    """True when every setting both headers define has the same value: a setting this checkout added since (a new #define, at its default) does not count"""
    a, b = _defines(old), _defines(new)
    return bool(a) and all(b[k] == v for k, v in a.items() if k in b)


def check_profile(package, manifest, title_id):
    """Refuses (BuildError) a port not made from this checkout's profile of title_id: its version unregistered, or its profile header's hash absent or another"""
    sys.path.insert(0, str(DM / 'games'))
    try: import game
    finally: sys.path.pop(0)
    builds = game.load(title_id).builds()
    ver = manifest.get('version', '')
    if ver not in builds:
        raise BuildError(f'{package}: {ver or "no version"} is not a version the profile of {title_id} registers ({", ".join(builds) or "none"}): the port came from a derived profile '
                         f'with its own alias region; port the game again')
    if not manifest.get('profile_h'):
        raise BuildError(f'{package}: no profile_h in nx2a-data.json (a data pack made before nx2android recorded the profile the host was built from): port the game again')
    if manifest['profile_h'] != profile_hash(title_id):
        raise BuildError(f'{package}: the host on the device was built from another profile of {title_id} than this checkout\'s (another layout, --alias-headroom or a derived profile): '
                         f'port the game again')


def _read_json(adb, path):
    try: d = json.loads(adb.read_text(path) or '{}')
    except ValueError: d = {}
    return d if isinstance(d, dict) else {}


def inspect(adb, package, folder=''):
    """Whether package can be brought to this checkout's host, without building anything. → {'package', 'title_id', 'name', 'display', 'version', 'installed', 'status',
    'reason', 'stale', 'derived', 'folder'}; status: current (built from this checkout's sources), update, risky (the rewriter changed since the port: an update only with
    force; a port again is the safe way), folder (needs the port's build folder to check its profile), port (only a port again)"""
    files = datapack.files_folder(package)
    man = _read_json(adb, f'{files}/nx2a-data.json'); stamp = _read_json(adb, f'{files}/{STAMP}')
    tid = man.get('title_id', '')
    r = {'package': package, 'title_id': tid.upper() if isinstance(tid, str) else '', 'name': man.get('name') or package, 'display': man.get('display', ''),
         'version': man.get('version', ''), 'installed': stamp.get('version') or (man.get('host') or {}).get('version') or '', 'status': 'port', 'reason': '', 'stale': [],
         'derived': False, 'folder': ''}
    if not tid: r['reason'] = 'no title ID in its nx2a-data.json (a data pack made before nx2android wrote one)'; return r
    if not isinstance(tid, str) or not TITLE_ID.fullmatch(tid): r.update(title_id='', reason=f'{tid!r} in its nx2a-data.json is not a title ID (16 hexadecimal digits)'); return r
    tid = tid.upper()
    if not (DM / 'games' / tid / 'game.tsv').is_file(): r['reason'] = f'no profile of {tid} in this version (an experimental port)'; return r
    record = adb.read_text(f'{files}/mods/build_src.sha256')
    if not record.strip(): r['reason'] = 'no mods/build_src.sha256 on the device'; return r
    sys.path.insert(0, str(DM / 'games'))
    try: import game
    finally: sys.path.pop(0)
    derived = r['version'] not in game.load(tid).builds(); r['derived'] = derived
    bf = find_build_folder(tid, folder)
    if bf: r['folder'] = str(bf)
    games_dir = None
    if derived:
        if not bf:
            r.update(status='folder', reason=f'{r["version"] or "no version"} is not a version the profile of {tid} registers (a derived profile): its build folder ({tid}_build, '
                                              'beside the game\'s files) has the profile it was ported with')
            return r
        games_dir = bf / 'profile-derived'
        if not (games_dir / tid / 'game.tsv').is_file(): r.update(status='folder', reason=f'{bf} has no derived profile of {tid}'); return r
    try: new = profile_header(tid, games_dir)
    except BuildError as e: r['reason'] = str(e); return r
    old = _built_header(bf, tid) if bf else None
    # The port's profile: its recorded hash (porter port's profile_h), else the header its host was built with in its build folder, setting by setting (same_layout:
    # a setting this checkout added since, at its default, is no change)
    if man.get('profile_h') and man['profile_h'] == hashlib.sha256(new).hexdigest(): pass
    elif old is not None:
        if not same_layout(old, new.decode('utf-8', 'replace')): r['reason'] = f'this version gives {tid} another memory layout than its port was built with (another profile)'; return r
    elif man.get('profile_h'):
        r.update(status='folder', reason=f'the host on the device was built from another profile of {tid} than this version\'s: its build folder tells whether only new settings changed'); return r
    else:
        r.update(status='folder', reason='no profile_h in its nx2a-data.json (a port made before nx2android recorded its profile): its build folder has the header its host was built with')
        return r
    names = sorted({n.strip().rsplit('/', 1)[-1][:-len('.cuts.tsv')] for n in adb.shell(f'ls {shlex.quote(files)}/mods', check=False).split() if n.strip().endswith('.cuts.tsv')})
    modules = [module_tables(adb.read_text(f'{files}/mods/{n}.cuts.tsv'), adb.read_text(f'{files}/mods/{n}.obs.tsv')) for n in names]
    r['stale'] = stale_sources(record, tid, modules=modules)
    if (stamp.get('fingerprint') or (man.get('host') or {}).get('fingerprint')) == host_fingerprint(tid): r['status'] = 'current'; return r
    if r['stale']:
        r.update(status='risky', reason='the code rewriter changed since the port (' + ', '.join(r['stale']) + '): a port again is the safe way; an update keeps the game\'s rewritten code')
        return r
    r['status'] = 'update'; return r


def update(adb, package, jobs=os.cpu_count() or 8, folder='', force=False):
    """package's libdmhost.so built again from this checkout and installed (folder: its build folder, for a derived profile or a port made before profile_h; force: also when
    the rewriter changed since the port). → {'package', 'title_id', 'debug', 'host', 'version'}"""
    s = inspect(adb, package, folder)
    if s['status'] == 'port': raise BuildError(f'{package}: {s["reason"]}: port the game again')
    if s['status'] == 'folder': raise BuildError(f'{package}: {s["reason"]} (--folder)')
    if s['status'] == 'risky' and not force: raise BuildError(f'{package}: {s["reason"]} (--force to update anyway)')
    title_id, files = s['title_id'], datapack.files_folder(package)
    env = clean_env()
    if s['derived']: env.update(DM_GAMES_DIR=str(Path(s['folder']) / 'profile-derived'), DM_GAMES_FIRST='1')
    debug = 'DEBUGGABLE' in adb.shell(f'dumpsys package {shlex.quote(package)} | grep -m1 flags=', check=False)
    ndk, _ = toolchain.find_ndk()
    if not ndk: raise BuildError('no Android NDK found: python -m porter tools --download')
    with tempfile.TemporaryDirectory(prefix='nx2a_host_') as t:
        say(f'{package}: building the host of {title_id} ({"debug" if debug else "release"} build' + (', from its derived profile' if s['derived'] else '') + ')')
        r = subprocess.run([sys.executable, str(DM / 'android/build.py'), '--game', title_id, '--ndk', str(ndk), '--out', t, '--lib', '--jobs', str(jobs)] + ([] if debug else ['--release']),
                           capture_output=True, text=True, errors='replace', env=env)
        so = Path(t) / 'libdmhost.so'
        if r.returncode or not so.is_file(): raise BuildError(f'{package}: the host did not build: ' + ((r.stderr.strip() or r.stdout.strip()).splitlines() or ['no output'])[-1])
        src, out = Path(t) / 'installed.apk', Path(t) / 'host.apk'
        adb.run('pull', installed_apk(adb, package), src, timeout=600)
        from porter.pipeline import ui_font_assets   # the overlay's font: an APK ported before it came has none, and the new host looks for it
        fonts = [a for n, f in ui_font_assets().items() for a in ('--asset', f'{n}={f}')]
        r = subprocess.run([sys.executable, str(DM / 'android/apk/apkdriver.py'), str(src), str(out), str(paths.signing_key()), '--host', str(so)] + fonts,
                           capture_output=True, text=True, errors='replace')
        if r.returncode: raise BuildError((r.stderr.strip() or r.stdout.strip()).splitlines()[-1])
        size = so.stat().st_size
        adb.shell(f'am force-stop {shlex.quote(package)}', check=False)
        try: adb.install(out, package)
        except AdbError as e: raise BuildError(str(e)) from e
        ver = checkout_version()
        st = Path(t) / STAMP
        st.write_text(json.dumps({'version': ver, 'fingerprint': host_fingerprint(title_id), 'made': time.strftime('%Y-%m-%d %H:%M:%S'), 'forced': s['status'] == 'risky'}, indent=2),
                      encoding='utf-8')
        adb.run('push', st, f'{files}/{STAMP}')
    if s['folder']: remember_folder(title_id, s['folder'])
    say(f'{package}: host of this checkout installed ({size / 2**20:.1f} MB); the game\'s data on the device is unchanged')
    return {'package': package, 'title_id': title_id, 'debug': debug, 'host': size, 'version': ver}
