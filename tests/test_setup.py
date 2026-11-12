"""Installer integrity tests. No external downloads or executables are needed."""
from pathlib import Path
import hashlib
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import setup_windows as setup


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
    def tearDown(self):
        self.temp.cleanup()

    def spec(self,name,data):
        return {'filename':name,'sha256':hashlib.sha256(data).hexdigest(),'url':'https://example.invalid/'+name}

    def test_verified_cache_is_used_without_network(self):
        data=b'verified content';spec=self.spec('item',data)
        (self.root/'item').write_bytes(data)
        with patch.object(setup,'fetch',side_effect=AssertionError('Network must not be used')):
            self.assertEqual(setup.download(spec,self.root).read_bytes(),data)

    def test_bad_checksum_is_not_published(self):
        with patch.object(setup,'fetch',side_effect=lambda url,path:path.write_bytes(b'incorrect')):
            with self.assertRaisesRegex(RuntimeError,'Checksum mismatch'):
                setup.download(self.spec('item',b'expected'),self.root)
        self.assertFalse((self.root/'item').exists())
        self.assertFalse((self.root/'item.partial').exists())

    def prepare_archive(self,member):
        cache=self.root/'.downloads';cache.mkdir()
        bundle=cache/'bundle.zip'
        with zipfile.ZipFile(bundle,'w') as archive:
            archive.writestr(member,b'fixture, never executed')
        program=b'program fixture';(cache/'program.single').write_bytes(program)
        manifest={'pdfsizeopt_windows':self.spec('bundle.zip',bundle.read_bytes()),
                  'pdfsizeopt_program':self.spec('program.single',program)}
        (self.root/'dependencies.json').write_text(json.dumps(manifest),encoding='utf-8')

    def test_archive_cannot_escape_bin(self):
        self.prepare_archive('../escaped')
        with self.assertRaisesRegex(RuntimeError,'Unsafe path'):
            setup.install_optimizer(self.root)
        self.assertFalse((self.root/'escaped').exists())

    def test_expected_archive_layout_is_installed(self):
        self.prepare_archive('pdfsizeopt.exe')
        setup.install_optimizer(self.root)
        self.assertTrue((self.root/'bin'/'pdfsizeopt.exe').is_file())
        self.assertEqual((self.root/'bin'/'pdfsizeopt.single').read_bytes(),b'program fixture')

if __name__=='__main__':unittest.main()
