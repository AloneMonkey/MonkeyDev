"""Build and inspect real arm64 Logos/Substrate packages without a device."""
import io
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
THEOS = Path.home() / 'theos'

@unittest.skipUnless(shutil.which('xcrun') and Path('/opt/homebrew/bin/ldid').exists(), 'requires Xcode and ldid')
class TweakPackageTests(unittest.TestCase):
    def run_cmd(self, args, **kwargs):
        result = subprocess.run(args, capture_output=True, text=True, **kwargs)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def build(self, work, scheme, no_install=False, tool=False, captain=False):
        if not tool and not captain and not (THEOS / 'bin/logos.pl').exists():
            self.skipTest('Logos tweak requires Theos')
        project = work / 'Project With Spaces'
        package = project / 'Tweak/Package'
        (package / 'DEBIAN').mkdir(parents=True)
        resources = package / 'Library/MobileSubstrate/DynamicLibraries'
        if not tool:
            resources.mkdir(parents=True)
            (resources / 'Tweak.plist').write_text('<plist version="1.0"><dict/></plist>')
        original = 'Package: com.monkeydev.test\nName: Test\nVersion: 1.0\nArchitecture: iphoneos-arm\nDescription: Fixture\nMaintainer: Test\n'
        if not tool:
            original += 'Depends: mobilesubstrate\n'
        (package / 'DEBIAN/control').write_text(original)
        products = work / 'Build With Spaces'
        products.mkdir()
        sdk = self.run_cmd(['xcrun', '--sdk', 'iphoneos', '--show-sdk-path']).strip()
        libdir = THEOS / 'vendor/lib'
        prefix = ''
        flags = []
        if scheme == 'rootless':
            libdir /= 'iphone/rootless'
            prefix = '/var/jb'
            flags = ['-Wl,-rpath,/var/jb/usr/lib', '-Wl,-rpath,/var/jb/Library/Frameworks',
                     '-Wl,-rpath,@loader_path/.jbroot/usr/lib',
                     '-Wl,-rpath,@loader_path/.jbroot/Library/Frameworks']
        elif scheme == 'roothide':
            libdir = ROOT / 'Librarys/roothide'
            flags = ['-Wl,-rpath,@loader_path/.jbroot/usr/lib',
                     '-Wl,-rpath,@loader_path/.jbroot/Library/Frameworks']
        install_name = ('@loader_path/.jbroot/Library/MobileSubstrate/DynamicLibraries/libTweak.dylib'
                        if scheme == 'roothide' else '@rpath/libTweak.dylib')
        binary = products / ('CommandFixture' if tool else 'libTweak.dylib')
        if tool:
            source = work / 'main.c'
            source.write_text('#include <stdio.h>\nint main(void) { puts("Hello, World!"); return 0; }\n')
            self.run_cmd(['xcrun', 'clang', '-target', 'arm64-apple-ios15.0', '-isysroot', sdk,
                          str(source), '-o', str(binary)])
        elif captain:
            self.run_cmd(['xcrun', 'clang', '-target', 'arm64-apple-ios15.0', '-isysroot', sdk,
                          '-dynamiclib', '-fobjc-arc', '-DMD_CAPTAIN_DEVICE_TEST', '-I' + str(ROOT / 'include'),
                          '-framework', 'Foundation', '-Wl,-install_name,' + install_name,
                          str(ROOT / 'tests/captainhook_fixture.m'), '-o', str(binary)])
        else:
            source = work / 'Hook.xm'
            source.write_text('%config(generator=MobileSubstrate);\n#import <Foundation/Foundation.h>\n%hook NSObject\n- (NSString *)description {\n    return %orig;\n}\n%end\n')
            generated = work / 'Hook.mm'
            generated.write_text(self.run_cmd([str(THEOS / 'bin/logos.pl'), str(source)]))
            self.run_cmd(['xcrun', 'clang++', '-target', 'arm64-apple-ios15.0', '-isysroot', sdk,
                          '-dynamiclib', '-fobjc-arc', '-I' + str(THEOS / 'vendor/include'),
                          '-F' + str(THEOS / 'vendor/lib'), '-L' + str(libdir), '-lsubstrate', '-framework', 'Foundation',
                          '-Wl,-install_name,' + install_name, *flags, str(generated), '-o', str(binary)])
        env = dict(os.environ, ACTION='build', PROJECT_DIR=str(project), PROJECT_NAME='Tweak',
                   TARGET_NAME='Tweak', TARGET_BUILD_DIR=str(products), BUILT_PRODUCTS_DIR=str(products),
                   EXECUTABLE_PATH=binary.name, SHALLOW_BUNDLE='NO', INSTALL_MODE_FLAG='0755',
                   INSTALL_PATH=prefix + '/Library/MobileSubstrate/DynamicLibraries',
                   MONKEYDEV_PACKAGE_SCHEME=scheme, PLATFORM_NAME='iphoneos', CONFIGURATION='Debug',
                   VALIDATE_PRODUCT='NO', MonkeyDevDeviceIP='unused', MonkeyDevDevicePort='22',
                   MonkeyDevCopyOnBuild='NO', MonkeyDevBuildPackageOnAnyBuild='YES',
                   MonkeyDevInstallOnAnyBuild='NO', MonkeyDevInstallOnProfiling='NO',
                   MonkeyDevDevicePassword='', CODE_SIGN_ENTITLEMENTS='')
        if tool:
            env.update(PRODUCT_TYPE='com.apple.product-type.tool', INSTALL_PATH=prefix + '/usr/bin')
        if no_install:
            # None must suppress installation even when an old override enables it.
            env.update(MonkeyDevAuthentication='None', MonkeyDevInstallOnAnyBuild='YES',
                       MonkeyDevInstallOnProfiling='YES', CONFIGURATION='Release', VALIDATE_PRODUCT='YES')
        output = self.run_cmd(['/bin/bash', str(ROOT / 'bin/md'), '--xcbp'], env=env)
        if no_install:
            self.assertIn('installation disabled (SSH Authentication: None)', output)
        self.assertEqual((package / 'DEBIAN/control').read_text(), original)
        self.assertFalse((package / 'var').exists())
        self.assertFalse((resources / binary.name).exists())
        debs = list((project / 'Packages').glob('*.deb'))
        self.assertEqual(len(debs), 1)
        members = self.run_cmd(['ar', '-t', str(debs[0])]).splitlines()
        self.assertEqual(members, ['debian-binary', 'control.tar.gz', 'data.tar.gz'])
        def archive(member):
            data = subprocess.check_output(['ar', '-p', str(debs[0]), member])
            return tarfile.open(fileobj=io.BytesIO(data), mode='r:gz')
        with archive('data.tar.gz') as data:
            names = {n.removeprefix('./') for n in data.getnames()}
            dest = prefix.lstrip('/') + '/Library/MobileSubstrate/DynamicLibraries/' if prefix else 'Library/MobileSubstrate/DynamicLibraries/'
            if tool:
                dest = prefix.lstrip('/') + '/usr/bin/' if prefix else 'usr/bin/'
            self.assertIn(dest + binary.name, names)
            if not tool:
                self.assertIn(dest + 'Tweak.plist', names)
            else:
                self.assertFalse(any(n.endswith(('Tweak.plist', '0xdeadfa11')) for n in names))
            self.assertNotIn('DEBIAN/control', names)
            self.assertFalse(any(n.endswith('.tbd') or n.endswith('/libsubstrate.dylib') for n in names))
            for member in data.getmembers():
                self.assertEqual((member.uid, member.gid), (0, 0))
                self.assertEqual(member.pax_headers, {})
            if prefix:
                self.assertNotIn('Library/MobileSubstrate/DynamicLibraries/' + binary.name, names)
        with archive('control.tar.gz') as control:
            metadata = control.extractfile('control').read().decode()
            arch = 'iphoneos-arm64' if prefix else 'iphoneos-arm'
            if scheme == 'roothide':
                arch = 'iphoneos-arm64e'
            self.assertIn('Architecture: ' + arch + '\n', metadata)
        linked = self.run_cmd(['otool', '-L', str(binary)])
        expected = '@rpath/CydiaSubstrate.framework/CydiaSubstrate' if prefix else '/Library/Frameworks/CydiaSubstrate.framework/CydiaSubstrate'
        if scheme == 'roothide':
            expected = '@loader_path/.jbroot/usr/lib/libsubstrate.dylib'
            self.assertNotIn('/var/jb', linked)
            if not tool:
                self.assertIn(install_name, linked)
        if tool or captain:
            self.assertNotIn('libsubstrate.dylib', linked)
            self.assertNotIn('CydiaSubstrate.framework/', linked)
            undefined = self.run_cmd(['nm', '-u', str(binary)])
            self.assertNotIn('MSHook', undefined)
        else:
            self.assertIn(expected, linked)
        signature = subprocess.run(['codesign', '-dv', str(binary)], capture_output=True, text=True)
        self.assertEqual(signature.returncode, 0, signature.stderr)
        self.assertIn('CodeDirectory v=', signature.stderr)
        self.assertIn('location=embedded', signature.stderr)

    def test_rootless_real_build_and_package(self):
        with tempfile.TemporaryDirectory(prefix='md tweak rootless ') as work:
            self.build(Path(work), 'rootless')

    def test_rootful_real_build_and_package(self):
        with tempfile.TemporaryDirectory(prefix='md tweak rootful ') as work:
            self.build(Path(work), 'rootful')

    def test_roothide_real_build_and_package(self):
        with tempfile.TemporaryDirectory(prefix='md tweak roothide ') as work:
            self.build(Path(work), 'roothide')

    def test_captainhook_packages_without_substrate(self):
        for scheme in ('rootless', 'rootful', 'roothide'):
            with self.subTest(scheme=scheme), tempfile.TemporaryDirectory(prefix='md captain ') as work:
                self.build(Path(work), scheme, captain=True)

    def test_none_builds_deb_without_installing(self):
        with tempfile.TemporaryDirectory(prefix='md tweak no install ') as work:
            self.build(Path(work), 'rootless', no_install=True)

    def test_command_line_tool_packages(self):
        for scheme in ('rootless', 'rootful', 'roothide'):
            with self.subTest(scheme=scheme), tempfile.TemporaryDirectory(prefix='md command tool ') as work:
                self.build(Path(work), scheme, tool=True)

if __name__ == '__main__':
    unittest.main()
