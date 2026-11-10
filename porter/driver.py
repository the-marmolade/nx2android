# Another Vulkan driver for a port already on the device (python -m porter driver …), without the game's files: the installed APK is pulled, written again with the new
# driver library by nxnative/dm/android/apk/apkdriver.py and signed with the player's key (the same signer: it installs over the app, its saves stay), and env.txt's
# DM_VK_DRIVER row names the library (gfx_vk_core.c vk_init loads it through libadrenotools; no row: the device's driver). The game's data on the device is not touched.
# Only an APK ported with a driver carries libadrenotools: one ported without needs one port with --vulkan-driver first.
import json, re, shlex, subprocess, sys, tempfile
from pathlib import Path

from porter import datapack, paths
from porter.adb import AdbError
from porter.paths import DM
from porter.upstream import BuildError, say

ROW = 'DM_VK_DRIVER'


def env_with_driver(text, lib):
    """env.txt with its DM_VK_DRIVER row naming lib, in place of the old row (appended when there was none), or dropped when lib is '' (the device's driver)"""
    lines = text.splitlines(); out, done = [], False
    for ln in lines:
        if re.match(rf'\s*{ROW}\s*=', ln):
            if lib and not done: out.append(f'{ROW}={lib}'); done = True
            continue
        out.append(ln)
    if lib and not done: out.append(f'{ROW}={lib}')
    return '\n'.join(out) + '\n'


def installed_apk(adb, package):   # the installed APK's path on the device (ports are one APK, no splits)
    rows = [ln[len('package:'):].strip() for ln in adb.shell(f'pm path {shlex.quote(package)}', check=False).splitlines() if ln.startswith('package:')]
    if not rows: raise BuildError(f'{package} is not installed on the device')
    return rows[0]


# ---- the driver set (porter drivers; the GUI's Drivers window): up to three drivers in the APK, named in the pause menu's Driver tab (front_android.c drivers_init:
# env.txt's DM_VK_DRIVERS, NAME=lib*.so;...), one of them or the device's own (no DM_VK_DRIVER row) the default
MAX = 3
LIST_ROW = 'DM_VK_DRIVERS'
LOADER = ('libadrenotools.so', 'libhook_impl.so', 'libmain_hook.so', 'libfile_redirect_hook.so', 'libgsl_alloc_hook.so')   # porter/pipeline.py ADRENOTOOLS_LIBS
OWN = set(LOADER) | {'libdmhost.so'}


def menu_name(s):   # the menu draws ASCII only, ≤ 23 characters, and ; and = separate DM_VK_DRIVERS' entries
    return re.sub(r'\s+', ' ', re.sub(r'[^ -~]|[;=]', '', s or '')).strip()[:20].strip() or 'driver'


def env_drivers(text):
    """env.txt's driver set as the app reads it (drivers_init): ([(name, lib)], the default lib, '' for the device's driver)"""
    rows = dict(m.groups() for m in re.finditer(r'^\s*(DM_VK_DRIVERS?)\s*=\s*(.*?)\s*$', text or '', re.M))
    out = []
    for part in (rows.get(LIST_ROW) or '').split(';'):
        n, _, lib = part.partition('=')
        if n and lib and len(out) < MAX: out.append((n, lib))
    cur = rows.get(ROW, '')
    if cur and cur not in [l for _, l in out] and len(out) < MAX:
        from porter.pipeline import driver_menu_name
        out.append((driver_menu_name(cur), cur))
    return out, cur


def env_with_drivers(text, drivers, default):
    """env.txt with its DM_VK_DRIVER and DM_VK_DRIVERS rows for drivers ([(name, lib)]) and default (a lib, or '' for the device's driver), in place of the old rows"""
    out = [ln for ln in (text or '').splitlines() if not re.match(r'\s*DM_VK_DRIVERS?\s*=', ln)]
    if default: out.append(f'{ROW}={default}')
    if drivers: out.append(f'{LIST_ROW}=' + ';'.join(f'{n}={l}' for n, l in drivers))
    return '\n'.join(out) + '\n'


def settings_without_choice(text):   # settings.txt without the menu's driver= choice: an index into the old list, which the new one would give another meaning
    return ''.join(ln + '\n' for ln in (text or '').splitlines() if not re.match(r'\s*driver\s*=', ln))


def _apk_libs(adb, package):   # the libraries the installed app has (the package manager extracts them beside its APK)
    d = installed_apk(adb, package).rsplit('/', 1)[0]
    return sorted(n.strip() for n in adb.shell(f'ls {shlex.quote(d + "/lib/arm64")}', check=False).split() if n.strip().endswith('.so'))


def gpu(adb):   # the device's GPU as the system's GL stack names it (Adreno (TM) 740), '' when unknown
    m = re.search(r'GLES:\s*([^\r\n]+)', adb.shell('dumpsys SurfaceFlinger | grep -m1 GLES:', check=False))
    return ', '.join(m.group(1).split(',')[:2]).strip() if m else ''


def current(adb, package):
    """package's driver set: {'package', 'drivers': [{'name', 'lib'}], 'default' (a lib, '' the device's), 'loader' (the APK carries libadrenotools), 'gpu'}"""
    env = adb.read_text(f'{datapack.files_folder(package)}/env.txt')
    drivers, default = env_drivers(env)
    libs = _apk_libs(adb, package)
    drivers = [(n, l) for n, l in drivers if l in libs or not libs]   # rows whose library the APK lacks are not offered
    return {'package': package, 'drivers': [{'name': n, 'lib': l} for n, l in drivers], 'default': default if default in [l for _, l in drivers] else '',
            'loader': all(x in libs for x in LOADER), 'gpu': gpu(adb)}


def read_driver(path, dest=None):
    """A driver file: an AdrenoTools .zip (meta.json names its library and the driver) or the library itself (.so). → {'name', 'description', 'lib', 'file'}; with dest
    (a folder), the library is written there and 'file' is its path"""
    import zipfile
    p = Path(path)
    if not p.is_file(): raise BuildError(f'{p}: no such file')
    if zipfile.is_zipfile(p):
        with zipfile.ZipFile(p) as z:
            meta = {}
            if 'meta.json' in z.namelist():
                try: meta = json.loads(z.read('meta.json').decode('utf-8', 'replace'))
                except ValueError: meta = {}
            sos = [n for n in z.namelist() if n.endswith('.so') and not n.endswith('/')]
            lib = meta.get('libraryName') if meta.get('libraryName') in sos else (sos[0] if len(sos) == 1 else None)
            if not lib: raise BuildError(f'{p.name}: not a driver package (no meta.json naming its library, and not exactly one .so in it)')
            data = z.read(lib)
        name = menu_name(meta.get('name') or Path(lib).stem)
        desc = ' · '.join(str(meta[k]) for k in ('description', 'driverVersion', 'vendor') if meta.get(k))
    else:
        data = p.read_bytes(); lib = p.name
        from porter.pipeline import driver_menu_name
        name, desc = menu_name(driver_menu_name(p)), ''
    if data[:4] != b'\x7fELF' or data[4] != 2 or int.from_bytes(data[18:20], 'little') != 183:
        raise BuildError(f'{p.name}: {Path(lib).name} is not a 64-bit ARM library (an Android arm64 Vulkan driver)')
    out = {'name': name, 'description': desc, 'lib': Path(lib).name if Path(lib).name.startswith('lib') else 'lib' + Path(lib).name, 'file': str(p)}
    if dest:
        f = Path(dest) / out['lib']; k = 2
        while f.exists(): f = Path(dest) / f'{Path(out["lib"]).stem}_{k}.so'; k += 1
        f.write_bytes(data); out['file'] = str(f)
    return out


def _loader_libs(title_id, out, jobs):   # libadrenotools and its hooks, built with the NDK (dm/android/build.py --adrenotools) for a port made without them
    from porter import toolchain
    from porter.host import clean_env
    ndk, _ = toolchain.find_ndk()
    if not ndk: raise BuildError('no Android NDK found (the driver loader is built with it): python -m porter tools --download')
    say(f'building the driver loader (libadrenotools), which this port was made without')
    r = subprocess.run([sys.executable, str(DM / 'android/build.py'), '--game', title_id, '--ndk', str(ndk), '--out', str(out), '--lib', '--release', '--adrenotools', '--jobs', str(jobs)],
                       capture_output=True, text=True, errors='replace', env=clean_env())
    libs = [Path(out) / n for n in LOADER]
    if r.returncode or not all(f.is_file() for f in libs): raise BuildError('the driver loader did not build: ' + ((r.stderr.strip() or r.stdout.strip()).splitlines() or ['no output'])[-1])
    return libs


def apply(adb, package, drivers, default, jobs=8):
    """package's APK with exactly drivers (in order, at most three: [{'name', 'lib'}] one it has, or [{'name', 'file'}] a new one, a .zip or .so) and default (an index into
    drivers, or -1 for the device's own driver); env.txt names them, and settings.txt's menu choice is cleared so the default applies. The saves and data stay.
    → {'package', 'drivers': [{'name', 'lib'}], 'default', 'loader_added'}"""
    if len(drivers) > MAX: raise BuildError(f'{len(drivers)} drivers: the pause menu\'s Driver tab has room for {MAX}')
    if not -1 <= default < len(drivers): raise BuildError(f'default {default}: not one of the {len(drivers)} drivers (or -1, the device\'s own)')
    files = datapack.files_folder(package)
    try: man = json.loads(adb.read_text(f'{files}/nx2a-data.json') or '{}')
    except ValueError: man = {}
    with tempfile.TemporaryDirectory(prefix='nx2a_drivers_') as t:
        t = Path(t); src, out, new = t / 'installed.apk', t / 'drivers.apk', t / 'new'; new.mkdir()
        say(f'{package}: pulling the installed APK')
        adb.run('pull', installed_apk(adb, package), src, timeout=600)
        import zipfile
        with zipfile.ZipFile(src) as z: have = {Path(n).name: n for n in z.namelist() if n.startswith('lib/arm64-v8a/')}
        chosen, used = [], set(OWN)
        for d in drivers:   # the ones it keeps first, so their library names stay
            if d.get('lib'):
                if d['lib'] not in have or d['lib'] in OWN: raise BuildError(f'{package} has no driver library {d["lib"]}')
                used.add(d['lib'])
        for d in drivers:
            name = menu_name(d.get('name', ''))
            if d.get('lib'):
                f = t / f'keep_{d["lib"]}'
                with zipfile.ZipFile(src) as z: f.write_bytes(z.read(have[d['lib']]))
                chosen.append((name, d['lib'], f))
            else:
                info = read_driver(d['file'], new); lib = info['lib']; stem, k = lib[:-3], 2
                while lib in used: lib = f'{stem}_{k}.so'; k += 1
                used.add(lib); chosen.append((name or info['name'], lib, Path(info['file'])))
        names = [n for n, _, _ in chosen]
        if len(set(names)) != len(names): raise BuildError('two drivers have the same name: the pause menu tells them apart by it')
        loader = []
        if chosen and not all(x in have for x in LOADER):
            tid = str(man.get('title_id') or '').upper()
            if not re.fullmatch(r'[0-9A-F]{16}', tid): raise BuildError(f'{package}: no title ID in its nx2a-data.json, so the driver loader cannot be built for it')
            loader = _loader_libs(tid, t / 'loader', jobs)
        r = subprocess.run([sys.executable, str(DM / 'android/apk/apkdriver.py'), str(src), str(out), str(paths.signing_key()), '--set-drivers']
                           + [a for _, lib, f in chosen for a in ('--set-driver', f'{lib}={f}')] + [a for f in loader for a in ('--loader', str(f))],
                           capture_output=True, text=True, errors='replace')
        if r.returncode: raise BuildError((r.stderr.strip() or r.stdout.strip()).splitlines()[-1])
        adb.shell(f'am force-stop {shlex.quote(package)}', check=False)
        say(f'{package}: installing the APK with ' + (', '.join(f'{n} ({l})' for n, l, _ in chosen) or 'no driver library'))
        try: adb.install(out, package)
        except AdbError as e: raise BuildError(str(e)) from e
        dflt = chosen[default][1] if default >= 0 else ''
        e = t / 'env.txt'; e.write_text(env_with_drivers(adb.read_text(f'{files}/env.txt'), [(n, l) for n, l, _ in chosen], dflt), encoding='utf-8', newline='\n')
        adb.run('push', e, f'{files}/env.txt')
        s = adb.read_text(f'{files}/settings.txt')
        if re.search(r'^\s*driver\s*=', s or '', re.M):
            f = t / 'settings.txt'; f.write_text(settings_without_choice(s), encoding='utf-8', newline='\n'); adb.run('push', f, f'{files}/settings.txt')
    own = "the device's own"
    say(f'{package}: drivers ' + (', '.join(n for n, _, _ in chosen) or 'none') + f'; default {chosen[default][0] if default >= 0 else own}')
    return {'package': package, 'drivers': [{'name': n, 'lib': l} for n, l, _ in chosen], 'default': dflt, 'loader_added': bool(loader)}


def swap(adb, package, driver=None):
    """package's APK again with driver (a .so path), or with the device's own driver when None; env.txt names it. → {'package', 'driver', 'dropped'}"""
    if driver and not Path(driver).is_file(): raise BuildError(f'{driver}: no such driver library')
    with tempfile.TemporaryDirectory(prefix='nx2a_driver_') as t:
        src, out = Path(t) / 'installed.apk', Path(t) / 'driver.apk'
        say(f'{package}: pulling the installed APK')
        adb.run('pull', installed_apk(adb, package), src, timeout=600)
        r = subprocess.run([sys.executable, str(DM / 'android/apk/apkdriver.py'), str(src), str(out), str(paths.signing_key())]
                           + (['--driver', str(driver)] if driver else ['--system']), capture_output=True, text=True, errors='replace')
        if r.returncode: raise BuildError((r.stderr.strip() or r.stdout.strip()).splitlines()[-1])
        res = json.loads(r.stdout.strip().splitlines()[-1])
        adb.shell(f'am force-stop {shlex.quote(package)}', check=False)
        say(f'{package}: installing the APK with ' + (f'{res["driver"]}' if res['driver'] else 'no driver library (the device\'s driver)'))
        try: adb.install(out, package)
        except AdbError as e: raise BuildError(str(e)) from e
        env = f'{datapack.files_folder(package)}/env.txt'
        new = Path(t) / 'env.txt'; new.write_text(env_with_driver(adb.read_text(env), res['driver']), encoding='utf-8', newline='\n')
        adb.run('push', new, env)
    say(f'{package}: ' + (f'{ROW}={res["driver"]}' if res['driver'] else f'no {ROW} row: the device\'s driver') + ' (dropped: ' + (', '.join(res['dropped']) or 'none') + ')')
    return dict(res, package=package)
