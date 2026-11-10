# TV mode for a port already on the device (python -m porter tv on|off|status), without the game's files: the installed APK gets the external-display activity
# (nxnative/dm/android/java/org/nx2a, compiled here with a JDK and the Android SDK's platform and d8) and its manifest names it, by
# nxnative/dm/android/apk/apkdriver.py --external-dex, signed with the player's key (the same signer: it installs over the app, its saves stay). With the activity, a
# display plugged into the device (HDMI or DisplayPort over USB-C, never a second built-in screen: ExternalDisplay.pick) shows the game in its own best mode, and the
# device's screen becomes the gamepad; with none connected the game runs on the device as before. off puts Android's NativeActivity back.
import json, os, re, shlex, subprocess, sys, tempfile
from pathlib import Path

from porter import paths, toolchain
from porter.adb import AdbError
from porter.driver import installed_apk
from porter.paths import DM
from porter.upstream import BuildError, say

EXTERNAL = 'org.nx2a.ExternalActivity'


def tools():
    """(javac, android.jar, d8) for the activity, or BuildError naming what is missing"""
    javac = toolchain.find_javac()
    roots = toolchain._sdk_roots()
    platforms = [p for r in roots for p in (r / 'platforms').glob('android-*/android.jar')]
    d8s = [p for r in roots for p in (r / 'build-tools').glob('*/d8' + ('.bat' if os.name == 'nt' else ''))]
    def version(p): return tuple(int(x) for x in re.findall(r'\d+', p.parent.name))
    missing = [w for w, have in (('a JDK (javac)', javac), ('an Android SDK platform (platforms/android-*)', platforms), ('Android SDK build-tools (d8)', d8s)) if not have]
    if missing: raise BuildError('TV mode needs ' + ', '.join(missing) + ': install them, or set JAVA_HOME / ANDROID_HOME')
    return javac, max(platforms, key=version), max(d8s, key=version)


def build_dex(out):
    """classes.dex of the external-display activity, in out (a folder). → its path"""
    javac, platform, d8 = tools()
    out = Path(out).resolve(); classes, dex = out / 'classes', out / 'dex'; classes.mkdir(parents=True); dex.mkdir()   # (absolute: d8.bat runs from its own folder)
    env = dict(os.environ)   # d8 is a Java program: it runs with the JDK the compiler came from
    if Path(javac).parent.name == 'bin': env['JAVA_HOME'] = str(Path(javac).parent.parent)
    sources = sorted((DM / 'android/java/org/nx2a').glob('*.java'))
    def run(what, argv):
        r = subprocess.run(argv, capture_output=True, text=True, errors='replace', env=env)
        if r.returncode: raise BuildError(f'TV mode: {what}: ' + ((r.stderr.strip() or r.stdout.strip()).splitlines() or ['no output'])[-1])
    run('the activity did not compile', [javac, '-encoding', 'UTF-8', '-source', '8', '-target', '8', '-Xlint:-options', '-classpath', str(platform), '-d', str(classes), *map(str, sources)])
    run('d8 failed', [str(d8), '--min-api', '29', '--lib', str(platform), '--output', str(dex), *map(str, sorted(classes.rglob('*.class')))])   # (the classes javac just wrote)
    if not (dex / 'classes.dex').is_file(): raise BuildError('TV mode: d8 made no classes.dex')
    return dex / 'classes.dex'


def status(adb, package):
    """{'package', 'tv': the app has the external-display activity}"""
    out = adb.shell(f'cmd package resolve-activity --brief {shlex.quote(package)}', check=False)
    return {'package': package, 'tv': EXTERNAL in out}


def set_mode(adb, package, on):
    """package's APK with the external-display activity (on) or without it. → {'package', 'tv'}"""
    with tempfile.TemporaryDirectory(prefix='nx2a_tv_') as t:
        t = Path(t); src, out = t / 'installed.apk', t / 'tv.apk'
        change = ['--external-dex', str(build_dex(t / 'java'))] if on else ['--native-activity']
        say(f'{package}: pulling the installed APK')
        adb.run('pull', installed_apk(adb, package), src, timeout=600)
        r = subprocess.run([sys.executable, str(DM / 'android/apk/apkdriver.py'), str(src), str(out), str(paths.signing_key()), *change], capture_output=True, text=True, errors='replace')
        if r.returncode: raise BuildError((r.stderr.strip() or r.stdout.strip()).splitlines()[-1])
        res = json.loads(r.stdout.strip().splitlines()[-1])
        adb.shell(f'am force-stop {shlex.quote(package)}', check=False)
        say(f'{package}: installing the APK ' + ('with the external-display activity' if on else 'with Android\'s own activity'))
        try: adb.install(out, package)
        except AdbError as e: raise BuildError(str(e)) from e
    say(f'{package}: TV mode ' + ('on: with a display plugged in, the game shows there and the device is the gamepad' if on else 'off') + '; the game\'s data on the device is unchanged')
    return {'package': package, 'tv': res['activity'] == EXTERNAL}
