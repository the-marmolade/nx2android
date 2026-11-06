"""The shader list (gfx_vk_exec.c vk_pipelines.bin): harvested from the device at install, kept when longer, packed as the seed list at port."""
import shutil, tempfile, unittest
from pathlib import Path

from porter import install


class FakeAdb:
    def __init__(self, data): self.data = data; self.pulled = []
    def run(self, *a, **kw):
        assert a[0] == 'pull'; self.pulled.append(a[1])
        if self.data is not None: Path(a[2]).write_bytes(self.data)
        return ''


class HarvestTests(unittest.TestCase):
    def setUp(self): self.d = Path(tempfile.mkdtemp(prefix='nx2a_seed_'))
    def tearDown(self): shutil.rmtree(self.d, ignore_errors=True)

    def test_saved_when_new(self):
        adb = FakeAdb(b'PPE1' + b'\0' * 100)
        install.harvest_pipelines(adb, '/sdcard/Android/data/org.x/files', self.d)
        self.assertEqual(adb.pulled, ['/sdcard/Android/data/org.x/files/vk_pipelines.bin'])
        self.assertEqual((self.d / 'vk_pipelines.bin').stat().st_size, 104)

    def test_longer_list_kept(self):
        (self.d / 'vk_pipelines.bin').write_bytes(b'PPE1' + b'\0' * 500)
        install.harvest_pipelines(FakeAdb(b'PPE1' + b'\0' * 100), '/f', self.d)
        self.assertEqual((self.d / 'vk_pipelines.bin').stat().st_size, 504)

    def test_not_a_list_or_missing(self):
        install.harvest_pipelines(FakeAdb(b'XXXX' + b'\0' * 100), '/f', self.d)
        install.harvest_pipelines(FakeAdb(None), '/f', self.d)
        install.harvest_pipelines(FakeAdb(b'PPE1'), '/f', self.d)   # a header only: nothing recorded yet
        self.assertFalse((self.d / 'vk_pipelines.bin').exists())


if __name__ == '__main__':
    unittest.main()
