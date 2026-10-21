"""Verify optional Lookin injection with real arm64 Mach-O inputs."""
import hashlib
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

@unittest.skipUnless(shutil.which('xcrun'), 'requires Xcode')
class LookinTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shared = tempfile.TemporaryDirectory(prefix='md lookin sdk ')
        root = Path(cls.shared.name)
        sdk = subprocess.check_output(['xcrun', '--sdk', 'iphoneos', '--show-sdk-path'], text=True).strip()
        source = root / 'source.c'
        source.write_text('int marker(void) { return 1; }\n')
        cls.framework = root / 'LookinServer.framework'
        cls.framework.mkdir()
        (cls.framework / 'Info.plist').write_bytes(plistlib.dumps({'CFBundleShortVersionString': '1.2.8', 'CFBundleExecutable': 'LookinServer'}))
        subprocess.run(['xcrun', 'clang', '-target', 'arm64-apple-ios15.0', '-isysroot', sdk,
                        '-dynamiclib', str(source), '-o', str(cls.framework / 'LookinServer')], check=True)
        source.write_text('int main(void) { return 0; }\n')
        cls.main = root / 'Demo'
        subprocess.run(['xcrun', 'clang', '-target', 'arm64-apple-ios15.0', '-isysroot', sdk,
                        '-Wl,-headerpad,4096', str(source), '-o', str(cls.main)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.shared.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='md lookin app ')
        self.addCleanup(self.temp.cleanup)
        self.app = Path(self.temp.name) / 'Built App.app'
        self.app.mkdir()
        self.original = {'CFBundleExecutable': 'Demo'}
        (self.app / 'Info.plist').write_bytes(plistlib.dumps(self.original))
        shutil.copy2(self.main, self.app / 'Demo')
        self.env = dict(os.environ, MONKEYDEV_PATH=str(ROOT), BUILD_APP_PATH=str(self.app), APP_BINARY='Demo',
                        MONKEYPARSER=str(ROOT / 'bin/monkeyparser'), CONFIGURATION='Debug', PLATFORM_NAME='iphoneos',
                        MONKEYDEV_UI_INSPECTOR='Lookin', MONKEYDEV_LOOKIN_SDK=str(self.framework))

    def integrate(self, **settings):
        script = 'panic() { shift; echo "$*" >&2; exit 1; }; source "$1"; integrateLookin'
        return subprocess.run(['/bin/bash', '-c', script, 'test', str(ROOT / 'Tools/lookin.sh')],
                              env={**self.env, **settings}, capture_output=True, text=True)

    def test_off_and_release_do_not_require_sdk_or_modify_product(self):
        before = (self.app / 'Demo').read_bytes()
        for config in ({'MONKEYDEV_UI_INSPECTOR': 'None'}, {'MONKEYDEV_UI_INSPECTOR': 'Reveal'}, {'CONFIGURATION': 'Release'}):
            result = self.integrate(MONKEYDEV_LOOKIN_SDK='/nonexistent', **config)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((self.app / 'Frameworks').exists())
            self.assertEqual((self.app / 'Demo').read_bytes(), before)

    def test_missing_custom_sdk_reports_error(self):
        result = self.integrate(MONKEYDEV_LOOKIN_SDK='/nonexistent')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Reinstall/update MonkeyDev or set MONKEYDEV_LOOKIN_SDK', result.stderr)

    def test_real_injection_preserves_sdk_and_signs_framework(self):
        sdk = ROOT / 'Librarys/Lookin/LookinServer.framework'
        before = hashlib.sha256((sdk / 'LookinServer').read_bytes()).hexdigest()
        result = self.integrate(MONKEYDEV_LOOKIN_SDK='')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        framework = self.app / 'Frameworks/LookinServer.framework'
        linked = subprocess.check_output(['otool', '-L', str(self.app / 'Demo')], text=True)
        self.assertIn('@executable_path/Frameworks/LookinServer.framework/LookinServer', linked)
        self.assertEqual(hashlib.sha256((sdk / 'LookinServer').read_bytes()).hexdigest(), before)
        self.assertEqual(plistlib.loads((self.app / 'Info.plist').read_bytes()), self.original)
        subprocess.run(['codesign', '-f', '-s', '-', str(framework)], check=True, capture_output=True)
        subprocess.run(['codesign', '--verify', '--strict', str(framework)], check=True, capture_output=True)

    def test_input_owned_framework_is_not_overwritten(self):
        destination = self.app / 'Frameworks/LookinServer.framework'
        destination.mkdir(parents=True)
        (destination / 'user.txt').write_text('user-owned')
        result = self.integrate()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((destination / 'user.txt').read_text(), 'user-owned')

    def test_pack_switching_inspector_and_release_clears_previous_injection(self):
        root = Path(self.temp.name) / 'Project'
        (root / 'Test/TargetApp').mkdir(parents=True)
        shutil.copy2(ROOT / 'Resource/TargetApp.app/Info.plist', root / 'Test/Info.plist')
        products = root / 'Build Products'
        products.mkdir()
        env = dict(self.env, MonkeyDevPath=str(ROOT), SRCROOT=str(root), PROJECT_DIR=str(root),
                   TARGET_NAME='Test', BUILT_PRODUCTS_DIR=str(products), TARGET_BUILD_DIR=str(products),
                   FULL_PRODUCT_NAME='Test.app', MONKEYDEV_MINIMAL='YES', MONKEYDEV_INSERT_DYLIB='NO',
                   MONKEYDEV_TARGET_APP='Optional', MONKEYDEV_INPUT_APP='', MONKEYDEV_CLASS_DUMP='NO',
                   MONKEYDEV_RESTORE_SYMBOL='NO', PRODUCT_BUNDLE_IDENTIFIER='com.example.lookin',
                   MONKEYDEV_REVEAL='YES')
        # The new selector must override legacy Reveal and must not retain a prior Lookin load command.
        for inspector, configuration, present in [('Lookin', 'Debug', True), ('None', 'Debug', False),
                                                   ('Lookin', 'Debug', True), ('Lookin', 'Release', False)]:
            with self.subTest(inspector=inspector, configuration=configuration):
                env.update(MONKEYDEV_UI_INSPECTOR=inspector, CONFIGURATION=configuration)
                result = subprocess.run(['/bin/bash', str(ROOT / 'Tools/pack.sh')], env=env,
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                app = products / 'Test.app'
                self.assertEqual((app / 'Frameworks/LookinServer.framework').exists(), present)
                self.assertFalse((app / 'Frameworks/RevealServer.framework').exists())
                binary = plistlib.loads((app / 'Info.plist').read_bytes())['CFBundleExecutable']
                loads = subprocess.check_output(['otool', '-L', str(app / binary)], text=True)
                self.assertEqual('LookinServer.framework' in loads, present)

    def test_static_sdk_is_rejected(self):
        sdk = Path(self.temp.name) / 'Static.framework'
        shutil.copytree(self.framework, sdk)
        shutil.copy2(self.main, sdk / 'LookinServer')
        result = self.integrate(MONKEYDEV_LOOKIN_SDK=str(sdk))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('dynamic framework', result.stderr)

    def test_obsolete_sdk_is_rejected(self):
        sdk = Path(self.temp.name) / 'Old.framework'
        shutil.copytree(self.framework, sdk)
        (sdk / 'Info.plist').write_bytes(plistlib.dumps({'CFBundleShortVersionString': '1.0.5'}))
        result = self.integrate(MONKEYDEV_LOOKIN_SDK=str(sdk))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('1.0.6', result.stderr)

if __name__ == '__main__': unittest.main()
