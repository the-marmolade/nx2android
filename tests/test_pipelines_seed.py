"""The shader list (gfx_vk_exec.c vk_pipelines.bin): harvested from the device at install, merged with the PC's, packed as the seed list at port."""
import shutil, tempfile, unittest
from pathlib import Path

from porter import install


def lst(*recs, magic=b'PPE2', size=4):   # a shader list: the header (magic, record size), then the records
    return magic + size.to_bytes(4, 'little') + b''.join(r.ljust(size, b'\0') for r in recs)


class FakeAdb:
    def __init__(self, data): self.data = data; self.pulled = []
    def run(self, *a, **kw):
        assert a[0] == 'pull'; self.pulled.append(a[1])
        if self.data is not None: Path(a[2]).write_bytes(self.data)
        return ''


class HarvestTests(unittest.TestCase):
    def setUp(self): self.d = Path(tempfile.mkdtemp(prefix='nx2a_seed_'))
    def tearDown(self): shutil.rmtree(self.d, ignore_errors=True)
    def mine(self): return (self.d / 'vk_pipelines.bin').read_bytes()

    def test_saved_when_new(self):
        adb = FakeAdb(lst(b'a', b'b'))
        install.harvest_pipelines(adb, '/sdcard/Android/data/org.x/files', self.d)
        self.assertEqual(adb.pulled, ['/sdcard/Android/data/org.x/files/vk_pipelines.bin'])
        self.assertEqual(self.mine(), lst(b'a', b'b'))

    def test_lists_merged(self):   # a shorter device list from another session still adds what it reached; nothing is lost or doubled
        (self.d / 'vk_pipelines.bin').write_bytes(lst(b'a', b'b', b'c', b'd'))
        install.harvest_pipelines(FakeAdb(lst(b'c', b'e', b'e')), '/f', self.d)
        self.assertEqual(self.mine(), lst(b'a', b'b', b'c', b'd', b'e'))

    def test_nothing_new_unchanged(self):
        (self.d / 'vk_pipelines.bin').write_bytes(lst(b'a', b'b'))
        install.harvest_pipelines(FakeAdb(lst(b'b')), '/f', self.d)
        self.assertEqual(self.mine(), lst(b'a', b'b'))

    def test_new_layout_replaces(self):   # another host build's records: the old ones cannot be read by it
        (self.d / 'vk_pipelines.bin').write_bytes(lst(b'a', b'b', b'c', magic=b'PPE1'))
        install.harvest_pipelines(FakeAdb(lst(b'x', size=8)), '/f', self.d)
        self.assertEqual(self.mine(), lst(b'x', size=8))

    def test_torn_record_dropped(self):
        install.harvest_pipelines(FakeAdb(lst(b'a') + b'\1\2'), '/f', self.d)
        self.assertEqual(self.mine(), lst(b'a'))

    def test_not_a_list_or_missing(self):
        install.harvest_pipelines(FakeAdb(b'XXXX' + b'\0' * 100), '/f', self.d)
        install.harvest_pipelines(FakeAdb(None), '/f', self.d)
        install.harvest_pipelines(FakeAdb(lst()), '/f', self.d)   # a header only: nothing recorded yet
        self.assertFalse((self.d / 'vk_pipelines.bin').exists())


if __name__ == '__main__':
    unittest.main()
