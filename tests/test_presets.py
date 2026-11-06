"""Device presets (porter/presets.py): rows under the game profile's own, and the CLI's check of the name."""
import unittest

from porter import presets


class PresetTests(unittest.TestCase):
    def test_thor_adds_its_rows(self):
        p = presets.get('thor')
        self.assertEqual(presets.env_rows(p, []), ['DM_PIN_REPLAY=prime'])
        self.assertEqual(p.settings, {'overlay': '0'})

    def test_profile_value_kept(self):
        rows = presets.env_rows(presets.get('Thor'), ['DM_NVN_ASYNC=1', 'DM_PIN_REPLAY=big'])
        self.assertEqual(rows, [])   # the profile's big stands; the preset adds nothing over it

    def test_comment_rows_ignored(self):
        self.assertEqual(presets.env_rows(presets.get('thor'), ['# DM_PIN_REPLAY=big was slower']), ['DM_PIN_REPLAY=prime'])

    def test_gpu_turbo_is_the_players_choice(self):
        self.assertEqual(presets.env_rows(None, ['DM_GPU_TURBO=0'], gpu_turbo=True), ['DM_GPU_TURBO=1'])
        self.assertEqual(presets.env_rows(None, []), [])

    def test_unknown_preset(self):
        self.assertIsNone(presets.get(''))
        with self.assertRaises(ValueError): presets.get('odin9')


if __name__ == '__main__':
    unittest.main()
