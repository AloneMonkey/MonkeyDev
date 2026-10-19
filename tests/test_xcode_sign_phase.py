"""Exercise the existing MonkeyApp Run Script with Xcode build-setting variables."""
import hashlib
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "Tools/pack.sh"


@unittest.skipUnless(Path("/usr/bin/codesign").exists(), "requires Xcode on macOS")
class XcodeSigningPhaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="monkeydev-xcode-phase-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.app = self.root / "Built Products/Monkey Example.app"
        self.framework = self.app / "Frameworks/Helper.framework"
        self.framework.mkdir(parents=True)
        sdk = subprocess.check_output(["xcrun", "--sdk", "iphoneos", "--show-sdk-path"], text=True).strip()
        compiler = ["xcrun", "clang", "-target", "arm64-apple-ios15.0", "-isysroot", sdk]
        source = self.root / "source.c"
        source.write_text("int main(void) { return 0; }\n")
        subprocess.run([*compiler, str(source), "-o", str(self.app / "Example")], check=True)
        subprocess.run([*compiler, "-dynamiclib", str(source), "-o", str(self.framework / "Helper")], check=True)
        self.dylib = self.app / "Frameworks/lib Example.dylib"
        subprocess.run([*compiler, "-dynamiclib", str(source), "-o", str(self.dylib)], check=True)
        for bundle, executable, kind in [(self.app, "Example", "APPL"), (self.framework, "Helper", "FMWK")]:
            (bundle / "Info.plist").write_bytes(plistlib.dumps({
                "CFBundleExecutable": executable, "CFBundlePackageType": kind,
                "CFBundleIdentifier": "com.example." + executable, "CFBundleVersion": "1",
            }))
        self.main_hash = hashlib.sha256((self.app / "Example").read_bytes()).hexdigest()

    def run_phase(self, **settings):
        env = {**os.environ, "MonkeyDevPath": str(SCRIPT.parent.parent), "TARGET_BUILD_DIR": str(self.app.parent),
               "FULL_PRODUCT_NAME": self.app.name, "TARGET_NAME": "Monkey Example",
               "SRCROOT": str(self.root), "EXPANDED_CODE_SIGN_IDENTITY": "-",
               "CODE_SIGNING_ALLOWED": "YES", "MONKEYDEV_INSERT_DYLIB": "YES", **settings}
        return subprocess.run(["/bin/bash", str(SCRIPT), "codesign"], env=env,
                              capture_output=True, text=True, timeout=20)

    def test_embedded_signatures_and_main_app_left_for_xcode(self):
        result = self.run_phase()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for item in (self.dylib, self.framework):
            subprocess.run(["codesign", "--verify", "--strict", str(item)], check=True)
        self.assertEqual(hashlib.sha256((self.app / "Example").read_bytes()).hexdigest(), self.main_hash)
        self.assertFalse((self.app / "_CodeSignature").exists())

    def test_repacked_main_and_framework_are_resigned_with_xcode_entitlements(self):
        temp = self.root / 'Target Temp'
        temp.mkdir()
        entitlements = temp / (self.app.name + '.xcent')
        entitlements.write_bytes(plistlib.dumps({'get-task-allow': True}))
        settings = dict(TARGET_TEMP_DIR=str(temp), FULL_PRODUCT_NAME=self.app.name)
        unsigned_main = (self.app / 'Example').read_bytes()
        unsigned_helper = (self.framework / 'Helper').read_bytes()
        for _ in range(2):
            # Repack replaces executable and framework, invalidating old signatures.
            (self.app / 'Example').write_bytes(unsigned_main)
            (self.framework / 'Helper').write_bytes(unsigned_helper)
            info = plistlib.loads((self.app / 'Info.plist').read_bytes())
            info['UISupportedDevices'] = ['iPhone1,1']
            (self.app / 'Info.plist').write_bytes(plistlib.dumps(info))
            result = self.run_phase(**settings)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn('UISupportedDevices', plistlib.loads((self.app / 'Info.plist').read_bytes()))
            subprocess.run(['codesign', '--verify', '--deep', '--strict', str(self.app)], check=True)
            decoded = subprocess.check_output(['codesign', '-d', '--entitlements', ':-', str(self.app)], stderr=subprocess.DEVNULL)
            self.assertEqual(plistlib.loads(decoded), {'get-task-allow': True})
        entitlements.unlink()
        result = self.run_phase(**settings)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Xcode-generated signing entitlements not found', result.stderr)

    def test_embedded_code_outside_frameworks_is_resigned(self):
        root_library = self.app / 'ADManager.dylib'
        extensionless_library = self.app / 'Libraries/Helper Library'
        extensionless_library.parent.mkdir()
        nested_framework = self.app / 'Helpers/Outer.framework/Frameworks/Inner.framework'
        nested_framework.parent.mkdir(parents=True)
        outer_framework = nested_framework.parent.parent
        shutil.copy2(self.framework / 'Helper', outer_framework / 'Outer')
        shutil.copytree(self.framework, nested_framework)
        (nested_framework / 'Helper').rename(nested_framework / 'Inner')
        for bundle, name in [(outer_framework, 'Outer'), (nested_framework, 'Inner')]:
            (bundle / 'Info.plist').write_bytes(plistlib.dumps({
                'CFBundleExecutable': name, 'CFBundlePackageType': 'FMWK',
                'CFBundleIdentifier': 'com.example.' + name, 'CFBundleVersion': '1',
            }))
        for library in (root_library, extensionless_library):
            shutil.copy2(self.dylib, library)
        # No Frameworks directory: this used to skip embedded signing entirely.
        shutil.rmtree(self.app / 'Frameworks')
        resource = self.app / 'resource.txt'
        resource.write_text('not executable code')
        original_main = (self.app / 'Example').read_bytes()
        original_resource = resource.read_bytes()
        for _ in range(2):
            result = self.run_phase()
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            for item in (root_library, extensionless_library, nested_framework, outer_framework):
                subprocess.run(['codesign', '--verify', '--deep', '--strict', str(item)], check=True)
                entitlements = subprocess.check_output(
                    ['codesign', '-d', '--entitlements', ':-', str(item)], stderr=subprocess.DEVNULL)
                self.assertFalse(entitlements.strip())
            self.assertEqual((self.app / 'Example').read_bytes(), original_main)
            self.assertEqual(resource.read_bytes(), original_resource)

    def test_missing_identity_fails(self):
        result = self.run_phase(EXPANDED_CODE_SIGN_IDENTITY="")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Signing & Capabilities", result.stderr)

    def test_signing_disabled_by_xcode(self):
        before = self.dylib.read_bytes()
        result = self.run_phase(CODE_SIGNING_ALLOWED="NO", EXPANDED_CODE_SIGN_IDENTITY="")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.dylib.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
