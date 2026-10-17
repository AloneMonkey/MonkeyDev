"""Integration checks against the user's installed ~/theos Logos processor."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
LOGOS = Path.home() / 'theos/bin/logos.pl'
SOURCE = '''%config(generator=internal);
#import <Foundation/Foundation.h>
%hook NSObject
- (NSString *)description { return %orig; }
%end
'''

@unittest.skipUnless(LOGOS.is_file(), 'requires ~/theos')
class LogosTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='monkeydev logos ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'Test.xcodeproj').mkdir()
        (self.root / 'Test.xcodeproj/project.pbxproj').touch()
        self.env = dict(os.environ, ACTION='build', PROJECT_DIR=str(self.root),
                        PROJECT_FILE_PATH=str(self.root / 'Test.xcodeproj'),
                        PATH='/usr/bin:/bin')

    def run_processor(self):
        return subprocess.run(['/bin/bash', str(ROOT / 'bin/md'), '--xcbp-logos'],
                              env=self.env, capture_output=True, text=True)

    def test_real_processor_handles_spaces_and_both_languages(self):
        for suffix in ['x', 'xm']:
            (self.root / ('hook with space.' + suffix)).write_text(SOURCE)
        skipped = self.root / 'TargetApp'
        skipped.mkdir()
        (skipped / 'bad.xm').write_text('%hook')
        result = self.run_processor()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for suffix in ['m', 'mm']:
            generated = (self.root / ('hook with space.' + suffix)).read_text()
            self.assertIn('method_setImplementation', generated)
            self.assertNotIn('MSHookMessageEx', generated)
        self.assertFalse((skipped / 'bad.mm').exists())

    def test_failure_preserves_previous_generated_file(self):
        source = self.root / 'bad.xm'
        output = self.root / 'bad.mm'
        output.write_text('previous valid output')
        source.write_text('%config(generator=NonexistentMonkeyDevBackend);\n%hook NSObject\n%end\n')
        os.utime(output, (1, 1))
        result = self.run_processor()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(output.read_text(), 'previous valid output')

    def test_symlinked_sources_generate_beside_the_links(self):
        with tempfile.TemporaryDirectory(prefix='monkeydev shared ') as shared:
            for suffix in ['x', 'xm']:
                source = Path(shared) / ('Shared.' + suffix)
                source.write_text(SOURCE)
                (self.root / ('linked hook.' + suffix)).symlink_to(source)
            result = self.run_processor()
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            for suffix in ['m', 'mm']:
                output = self.root / ('linked hook.' + suffix)
                self.assertIn('method_setImplementation', output.read_text())
                self.assertFalse((Path(shared) / ('Shared.' + suffix)).exists())

    def test_missing_source_directory_fails(self):
        self.env['PROJECT_DIR'] = str(self.root / 'missing')
        result = self.run_processor()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Failed to scan Logos sources', result.stderr)

    @unittest.skipIf(os.geteuid() == 0, 'requires non-root filesystem permissions')
    def test_failed_scan_does_not_replace_previous_output(self):
        (self.root / 'Hook.xm').write_text(SOURCE)
        output = self.root / 'Hook.mm'
        output.write_text('previous valid output')
        unreadable = self.root / 'Private Sources'
        unreadable.mkdir()
        unreadable.chmod(0)
        try:
            result = self.run_processor()
        finally:
            unreadable.chmod(0o700)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Failed to scan Logos sources', result.stderr)
        self.assertEqual(output.read_text(), 'previous valid output')

    def test_newer_placeholder_is_generated_and_unchanged_output_is_not_touched(self):
        source = self.root / 'new.xm'
        output = self.root / 'new.mm'
        source.write_text(SOURCE)
        output.write_text('// Created after the Logos input by the Xcode template\n')
        os.utime(source, (1, 1))
        result = self.run_processor()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('method_setImplementation', output.read_text())
        timestamp = output.stat().st_mtime_ns
        result = self.run_processor()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(output.stat().st_mtime_ns, timestamp)

if __name__ == '__main__':
    unittest.main()
