"""Run CaptainHook's internal backend on Apple Silicon, without Substrate."""
import os
from pathlib import Path
import platform
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

@unittest.skipUnless(platform.system() == 'Darwin' and platform.machine() == 'arm64', 'requires Apple Silicon')
class CaptainHookTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='monkeydev-captainhook-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def compile(self, platform='macosx', extra=()):
        sdk = subprocess.check_output(['xcrun', '--sdk', platform, '--show-sdk-path'], text=True).strip()
        target = 'arm64-apple-macos14.0' if platform == 'macosx' else 'arm64-apple-ios15.0'
        output = self.root / ('fixture' if platform == 'macosx' else 'libFixture.dylib')
        flags = [] if platform == 'macosx' else ['-dynamiclib', '-DMD_CAPTAIN_DEVICE_TEST=1']
        result = subprocess.run(['xcrun', 'clang', '-target', target, '-isysroot', sdk, '-fobjc-arc', '-O0',
                        '-I', str(ROOT / 'include'), *flags, str(ROOT / 'tests/captainhook_fixture.m'),
                        *extra, '-framework', 'Foundation', '-o', str(output)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        dependencies = subprocess.check_output(['otool', '-L', str(output)], text=True)
        self.assertNotIn('substrate', dependencies.lower())
        undefined = subprocess.check_output(['nm', '-u', str(output)], text=True)
        self.assertNotIn('MSHook', undefined)
        return output

    def test_internal_runtime_and_abi(self):
        output = self.compile()
        result = subprocess.run([str(output)], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('[MonkeyDevCaptainHook] PASS', result.stderr)

    def test_iphoneos_arm64_library(self):
        self.compile('iphoneos')

    def test_logos_internal_chain(self):
        logos = Path.home() / 'theos/bin/logos.pl'
        if not logos.exists(): self.skipTest('requires ~/theos')
        generated = self.root / 'chain.m'
        result = subprocess.run([str(logos), str(ROOT / 'tests/captainhook_chain.xm')], capture_output=True, text=True, check=True)
        generated.write_text(result.stdout)
        output = self.compile(extra=('-DMD_CAPTAIN_LOGOS_TEST=1', str(generated), '-I', str(Path.home() / 'theos/vendor/include')))
        result = subprocess.run([str(output)], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('[MonkeyDevCaptainHook] PASS', result.stderr)

    def test_legacy_copy_skips_substrate_but_keeps_other_files(self):
        frameworks = self.root / 'Frameworks'
        destination = self.root / 'Built Frameworks'
        frameworks.mkdir(); destination.mkdir()
        (frameworks / 'libsubstrate.dylib').write_text('retired')
        (frameworks / 'libcycript.dylib').write_text('retired')
        (frameworks / 'libcycript.cy').write_text('retired')
        (frameworks / 'Helper.dylib').write_text('optional')
        definitions = (ROOT / 'Tools/pack.sh').read_text().split('\nif [[ "$1" == "codesign" ]]; then')[0]
        env = dict(os.environ, MonkeyDevPath=str(self.root), SRCROOT=str(self.root), TARGET_NAME='Example')
        result = subprocess.run(['/bin/bash', '-c', definitions + '\ncopyOptionalFrameworks "$1"',
                                 'copy-test', str(destination)], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((destination / 'libsubstrate.dylib').exists())
        self.assertFalse((destination / 'libcycript.dylib').exists())
        self.assertFalse((destination / 'libcycript.cy').exists())
        self.assertEqual((destination / 'Helper.dylib').read_text(), 'optional')

if __name__ == '__main__': unittest.main()
