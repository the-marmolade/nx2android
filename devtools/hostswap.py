#!/usr/bin/env python3
# hostswap.py: an installed port's APK again with another libdmhost.so (a host built by nxnative/dm/android/build.py --game <id> --lib --release), signed again
# with the player's key (the same signer: it installs over the app and keeps its saves), so a host change is tried on the device without the game's files or a new
# port. Every other entry (the drivers, the hooks, the assets) is kept. --env KEY=VALUE sets a row of the app's env.txt (KEY= alone removes it).
# Usage: python devtools/hostswap.py <package> <libdmhost.so> [--env KEY=VALUE ...] [--serial S]
import argparse, subprocess, sys, tempfile, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / 'nxnative/dm/android/apk'))
import json
from apksign import build_zip, sign_v2   # noqa: E402
from porter import paths, datapack         # noqa: E402

LIB = 'lib/arm64-v8a/libdmhost.so'


def adb(serial, *args, **kw):
    return subprocess.run(['adb'] + (['-s', serial] if serial else []) + list(args), check=True, capture_output=True, text=kw.get('text', True), errors='replace')


def main():
    p = argparse.ArgumentParser(description="an installed port's APK with another libdmhost.so, signed again with the same key")
    p.add_argument('package'); p.add_argument('lib'); p.add_argument('--env', action='append', default=[], metavar='KEY=VALUE'); p.add_argument('--serial')
    a = p.parse_args()
    lib = Path(a.lib).read_bytes()
    with tempfile.TemporaryDirectory(prefix='nx2a_hostswap_') as t:
        src, out = Path(t) / 'installed.apk', Path(t) / 'host.apk'
        path = next(ln[8:].strip() for ln in adb(a.serial, 'shell', f'pm path {a.package}').stdout.splitlines() if ln.startswith('package:'))
        adb(a.serial, 'pull', path, str(src))
        z = zipfile.ZipFile(src)
        if LIB not in z.namelist(): raise SystemExit(f'{a.package}: not an nx2android port (no {LIB})')
        entries = [(i.filename, lib if i.filename == LIB else z.read(i), 16384 if i.filename.startswith('lib/') else 4) for i in z.infolist()]
        kj = json.load(open(paths.signing_key())); k = {n: int(v) for n, v in kj.items() if n != 'cert'}; crt = bytes.fromhex(kj['cert'])
        zz, cd, eocd = build_zip(entries); out.write_bytes(sign_v2(zz, cd, eocd, k, crt))
        adb(a.serial, 'shell', f'am force-stop {a.package}')
        adb(a.serial, 'install', '-r', str(out))
        print(f'{a.package}: installed with {a.lib} ({len(lib) // 1024} KB)')
        if a.env:
            env = f'{datapack.files_folder(a.package)}/env.txt'; local = Path(t) / 'env.txt'
            rows = adb(a.serial, 'shell', f'cat {env}').stdout.splitlines()
            for kv in a.env:
                key, _, val = kv.partition('=')
                rows = [r for r in rows if not r.startswith(key + '=')] + ([f'{key}={val}'] if val else [])
                print(f'env.txt: {key}={val}' if val else f'env.txt: {key} removed')
            local.write_text('\n'.join(rows) + '\n', encoding='utf-8', newline='\n')
            adb(a.serial, 'push', str(local), env)


if __name__ == '__main__': sys.exit(main())
