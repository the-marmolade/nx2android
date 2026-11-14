# The launcher's game library (gui/launcher.py, `porter library`): every game the tool knows (the game profiles: the Catalog), the games found in the player's folders
# (the Library: dumps grouped by title ID, in any folder below the ones chosen), the ports already made in the output folder (<App>-data/nx2a-data.json beside <App>.apk),
# and a rating of each game for a device model (its android.tsv's tested line and notes name the devices it was tried on).
import hashlib, json, os, re, shutil, subprocess, tempfile
from pathlib import Path

from porter import config, dumps
from porter.paths import DM, user_dir

ART = 'art'                    # <user dir>/art/<title ID>.jpg: each owned game's own icon, from its control data (nx_extract --control); index.json: {title ID: {'key', 'name', 'icon'}}

CACHE = 'library-cache.json'   # {path: [size, mtime, title ID or None]}: reading a ticket opens the file, so a rescan only opens new or changed files
MAX_DEPTH = 4                  # folders below a library folder that are scanned

# Device models adb reports (getprop ro.product.model, spaces as _) → the name the notes use and the GPU. A model not here is matched by its own name only
DEVICES = {
    'AYN_Thor': ('AYN Thor', 'Adreno 740'),
    'AYN_Odin2': ('Odin 2', 'Adreno 740'),
    'AYN_Odin2_Portal': ('Odin 2', 'Adreno 740'),
    'TB322FC': ('Legion Y700', 'Adreno 830'),
    'TB321FU': ('Legion Y700', 'Adreno 730'),
}


def folders():
    """The library folders (config 'library': paths joined with ;)"""
    return [f for f in (config.load().get('library') or '').split(';') if f.strip()]


def set_folders(fs):
    seen, out = set(), []
    for f in fs:
        k = os.path.normcase(os.path.abspath(f))
        if f.strip() and k not in seen: seen.add(k); out.append(f)
    config.set_value('library', ';'.join(out))
    return out


def _load_cache():
    try: return json.loads((user_dir() / CACHE).read_text(encoding='utf-8'))
    except (OSError, ValueError): return {}


def _save_cache(c):
    p = user_dir() / CACHE; tmp = p.with_suffix('.tmp')
    try: tmp.write_text(json.dumps(c), encoding='utf-8'); tmp.replace(p)
    except OSError: pass


def clean_name(stem):
    """A display name from a dump's file name: 'Game Name [0100…][v0] (US).nsp' → 'Game Name'"""
    s = re.sub(r'\[[^\]]*\]|\([^)]*\)|\{[^}]*\}', ' ', stem)
    s = re.sub(r'[_.]+', ' ', s)
    return re.sub(r'\s+', ' ', s).strip(' -') or stem


def scan(roots, keys=None):
    """The games in roots and the folders below them (MAX_DEPTH): {application title ID (str): {'folders': [folder with its base game first], 'base': file, 'updates': [versions],
    'dlc': n, 'bytes': n, 'files': n, 'port_ready': whether porter can port it from its folder (one game per folder, the base there), 'file_name': base game's name}}"""
    from porter.upstream import nsp
    hk = nsp.header_key(keys) if keys else None
    cache, used = _load_cache(), {}
    per_dir = {}   # folder → {app: {'base', 'updates', 'dlc', 'bytes', 'files'}}
    for root in roots:
        root = Path(root)
        if not root.is_dir(): continue
        base_depth = len(root.parts)
        for d, subs, files in os.walk(root):
            if len(Path(d).parts) - base_depth >= MAX_DEPTH: subs[:] = []
            subs[:] = [s for s in subs if not s.startswith('.') and not s.endswith(('-data', '_build'))]   # a port's data pack, a build folder (its tmp/dumps are the game's own, unpacked)
            for fn in files:
                if fn.lower().rsplit('.', 1)[-1] not in dumps.EXTS: continue
                p = Path(d) / fn
                try: st = p.stat()
                except OSError: continue
                if not st.st_size: continue
                key = str(p); c = cache.get(key)
                if c and c[0] == st.st_size and c[1] == int(st.st_mtime): tid = c[2]
                else:
                    try: tid = nsp.title_of(p, hk)
                    except (OSError, ValueError, Exception): tid = None
                used[key] = [st.st_size, int(st.st_mtime), tid]
                if tid is None: continue
                low = tid & 0xFFF
                app = tid if low == 0 else tid & ~0xFFF if low == 0x800 else (tid & ~0xFFF) - 0x1000
                fam = per_dir.setdefault(d, {}).setdefault(app, {'base': None, 'updates': [], 'dlc': 0, 'bytes': 0, 'files': 0})
                fam['bytes'] += st.st_size; fam['files'] += 1
                if low == 0: fam['base'] = p
                elif low == 0x800: fam['updates'].append(nsp.version_of(p))
                else: fam['dlc'] += 1
    _save_cache(used)
    games = {}
    for d, apps in per_dir.items():
        for app, fam in apps.items():
            tid = f'{app:016X}'
            g = games.setdefault(tid, {'folders': [], 'base': None, 'updates': [], 'dlc': 0, 'bytes': 0, 'files': 0, 'port_ready': False, 'file_name': ''})
            g['bytes'] += fam['bytes']; g['files'] += fam['files']; g['dlc'] += fam['dlc']
            g['updates'] += [v for v in fam['updates'] if v is not None]
            if fam['base'] and not g['base']:
                g['base'] = str(fam['base']); g['file_name'] = clean_name(fam['base'].stem); g['folders'].insert(0, d)
                g['port_ready'] = len(apps) == 1
            else: g['folders'].append(d)
    for g in games.values(): g['updates'] = sorted(set(g['updates']))
    return games


def ports(out):
    """The ports made in the output folder: {title ID: {'data', 'apk', 'version', 'display', 'made', 'package'}}, the newest of a title"""
    res = {}
    if not out or not Path(out).is_dir(): return res
    for man in Path(out).glob('*-data/nx2a-data.json'):
        try: m = json.loads(man.read_text(encoding='utf-8'))
        except (OSError, ValueError): continue
        data = man.parent; apk = data.with_name(data.name[:-len('-data')] + '.apk')
        tid = (m.get('title_id') or '').upper()
        if not tid or not apk.is_file(): continue
        r = {'data': str(data), 'apk': str(apk), 'version': m.get('version', ''), 'display': m.get('display', ''), 'made': m.get('made', ''), 'package': m.get('package', '')}
        if tid not in res or r['made'] > res[tid]['made']: res[tid] = r
    return res


def notes(profile_dir):
    """The comment lines at the top of a profile's android.tsv (what it was tested on and how, its known issues), as one text"""
    p = Path(profile_dir) / 'android.tsv'
    try: lines = p.read_text(encoding='utf-8').splitlines()
    except OSError: return ''
    out = []
    for ln in lines:
        if not ln.startswith('#'): break
        out.append(ln[1:].strip())
    return ' '.join(out[1:] if out and 'keys in docs' in out[0] else out)


def _art_index():
    try: return json.loads((user_dir() / ART / 'index.json').read_text(encoding='utf-8'))
    except (OSError, ValueError): return {}


def _base_key(path):
    st = Path(path).stat(); return f'{Path(path).name}|{st.st_size}|{int(st.st_mtime)}'


def nx_extract(say=print):
    """nx_extract built once into <user dir>/tools/nx_extract/ (again when its source changes): the art fetch reads only the control data with it. Needs the .NET SDK"""
    from porter import toolchain
    from porter.upstream import nsp
    src = DM / 'tools/nx_extract'
    fp = hashlib.sha256(b''.join((src / f).read_bytes() for f in ('Program.cs', 'nx_extract.csproj'))).hexdigest()[:16]
    work = user_dir(); exe = work / 'tools/nx_extract' / ('nx_extract.exe' if os.name == 'nt' else 'nx_extract'); stamp = exe.parent / 'source.key'
    dotnet = toolchain.find_dotnet()
    if not dotnet: raise RuntimeError('no .NET SDK: install the tools first (Setup & tools)')
    env = dict(os.environ, PATH=os.pathsep.join([str(dotnet.parent), os.environ.get('PATH', '')]), DOTNET_ROOT=str(toolchain.dotnet_root(dotnet)), DOTNET_CLI_TELEMETRY_OPTOUT='1')
    if not (exe.is_file() and stamp.is_file() and stamp.read_text().strip() == fp):
        say('building nx_extract (once)')
        logs = work / 'logs'; logs.mkdir(parents=True, exist_ok=True)
        os.environ['PATH'] = env['PATH']   # Windows finds dotnet by this process's PATH
        exe = nsp.build_nx_extract(DM.parent, work, logs, env)
        stamp.write_text(fp)
    return exe, env


def fetch_art(roots=None, say=print):
    """The icon and the name from each owned game's control data, for the games not fetched yet (or whose base dump changed). → {'fetched', 'failed', 'skipped'}"""
    from porter.upstream import nacp
    keys = config.load().get('keys')
    if not keys or not Path(keys).is_file(): raise RuntimeError('no prod.keys: the game files cannot be read without them')
    owned = scan(folders() if roots is None else roots, keys)
    d = user_dir() / ART; d.mkdir(parents=True, exist_ok=True)
    idx = _art_index(); todo = []
    for tid, g in owned.items():
        if not g['base']: continue
        k = _base_key(g['base'])
        if idx.get(tid, {}).get('key') != k: todo.append((tid, g['base'], k))
    res = {'fetched': 0, 'failed': [], 'skipped': len(owned) - len(todo)}
    if not todo: return res
    exe, env = nx_extract(say)
    for tid, base, k in todo:
        with tempfile.TemporaryDirectory(prefix='nx2a_art_') as t:
            try: r = subprocess.run([str(exe), keys, '--control', base, t], capture_output=True, text=True, errors='replace', timeout=120, env=env)
            except (OSError, subprocess.TimeoutExpired) as e: res['failed'].append(f'{tid}: {e}'); continue
            nac, ico = Path(t) / 'control.nacp', Path(t) / 'icon.jpg'
            if r.returncode or not nac.is_file():
                res['failed'].append(f'{tid}: ' + ((r.stderr or r.stdout).strip().splitlines() or ['nx_extract failed'])[-1])
                idx[tid] = {'key': k, 'name': '', 'icon': ''}   # not tried again until the dump changes
                continue
            entry = {'key': k, 'name': nacp.name(nac) or '', 'icon': ''}
            if ico.is_file(): shutil.copyfile(ico, d / f'{tid}.jpg'); entry['icon'] = f'{tid}.jpg'
            idx[tid] = entry; res['fetched'] += 1
            say(f'{tid}: {entry["name"] or "?"}' + ('' if entry['icon'] else ' (no icon)'))
    tmp = d / 'index.json.tmp'; tmp.write_text(json.dumps(idx, indent=1, ensure_ascii=False), encoding='utf-8'); tmp.replace(d / 'index.json')
    return res


def device_name(model):
    return DEVICES.get(model, (model.replace('_', ' '), ''))[0] if model else ''


def rating(status, android, tested, note, model):
    """(rating, why) of a game for a device model: Verified (playable, tried on this model), Playable (playable, tried on another), In progress (wip: parts missing),
    Untested (boots or experimental on Android), Experimental (an iOS profile only), Unsupported (no profile)"""
    if status is None: return 'Unsupported', 'No game profile: an experimental port guesses one and may not start'
    if not android: return 'Experimental', 'Has an iOS profile; not tuned for Android yet'
    name, gpu = DEVICES.get(model, (model.replace('_', ' ') if model else '', ''))
    text = f'{tested} {note}'.lower()
    on_this = bool(name) and name.lower() in text
    same_gpu = bool(gpu) and gpu.lower() in text
    where = f'tested on {tested}' if tested else 'tested on another device'
    if status == 'playable':
        if on_this: return 'Verified', f'Tested on {name}'
        return 'Playable', where + (f' (same GPU as your {name})' if same_gpu else '')
    if status == 'wip': return 'In progress', 'Plays, but parts are missing' + (f'; tried on {name}' if on_this else '')
    return 'Untested', f'Status: {status}' + (f'; tried on {name}' if on_this else '')


def library(model='', roots=None):
    """Everything the launcher shows: {'folders', 'out', 'games': [one per title: catalog fields, 'owned', 'scan', 'ported', 'rating', 'why', 'notes']}"""
    from porter.upstream import android_profile
    cfg = config.load()
    roots = folders() if roots is None else roots
    owned = scan(roots, cfg.get('keys') or None)
    made = ports(cfg.get('out'))
    idx, art = _art_index(), user_dir() / ART
    icon = lambda tid: str(art / idx[tid]['icon']) if idx.get(tid, {}).get('icon') and (art / idx[tid]['icon']).is_file() else ''
    games, seen = [], set()
    for g, p in android_profile.all_profiles():
        tid = g.id.upper(); seen.add(tid)
        status = p.status if p else 'ios only'
        note = notes(g.dir) if p else ''
        r, why = rating(status, bool(p), p.tested if p else '', note, model)
        games.append({'id': tid, 'name': g.get('name', g.id), 'profile': True, 'android': bool(p), 'status': status, 'tested': p.tested if p else '',
                      'package': p.package if p else f'org.nx2a.t{g.id.lower()}', 'owned': tid in owned, 'scan': owned.get(tid), 'ported': made.get(tid),
                      'rating': r, 'why': why, 'notes': note, 'icon': icon(tid) if tid in owned else ''})
    for tid, s in owned.items():   # found in the folders without a profile: the control data's name, else the file's
        if tid in seen: continue
        r, why = rating(None, False, '', '', model)
        games.append({'id': tid, 'name': idx.get(tid, {}).get('name') or s['file_name'] or f'Unknown title · {tid}', 'profile': False, 'android': False, 'status': 'unsupported',
                      'tested': '', 'package': f'org.nx2a.t{tid.lower()}', 'owned': True, 'scan': s, 'ported': made.get(tid), 'rating': r, 'why': why, 'notes': '', 'icon': icon(tid)})
    missing = sum(1 for tid, s in owned.items() if s['base'] and idx.get(tid, {}).get('key') != _base_key(s['base']))
    games.sort(key=lambda x: x['name'].lower())
    return {'folders': roots, 'out': cfg.get('out', ''), 'device': device_name(model), 'art_missing': missing, 'games': games}
