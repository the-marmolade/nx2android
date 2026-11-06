# Device presets (porter port --preset): env.txt rows and settings.txt values suited to a handheld, added under the game's own profile. A preset's env row is
# left out when the game's profile (android.tsv env) already sets that key: the profile's value was chosen for that game, the preset's is only a default.
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Preset:
    name: str
    about: str
    env: dict = field(default_factory=dict)        # KEY: value for env.txt
    settings: dict = field(default_factory=dict)   # settings.txt values (front_android.c settings_load); the player's own changes in the app replace them


PRESETS = {
    # AYN Thor (Pro): Snapdragon 8 Gen 2 (1 Cortex-X3 prime core, Adreno 740), built-in controls, a 120 Hz top screen. The replay thread on the prime core
    # (DM_PIN_REPLAY, perf_android.c), as the profiles that measured it set for Snapdragon 8-series; the on-screen gamepad hidden, the controls being built in.
    'thor': Preset('thor', 'AYN Thor: replay on the prime core, on-screen gamepad hidden',
                   env={'DM_PIN_REPLAY': 'prime'}, settings={'overlay': '0'}),
}


def get(name):
    if not name: return None
    p = PRESETS.get(name.lower())
    if not p: raise ValueError(f'no device preset {name!r}; presets: {", ".join(sorted(PRESETS))}')
    return p


def env_rows(preset, profile_env, gpu_turbo=False):
    """The preset's env.txt rows the profile's env rows do not set already, then DM_GPU_TURBO=1 when asked (the player's choice: over the profile's)"""
    have = {r.split('=', 1)[0].strip() for r in profile_env if '=' in r and not r.lstrip().startswith('#')}
    rows = [f'{k}={v}' for k, v in (preset.env if preset else {}).items() if k not in have]
    return rows + (['DM_GPU_TURBO=1'] if gpu_turbo else [])
