"""Export only isolated build products; preserve unrelated files and prior exports."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]

class CreateIPATests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='monkeydev-export-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.products = self.root / 'Build Products'
        self.products.mkdir()
        self.script = self.products / 'createIPA.command'
        shutil.copy2(ROOT / 'bin/createIPA.command', self.script)
        self.previous = self.products / 'Target.ipa'
        self.previous.write_bytes(b'previous export')
        self.payload = self.products / 'Payload/user-file'
        self.payload.parent.mkdir()
        self.payload.write_text('keep user directory')
        self.sibling = self.root / 'Build/keep.txt'
        self.sibling.parent.mkdir()
        self.sibling.write_text('keep sibling directory')

    def run_export(self, **settings):
        return subprocess.run(['/bin/bash', str(self.script)], cwd=self.root,
                              env={**os.environ, **settings}, capture_output=True, text=True, timeout=20)

    def assert_preserved(self):
        self.assertEqual(self.sibling.read_text(), 'keep sibling directory')
        self.assertEqual(self.payload.read_text(), 'keep user directory')
        self.assertFalse(list(self.products.glob('.monkeydev-export.*')))

    def test_spaces_nested_apps_and_repeated_export(self):
        app = self.products / 'Test App.app'
        app.mkdir()
        executable = app / 'Test App'
        executable.write_text('executable fixture')
        executable.chmod(0o755)
        nested = app / 'Watch/Nested.app/Info.plist'
        nested.parent.mkdir(parents=True)
        nested.write_text('embedded app fixture')
        (app / 'old.txt').write_text('old resource')
        for version in ['one', 'two']:
            if version == 'two':
                (app / 'old.txt').unlink()
            (app / 'version.txt').write_text(version)
            result = self.run_export()
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            with zipfile.ZipFile(self.previous) as archive:
                self.assertEqual(archive.read('Payload/Test App.app/version.txt').decode(), version)
                self.assertIn('Payload/Test App.app/Watch/Nested.app/Info.plist', archive.namelist())
                self.assertNotIn('Payload/user-file', archive.namelist())
                self.assertEqual('Payload/Test App.app/old.txt' in archive.namelist(), version == 'one')
                mode = archive.getinfo('Payload/Test App.app/Test App').external_attr >> 16
                self.assertTrue(mode & 0o111)
            self.assert_preserved()

    def test_missing_or_multiple_apps_keep_previous_export(self):
        for count in [0, 2]:
            with self.subTest(app_count=count):
                for index in range(count):
                    (self.products / f'App {index}.app').mkdir()
                result = self.run_export()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('Expected exactly one App', result.stderr)
                self.assertEqual(self.previous.read_bytes(), b'previous export')
                self.assert_preserved()

    def test_copy_failure_keeps_previous_export(self):
        (self.products / 'Test App.app').mkdir()
        programs = self.root / 'programs'
        programs.mkdir()
        stub = programs / 'cp'
        stub.write_text('#!/bin/bash\nexit 1\n')
        stub.chmod(0o755)
        result = self.run_export(PATH=str(programs) + ':' + os.environ['PATH'])
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.previous.read_bytes(), b'previous export')
        self.assert_preserved()

if __name__ == '__main__':
    unittest.main()
