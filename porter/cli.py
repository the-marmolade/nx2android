# The command line (python -m porter …). Every command the GUI uses is here, so a port runs the same headless. Exit codes: 0 done, 1 error, 130 interrupted.
import argparse, json, os, sys
from pathlib import Path


def _parser():
    ap = argparse.ArgumentParser(prog='porter', description='Port your own Switch game files to an Android app (docs/ARCHITECTURE.md).')
    sub = ap.add_subparsers(dest='cmd', required=True)
    d = sub.add_parser('doctor', help='check the tools a port needs'); d.add_argument('--json', action='store_true'); d.add_argument('-k', '--keys')
    p = sub.add_parser('profiles', help='list the games the tool can port'); p.add_argument('--all', action='store_true', help='also the iOS profiles not ported to Android'); p.add_argument('--json', action='store_true')
    i = sub.add_parser('inspect', help='what a game folder holds and whether it can be ported'); i.add_argument('folder'); i.add_argument('--json', action='store_true')
    i.add_argument('-k', '--keys', help='prod.keys (default: the configured one): reads the title ID of a dump with no [title ID] in its name')
    po = sub.add_parser('port', help='make the APK and the data pack (and install them)')
    po.add_argument('folder', help='the game\'s folder: its base game NSP / XCI / NSZ / XCZ, updates and DLC')
    po.add_argument('-k', '--keys', help='prod.keys (default: the configured one)')
    po.add_argument('-o', '--out', help='folder for the APK and the data pack (default: the game folder)')
    po.add_argument('-p', '--version', default='', help='version to pack, v<N> (default: the newest in the folder)')
    po.add_argument('-l', '--language', default='', help='game language, a code or a name (default: English)')
    po.add_argument('--app-name', default='', help='the app\'s name on the device (default: the game\'s name)')
    po.add_argument('--install', action='store_true', help='install on the connected device afterwards')
    po.add_argument('--device', default='', help='adb serial of the device to install on')
    po.add_argument('--replace-signer', action='store_true', help='uninstall an app of the same package signed with another key first (deletes its saves)')
    po.add_argument('--debug', action='store_true', help='a development build: debug information, debuggable, DM_CTL key presses')
    po.add_argument('--experimental', action='store_true', help='try a game not ported to Android yet (a profile guessed from a survey of its files; it may not start)')
    po.add_argument('--package', default='', help="the app's package instead of the profile's (a test install beside another build of the game)")
    po.add_argument('--external-display', action='store_true', help='build the external-screen gamepad activity (requires Android SDK platform and build-tools)')
    po.add_argument('--fps60', action='store_true', help='60 fps: the profile\'s own frame-rate cap, else the community\'s FPSLocker-Warehouse config of the game\'s build, fetched from GitHub')
    po.add_argument('--touch', action='store_true',
                    help='a game played by touch: the on-screen gamepad starts hidden, so every touch but the menu button\'s goes to the game (the pause menu shows it again; '
                         'the first launch\'s default: the app keeps the player\'s own settings)')
    po.add_argument('--preset', default='', metavar='DEVICE',
                    help='a device preset: env.txt and settings.txt defaults for a handheld, under the game profile\'s own (thor: the replay thread on the prime core, '
                         'the on-screen gamepad hidden)')
    po.add_argument('--gpu-turbo', action='store_true', help='DM_GPU_TURBO=1: an Adreno GPU held at its highest clock (more heat and battery; thermal limits still apply)')
    po.add_argument('--mt-replay', action='store_true',
                    help='multithread replay: the game\'s Vulkan commands are recorded on a thread of their own (DM_VK_MT_REPLAY=1 in env.txt), for a game whose replay '
                         'thread holds its frame rate back; it needs a port again (or env.txt edited) to turn off')
    po.add_argument('--vulkan-driver', default=None, metavar='[NAME=]FILE', action='append',
                    help='an arm64 Vulkan driver library (.so, such as Mesa\'s Turnip for Adreno) to pack in the APK and use instead of the device\'s own driver '
                         '(DM_VK_DRIVER in env.txt); the app falls back to the device\'s driver when the library does not load. A library not named lib*.so '
                         '(vulkan.purple.so) is packed as lib<name>, the only names Android extracts. Give it up to three times to pack several: the first is the default, '
                         'and the pause menu\'s Driver tab picks among them and the system\'s for the next launch (Quit, then reopen); NAME= is the menu\'s name for it')
    po.add_argument('--shared-font', default=None, metavar='FILE',
                    help='a TrueType font (.ttf, one font, not a collection) to pack as the system font the game asks for, instead of the device\'s Roboto: one with CJK '
                         'characters shows the Chinese and Korean text of a game that draws it with the system font (DM_SHARED_FONT in env.txt); never shipped with the tool')
    po.add_argument('--firmware', default=None, metavar='DIR',
                    help="a folder of your console's system content files (.nca: its firmware dump, NAND SYSTEM Contents/registered) for a game that reads system data "
                         "(android.tsv sysdata: Mario Kart 8 Deluxe's Mii heads come from MiiModel); never shipped with the tool (default: the configured one)")
    po.add_argument('--vercode-offset', type=int, default=None, metavar='N',
                    help='add N (0-65535) to the APK\'s versionCode, so a rebuild of the same game version installs over a build with a higher one and keeps its saves '
                         '(default: $NX2A_VERCODE_OFFSET, else 0)')
    po.add_argument('--alias-headroom', type=int, default=None, metavar='GB',
                    help='GB (0-48) of extra guest address space (the alias region) for a game with virtual address memory, for a game whose log shows '
                         '"AllocateAddressRegion refused (0x1803)" before it crashes; it uses no memory (default: 8 for a game version the profile was not '
                         'brought up on, none for one it was)')
    _romfs_at(po, 'with --install: ')
    po.add_argument('--jobs', type=int, default=os.cpu_count() or 8)
    po.add_argument('--progress', default='auto', choices=('auto', 'bar', 'lines', 'json', 'off'), help='json: one JSON event per line, for the GUI')
    ins = sub.add_parser('install', help='install a port made earlier'); ins.add_argument('data', help='the data pack folder (<App>-data)'); ins.add_argument('--apk', help='the APK (default: <App>.apk beside the pack)')
    ins.add_argument('--device', default=''); ins.add_argument('--replace-signer', action='store_true'); ins.add_argument('--progress', default='auto', choices=('auto', 'bar', 'lines', 'json', 'off'))
    _romfs_at(ins)
    dv = sub.add_parser('devices', help='the devices adb sees'); dv.add_argument('--json', action='store_true')
    t = sub.add_parser('tools', help='list, or download, the missing tools (Android NDK, .NET SDK, platform-tools) from Google and Microsoft')
    t.add_argument('--download', action='store_true', help='download and unpack them into the nx2android folder (you accept their licenses)')
    t.add_argument('--only', default='', help='these instead of the missing ones: ndk, dotnet, adb (comma-separated)'); t.add_argument('--json', action='store_true')
    t.add_argument('--progress', default='auto', choices=('auto', 'bar', 'lines', 'json', 'off'))
    c = sub.add_parser('config', help='show or change the saved settings'); c.add_argument('key', nargs='?'); c.add_argument('value', nargs='?')
    sv = sub.add_parser('saves', help="a game's save between the device and this PC: list, export, import (a console's save too)")
    svs = sv.add_subparsers(dest='saves_cmd', required=True)
    sa = svs.add_parser('apps', help='the ported games installed on the device')
    sl = svs.add_parser('list', help="the save folders in the app's files folder (saves/), newest first")
    se = svs.add_parser('export', help="the game's save to a folder here: a fresh export (the app is stopped, started to export, and ends), or --name one already there")
    se.add_argument('dest', nargs='?', default='.', help='the folder to put it in (default: here)'); se.add_argument('--name', default='', help='a save folder on the device instead of a fresh export')
    si = svs.add_parser('import', help="a save folder or .zip as the game's save (a console's, as its save tools copy it, or an export); the save it replaces is exported first on the device")
    si.add_argument('src', help='the save folder (its files at the top, as the game keeps them) or a .zip of it; <folder>.device beside it is the device save')
    si.add_argument('--name', default='', help="its folder name on the device (default: the folder's or the .zip's)")
    for x in (sa, sl, se, si):
        x.add_argument('--device', default='', help='adb serial (default: the configured device, else the only one)'); x.add_argument('--json', action='store_true')
        if x is not sa: x.add_argument('--package', default='', help='the app (default: the only ported game installed)')
    dr = sub.add_parser('driver', help='another Vulkan driver for a port on the device, without the game files: its APK is rebuilt with the library and signed again (the saves stay)')
    drg = dr.add_mutually_exclusive_group(required=True)
    drg.add_argument('library', nargs='?', help='the driver library (.so, such as Mesa\'s Turnip); the app must have been ported with --vulkan-driver once')
    drg.add_argument('--system', action='store_true', help='no driver library: the device\'s own driver')
    dr.add_argument('--package', default='', help='the app (default: the only ported game installed)')
    dr.add_argument('--device', default='', help='adb serial (default: the configured device, else the only one)'); dr.add_argument('--json', action='store_true')
    hs = sub.add_parser('host', help="a port on the device brought to this version's host, without the game files: its libdmhost.so is built again from the profile (the saves and the game's data stay)")
    hs.add_argument('--package', default='', help='the app (default: the only ported game installed)')
    hs.add_argument('--device', default='', help='adb serial (default: the configured device, else the only one)')
    hs.add_argument('--jobs', type=int, default=os.cpu_count() or 8); hs.add_argument('--json', action='store_true')
    hs.add_argument('--folder', default='', help="the port's build folder (<title ID>_build) or the game folder that holds it: a port from a derived profile, or one made before "
                                                   'nx2android recorded its profile, is checked against it (remembered after an update)')
    hs.add_argument('--force', action='store_true', help='update even when the code rewriter changed since the port (a port again is the safe way)')
    up = sub.add_parser('updates', help='the ported games on the device and whether each can be brought to this version (porter host)')
    up.add_argument('--device', default='', help='adb serial (default: the configured device, else the only one)')
    up.add_argument('--folder', action='append', default=[], metavar='TITLEID=FOLDER', help="a game's build folder (see porter host --folder); may repeat")
    up.add_argument('--json', action='store_true')
    tvp = sub.add_parser('tv', help='TV mode for a port on the device, without the game files: with a display plugged in, the game shows there in the display\'s own mode and the device is the gamepad')
    tvp.add_argument('mode', choices=('on', 'off', 'status'))
    tvp.add_argument('--package', default='', help='the app (default: the only ported game installed)'); tvp.add_argument('--device', default='', help='adb serial'); tvp.add_argument('--json', action='store_true')
    dv = sub.add_parser('drivers', help="a port's Vulkan drivers (up to three, the pause menu's Driver tab), changed without the game files: the saves and data stay")
    dvs = dv.add_subparsers(dest='drivers_cmd', required=True)
    d1 = dvs.add_parser('list', help="the drivers the app carries and its default"); d2 = dvs.add_parser('file', help='what a driver file (.zip or .so) holds')
    d3 = dvs.add_parser('set', help='the app with exactly these drivers')
    d2.add_argument('path')
    d3.add_argument('--keep', action='append', default=[], metavar='NAME=LIB', help='a driver the app has (its library name), under NAME in the menu')
    d3.add_argument('--add', action='append', default=[], metavar='NAME=FILE', help='a driver file (.zip or .so) added under NAME')
    d3.add_argument('--spec', default='', metavar='JSON_FILE', help='instead of --keep/--add: {"drivers": [{"name", "lib" | "file"}], "default": index or -1} (the GUI writes it)')
    d3.add_argument('--default', default='', help="the default: a driver's NAME, or system (the device's own); default: the first driver")
    d3.add_argument('--jobs', type=int, default=os.cpu_count() or 8)
    for d in (d1, d2, d3):
        d.add_argument('--json', action='store_true')
        if d is not d2: d.add_argument('--package', default='', help='the app (default: the only ported game installed)'); d.add_argument('--device', default='', help='adb serial')
    return ap


def _romfs_at(p, when=''):   # install's --romfs-at / --romfs-push (porter/install.py)
    p.add_argument('--romfs-at', default=None, metavar='FOLDER',
                   help=when + 'read the game\'s RomFS from this folder on the device (e.g. /sdcard/Games/<game>/romfs, a dump another app also reads, or a folder on the SD card) '
                        'instead of a copy in the app\'s files folder: the folder must hold exactly the pack\'s RomFS (names and sizes, and the content of a sample), the app is given All files access, '
                        'and a copy an earlier install left in the files folder is deleted. Later installs keep the folder; "app" moves the RomFS back into the files folder')
    p.add_argument('--romfs-push', action='store_true', help='with --romfs-at: push the pack\'s RomFS into that folder first (an empty folder, or one of this game; nothing there is deleted)')


def _print_json(obj): print(json.dumps(obj, ensure_ascii=False, indent=2))


def cmd_doctor(a):
    from porter import toolchain
    rows = toolchain.checks(keys=a.keys)
    if a.json: _print_json([r.as_dict() for r in rows])
    else:
        for r in rows: print(f'{"ok " if r.ok else ("!! " if r.required else "-- ")} {r.name:15} {r.detail}' + (f'\n{"":19}→ {r.fix}' if r.fix and not r.ok else ''))
    return 0 if all(r.ok or not r.required for r in rows) else 1


def cmd_profiles(a):
    from porter import profiles
    rows = profiles.all_entries(android_only=not a.all)
    if a.json: _print_json([r.as_dict() for r in rows]); return 0
    for r in rows: print(f'{r.id}  {r.status:12} {r.name}' + (f'  ({r.tested})' if r.tested else ''))
    return 0


def cmd_inspect(a):
    import contextlib
    from porter import pipeline
    from porter.upstream import BuildError
    try:
        with contextlib.redirect_stdout(sys.stderr if a.json else sys.stdout):
            info = pipeline.inspect(a.folder, a.keys)   # keep JSON stdout one document for the GUI
    except BuildError as e:
        if a.json: _print_json({'error': str(e)})
        else: print(e, file=sys.stderr)
        return 2
    if a.json: _print_json(info); return 0 if info['supported'] else 2
    print(f'{info["title_id"]}  {info.get("name", "")}\n  base: {info["base"]}')
    for u in info['updates']: print(f'  update {u["version"]}: {u["file"]}')
    for d in info['dlc']: print(f'  DLC {d["title_id"]}: {d["file"]}')
    if info.get('pack'): print(f'  packs {info["pack"]} (versions in the folder: {", ".join(info["versions"])})')
    if info['android']: print(f'  Android: {info["android"]["status"]}' + (f', tested on {info["android"]["tested"]}' if info['android']['tested'] else ''))
    if info['reason']: print(f'  {info["reason"]}')
    if info.get('experimental'): print('  porter port --experimental tries it')
    return 0 if info['supported'] else 2


def _with_progress(mode, fn):
    from porter.upstream import BuildError, PROG, nsp
    PROG.mode = nsp.progress_mode(mode)
    environ = dict(os.environ)
    try:
        fn(); return 0
    except BuildError as e:
        PROG.close(ok=False); PROG.say(f'[RED] {e}'); return 1
    except KeyboardInterrupt:
        PROG.close(ok=False); PROG.say('[RED] interrupted'); return 130
    except Exception as e:
        PROG.close(ok=False)
        if PROG.mode == 'json': PROG.say(f'[RED] {type(e).__name__}: {e}')
        raise
    finally:
        PROG.close(ok=False)
        for k in os.environ.keys() - environ.keys(): del os.environ[k]
        os.environ.update(environ)


def cmd_port(a):
    from porter import pipeline
    offset = a.vercode_offset
    if offset is None:
        env = os.environ.get('NX2A_VERCODE_OFFSET', '').strip() or '0'
        try: offset = int(env)
        except ValueError: print(f'NX2A_VERCODE_OFFSET is not a number: {env}', file=sys.stderr); return 2
    from porter import presets
    try: presets.get(a.preset)
    except ValueError as e: print(e, file=sys.stderr); return 2
    if (a.romfs_at is not None or a.romfs_push) and not a.install: print('--romfs-at and --romfs-push are install options: add --install, or run porter install after the port', file=sys.stderr); return 2
    from porter import install
    from porter.upstream import BuildError
    try: install.romfs_target(a.romfs_at)   # a folder the app cannot read fails now, not after the shaders
    except BuildError as e: print(e, file=sys.stderr); return 2
    opts = pipeline.Options(folder=Path(a.folder), keys=Path(a.keys) if a.keys else None, firmware=Path(a.firmware) if a.firmware else None, out=Path(a.out) if a.out else None, version=a.version, language=a.language,
                            app_name=a.app_name, install=a.install, device=a.device, replace_signer=a.replace_signer, debug=a.debug, experimental=a.experimental, package=a.package, fps60=a.fps60, touch=a.touch, mt_replay=a.mt_replay, vulkan_driver=a.vulkan_driver, shared_font=a.shared_font,
                            vercode_offset=offset, alias_headroom=a.alias_headroom, romfs_at=a.romfs_at, romfs_push=a.romfs_push, external_display=a.external_display, preset=a.preset, gpu_turbo=a.gpu_turbo, jobs=a.jobs)
    return _with_progress(a.progress, lambda: pipeline.emit_result(pipeline.Port(opts).run()))


def cmd_install(a):
    from porter import config, datapack, install, toolchain
    from porter.upstream import BuildError, PROG
    def go():
        data = Path(a.data).resolve()
        apk = Path(a.apk) if a.apk else data.with_name(data.name.removesuffix('-data') + '.apk')
        PROG.plan(1)
        cfg = config.load()
        install.install(apk, data, toolchain.find_adb(cfg), a.device or cfg.get('device'), replace_signer=a.replace_signer, romfs_at=a.romfs_at, romfs_push=a.romfs_push)
    return _with_progress(a.progress, go)


def cmd_devices(a):
    from porter import config, toolchain
    from porter.adb import Adb, AdbError
    exe = toolchain.find_adb()
    if not exe: print('adb not found', file=sys.stderr); return 1
    try: rows = Adb(exe).devices()
    except AdbError as e: print(e, file=sys.stderr); return 1
    if a.json: _print_json([{'serial': s, 'state': st, 'info': d} for s, st, d in rows]); return 0
    for s, st, d in rows: print(f'{s}\t{st}\t{d}')
    if not rows: print('no device')
    return 0


def cmd_tools(a):
    from porter import fetch
    from porter.upstream import BuildError
    names = [{'ndk': 'Android NDK', 'dotnet': '.NET SDK', 'adb': 'adb'}[n.strip()] for n in a.only.split(',') if n.strip()] or None
    if a.download:
        def go():
            items = fetch.plan(names)
            if not items: fetch.PROG.say('nothing to download: every tool is there'); return
            for it in items: fetch.PROG.say(f'{it.name} {it.version} ({it.size / 2**20:,.0f} MB) from {it.url}, license: {it.license}')
            fetch.download(items)
        return _with_progress(a.progress, go)
    try: items = fetch.plan(names)
    except (BuildError, OSError) as e: print(f'cannot read the download lists: {e}', file=sys.stderr); return 1
    if a.json: _print_json([it.as_dict() for it in items]); return 0
    for it in items: print(f'{it.name:12} {it.version:16} {it.size / 2**20:8,.0f} MB  {it.url}\n{"":12} license: {it.license}')
    print('porter tools --download fetches them' if items else 'nothing to download: every tool is there')
    return 0


def cmd_config(a):
    from porter import config
    if a.key is None:
        for k, v in config.load().items(): print(f'{k:9} {v or "-":40}  {config.KEYS[k]}')
        print(f'({config.path()})'); return 0
    if a.value is None: print(config.load().get(a.key, '')); return 0
    try: config.set_value(a.key, a.value)
    except KeyError as e: print(e.args[0], file=sys.stderr); return 1
    return 0


def cmd_saves(a):
    import contextlib
    from porter import config, saves, toolchain
    from porter.upstream import BuildError
    try:
        with contextlib.redirect_stdout(sys.stderr if a.json else sys.stdout):   # with --json, stdout is the one JSON document (the GUI parses it whole)
            cfg = config.load(); adb = saves.connect(toolchain.find_adb(cfg), a.device or cfg.get('device'))
            if a.saves_cmd == 'apps': out = saves.apps(adb)
            else:
                pkg = saves.pick_app(adb, a.package)
                if a.saves_cmd == 'list': out = saves.listing(adb, pkg)
                elif a.saves_cmd == 'export': out = {'package': pkg, 'folder': str(saves.export(adb, pkg, Path(a.dest), a.name))}
                else: out = dict(saves.import_(adb, pkg, Path(a.src), a.name), package=pkg)
    except BuildError as e:
        if a.json: _print_json({'error': str(e)})
        else: print(e, file=sys.stderr)
        return 1
    if a.json: _print_json(out)
    elif a.saves_cmd == 'apps': print('\n'.join(out) or 'no ported game is installed')
    elif a.saves_cmd == 'list':
        import time
        for r in out: print(f'{time.strftime("%Y-%m-%d %H:%M", time.localtime(r["time"]))}  {r["name"]:32} {r["files"]:5} files {r["bytes"] / 2**20:9.2f} MB' + ('  (+ device save)' if r['device'] else ''))
        if not out: print(f'no save folders on the device ({saves.saves_folder(pkg)})')
    return 0


def cmd_driver(a):   # porter driver and porter host: the installed APK rebuilt without the game files
    import contextlib
    from porter import config, driver, host, saves, toolchain, tv
    from porter.upstream import BuildError
    try:
        with contextlib.redirect_stdout(sys.stderr if a.json else sys.stdout):   # with --json, stdout is the one JSON document
            cfg = config.load(); adb = saves.connect(toolchain.find_adb(cfg), a.device or cfg.get('device'))
            if a.cmd == 'driver': out = driver.swap(adb, saves.pick_app(adb, a.package), None if a.system else a.library)
            elif a.cmd == 'tv':
                pkg = saves.pick_app(adb, a.package); out = tv.status(adb, pkg) if a.mode == 'status' else tv.set_mode(adb, pkg, a.mode == 'on')
            elif a.cmd == 'host': out = host.update(adb, saves.pick_app(adb, a.package), a.jobs, folder=a.folder, force=a.force)
            else:   # updates
                folders = {k.upper(): v for k, v in (f.split('=', 1) for f in a.folder if '=' in f)}
                out = {'version': host.checkout_version(), 'games': []}
                for pkg in saves.apps(adb):
                    try:
                        r = host.inspect(adb, pkg)
                        if r.get('title_id') in folders: r = host.inspect(adb, pkg, folders[r['title_id']])
                    except BuildError as e: r = {'package': pkg, 'name': pkg, 'status': 'port', 'reason': str(e)}
                    try: r['tv'] = tv.status(adb, pkg)['tv']
                    except BuildError: r['tv'] = False
                    out['games'].append(r)
    except BuildError as e:
        if a.json: _print_json({'error': str(e)})
        else: print(e, file=sys.stderr)
        return 1
    if a.json: _print_json(out)
    elif a.cmd == 'tv': print(f'{out["package"]}: TV mode ' + ('on' if out['tv'] else 'off'))
    elif a.cmd == 'updates':
        print(f'this version: {out["version"]}')
        for g in out['games']:
            print(f'{g["name"][:34]:34} {g.get("display", ""):9} {STATUS_WORD.get(g["status"], g["status"]):18} {g.get("reason", "")}')
        if not out['games']: print('no ported game is installed')
    return 0


def cmd_drivers(a):   # porter drivers list / file / set
    import contextlib
    from porter import config, driver, saves, toolchain
    from porter.upstream import BuildError
    try:
        with contextlib.redirect_stdout(sys.stderr if a.json else sys.stdout):
            if a.drivers_cmd == 'file': out = driver.read_driver(a.path)
            else:
                cfg = config.load(); adb = saves.connect(toolchain.find_adb(cfg), a.device or cfg.get('device')); pkg = saves.pick_app(adb, a.package)
                if a.drivers_cmd == 'list': out = driver.current(adb, pkg)
                else:
                    if a.spec:
                        spec = json.loads(Path(a.spec).read_text(encoding='utf-8')); ds, dflt = spec.get('drivers', []), int(spec.get('default', -1))
                    else:
                        def pair(s, what):
                            if '=' not in s: raise BuildError(f'{what} takes NAME=VALUE: {s}')
                            return s.split('=', 1)
                        ds = [{'name': n, 'lib': v} for n, v in (pair(s, '--keep') for s in a.keep)] + [{'name': n, 'file': v} for n, v in (pair(s, '--add') for s in a.add)]
                        names = [driver.menu_name(d['name']) for d in ds]
                        if a.default.lower() == 'system': dflt = -1
                        elif a.default: dflt = names.index(driver.menu_name(a.default)) if driver.menu_name(a.default) in names else -2
                        else: dflt = 0 if ds else -1
                        if dflt == -2: raise BuildError(f'--default {a.default}: not one of the drivers ({", ".join(names)}) or system')
                    out = driver.apply(adb, pkg, ds, dflt, a.jobs)
    except (BuildError, ValueError, OSError) as e:
        if a.json: _print_json({'error': str(e)})
        else: print(e, file=sys.stderr)
        return 1
    if a.json: _print_json(out)
    elif a.drivers_cmd == 'file': print(f'{out["name"]}: {out["lib"]}' + (f' ({out["description"]})' if out['description'] else ''))
    else:
        for d in out['drivers']: print(f'{"*" if d["lib"] == out["default"] else " "} {d["name"]:22} {d["lib"]}')
        if not out['default']: print('* System (the device\'s own driver)')
        if a.drivers_cmd == 'list' and not out['loader']: print('(no driver loader in the app yet: setting a driver builds and adds it)')
    return 0


STATUS_WORD = {'current': 'up to date', 'update': 'update available', 'risky': 'rewriter changed', 'folder': 'needs its folder', 'port': 'port again'}


def main(argv):
    if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8', errors='replace')   # game names and progress bars on a Windows console
    a = _parser().parse_args(argv)
    return {'doctor': cmd_doctor, 'profiles': cmd_profiles, 'inspect': cmd_inspect, 'port': cmd_port, 'install': cmd_install, 'devices': cmd_devices, 'tools': cmd_tools, 'config': cmd_config, 'saves': cmd_saves, 'driver': cmd_driver, 'host': cmd_driver, 'updates': cmd_driver, 'tv': cmd_driver, 'drivers': cmd_drivers}[a.cmd](a)
