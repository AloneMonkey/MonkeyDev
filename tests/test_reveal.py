"""Exercise optional Reveal injection with the locally installed proprietary SDK."""
import hashlib
import os
from pathlib import Path
import plistlib
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SDK = Path.home() / 'Library/Application Support/Reveal/RevealServer/RevealServer.xcframework'

@unittest.skipUnless(Path('/usr/bin/xcrun').exists(), 'requires Xcode')
class RevealTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='monkeydev-reveal-')
        self.addCleanup(self.temp.cleanup)
        self.app = Path(self.temp.name) / 'Built App.app'
        self.app.mkdir()
        self.plist = self.app / 'Info.plist'
        self.metadata = {'CFBundleExecutable': 'Demo', 'NSBonjourServices': ['_existing._tcp']}
        self.plist.write_bytes(plistlib.dumps(self.metadata))
        self.env = dict(os.environ, BUILD_APP_PATH=str(self.app), APP_BINARY='Demo',
                        MONKEYPARSER=str(ROOT / 'bin/monkeyparser'), CONFIGURATION='Debug',
                        PLATFORM_NAME='iphoneos', MONKEYDEV_REVEAL='YES', MONKEYDEV_REVEAL_SDK=str(SDK))

    def run_integration(self, **settings):
        script = 'panic() { echo "$*" >&2; exit 1; }; source "$1"; integrateReveal'
        return subprocess.run(['/bin/bash', '-c', script, 'test', str(ROOT / 'Tools/reveal.sh')],
                              env={**self.env, **settings}, capture_output=True, text=True, timeout=30)

    def test_disabled_and_release_do_not_need_sdk_or_modify_app(self):
        for settings in ({'MONKEYDEV_REVEAL': 'NO'}, {'CONFIGURATION': 'Release'}):
            result = self.run_integration(MONKEYDEV_REVEAL_SDK='/nonexistent', **settings)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse((self.app / 'Frameworks').exists())
            self.assertEqual(plistlib.loads(self.plist.read_bytes()), self.metadata)

    def test_missing_sdk_fails_when_enabled(self):
        result = self.run_integration(MONKEYDEV_REVEAL_SDK='/nonexistent')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Reveal SDK not found', result.stderr)

    def test_final_phase_restores_overwritten_discovery_metadata(self):
        framework = self.app / 'Frameworks/RevealServer.framework'
        framework.mkdir(parents=True)
        (framework / 'RevealServer').write_bytes(b'fixture')
        script = 'panic() { echo "$*" >&2; exit 1; }; source "$1"; configureRevealDiscovery; configureRevealDiscovery'
        # Simulate Xcode replacing the packaging phase's product Info.plist.
        result = subprocess.run(['/bin/bash', '-c', script, 'test', str(ROOT / 'Tools/reveal.sh')],
                                env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        info = plistlib.loads(self.plist.read_bytes())
        self.assertEqual(info['NSBonjourServices'], ['_existing._tcp', '_reveal._tcp'])
        self.assertTrue(info['NSLocalNetworkUsageDescription'])

    @unittest.skipUnless(SDK.exists(), 'requires local Reveal SDK')
    def test_real_sdk_injection_preserves_input_and_bonjour(self):
        binary = next(SDK.glob('ios-arm64*/RevealServer.framework/RevealServer'))
        digest = hashlib.sha256(binary.read_bytes()).hexdigest()
        source = self.app.parent / 'main.c'
        source.write_text('int main(void) { return 0; }\n')
        sdk = subprocess.check_output(['xcrun', '--sdk', 'iphoneos', '--show-sdk-path'], text=True).strip()
        subprocess.run(['xcrun', 'clang', '-target', 'arm64-apple-ios15.0', '-isysroot', sdk,
                        '-Wl,-headerpad,4096', str(source), '-o', str(self.app / 'Demo')], check=True)
        result = self.run_integration()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        framework = self.app / 'Frameworks/RevealServer.framework'
        arches = subprocess.check_output(['lipo', '-archs', str(framework / 'RevealServer')], text=True).strip()
        self.assertEqual(arches, 'arm64')
        loads = subprocess.check_output(['otool', '-L', str(self.app / 'Demo')], text=True)
        self.assertIn('@executable_path/Frameworks/RevealServer.framework/RevealServer', loads)
        info = plistlib.loads(self.plist.read_bytes())
        self.assertEqual(info['NSBonjourServices'], ['_existing._tcp', '_reveal._tcp'])
        self.assertTrue(info['NSLocalNetworkUsageDescription'])
        subprocess.run(['codesign', '-f', '-s', '-', str(framework)], check=True, capture_output=True)
        subprocess.run(['codesign', '--verify', '--strict', str(framework)], check=True)
        self.assertEqual(hashlib.sha256(binary.read_bytes()).hexdigest(), digest)

if __name__ == '__main__': unittest.main()
