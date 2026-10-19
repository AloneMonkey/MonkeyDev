"""Check cleanup of stale App Store extension metadata on the build copy."""
from pathlib import Path
import os
import plistlib
import shutil
import subprocess
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]

@unittest.skipUnless(Path('/usr/bin/xcrun').exists(), 'requires Xcode')
class AppMetadataTests(unittest.TestCase):
    def pack_fixture(self, root):
        target = root / 'Test'
        inputs = target / 'TargetApp'
        inputs.mkdir(parents=True)
        shutil.copy2(ROOT / 'Resource/TargetApp.app/Info.plist', target / 'Info.plist')
        products = root / 'Build Products'
        products.mkdir()
        env = dict(os.environ, MonkeyDevPath=str(ROOT), SRCROOT=str(root),
                   PROJECT_DIR=str(root), TARGET_NAME='Test', BUILT_PRODUCTS_DIR=str(products),
                   TARGET_BUILD_DIR=str(products), FULL_PRODUCT_NAME='Test.app',
                   MONKEYDEV_MINIMAL='YES', MONKEYDEV_INSERT_DYLIB='NO',
                   MONKEYDEV_TARGET_APP='Optional', MONKEYDEV_INPUT_APP='',
                   MONKEYDEV_REVEAL='NO', MONKEYDEV_CLASS_DUMP='NO',
                   MONKEYDEV_RESTORE_SYMBOL='NO', PRODUCT_BUNDLE_IDENTIFIER='com.example.repack',
                   CONFIGURATION='Debug', PLATFORM_NAME='iphoneos')
        return inputs, products, env

    def run_pack(self, env):
        return subprocess.run(['/bin/bash', str(ROOT / 'Tools/pack.sh')], env=env,
                              capture_output=True, text=True, timeout=30)

    def test_keep_original_bundle_id_can_be_toggled(self):
        with tempfile.TemporaryDirectory(prefix='monkeydev-bundle-id-') as temp:
            root = Path(temp)
            inputs, products, env = self.pack_fixture(root)
            app = inputs / 'Input.app'
            shutil.copytree(ROOT / 'Resource/TargetApp.app', app)
            plist = app / 'Info.plist'
            original = plist.read_bytes()
            original_id = plistlib.loads(original)['CFBundleIdentifier']
            self.assertNotEqual(original_id, env['PRODUCT_BUNDLE_IDENTIFIER'])
            for keep in ['YES', 'NO', 'YES']:
                env['MONKEYDEV_DEFAULT_BUNDLEID'] = keep
                result = self.run_pack(env)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                expected = original_id if keep == 'YES' else env['PRODUCT_BUNDLE_IDENTIFIER']
                for path in [products / 'Test.app/Info.plist', root / 'Test/Info.plist']:
                    self.assertEqual(plistlib.loads(path.read_bytes())['CFBundleIdentifier'], expected)
                self.assertEqual(plist.read_bytes(), original)

    def test_original_executable_name_survives_input_replacement(self):
        with tempfile.TemporaryDirectory(prefix='monkeydev-executable-') as temp:
            root = Path(temp)
            inputs, products, env = self.pack_fixture(root)
            env['EXECUTABLE_NAME'] = 'Test Custom'
            output = products / 'Test.app'
            for name in ['FirstExecutable', 'Second Executable', 'Second Executable']:
                app = inputs / 'Input.app'
                if app.exists():
                    shutil.rmtree(app)
                shutil.copytree(ROOT / 'Resource/TargetApp.app', app)
                (app / 'TargetApp').rename(app / name)
                plist = app / 'Info.plist'
                info = plistlib.loads(plist.read_bytes())
                info['CFBundleExecutable'] = name
                plist.write_bytes(plistlib.dumps(info))
                original = {str(p.relative_to(app)): p.read_bytes()
                            for p in app.rglob('*') if p.is_file()}
                result = self.run_pack(env)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                for path in [output / 'Info.plist', root / 'Test/Info.plist']:
                    self.assertEqual(plistlib.loads(path.read_bytes())['CFBundleExecutable'], name)
                self.assertTrue((output / name).is_file())
                self.assertFalse((output / 'Test Custom').exists())
                if name != 'FirstExecutable':
                    self.assertFalse((output / 'FirstExecutable').exists())
                self.assertEqual((output / name).read_bytes(), (app / name).read_bytes())
                self.assertEqual(original, {str(p.relative_to(app)): p.read_bytes()
                                            for p in app.rglob('*') if p.is_file()})

    def test_same_executable_refreshes_metadata(self):
        with tempfile.TemporaryDirectory(prefix='monkeydev-plist-refresh-') as temp:
            root = Path(temp)
            inputs, products, env = self.pack_fixture(root)
            app = inputs / 'Input.app'
            shutil.copytree(ROOT / 'Resource/TargetApp.app', app)
            source_plist = app / 'Info.plist'
            base = plistlib.loads(source_plist.read_bytes())
            for version in ['1', '2', '2']:
                info = {**base, 'CFBundleVersion': version,
                        'NSMicrophoneUsageDescription': 'Input version ' + version}
                if version == '1':
                    info['MDObsoleteKey'] = 'removed by version 2'
                source_plist.write_bytes(plistlib.dumps(info))
                original = source_plist.read_bytes()
                result = self.run_pack(env)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                for path in [products / 'Test.app/Info.plist', root / 'Test/Info.plist']:
                    output = plistlib.loads(path.read_bytes())
                    self.assertEqual(output['CFBundleVersion'], version)
                    self.assertEqual(output['NSMicrophoneUsageDescription'], 'Input version ' + version)
                    self.assertEqual(output['CFBundleExecutable'], base['CFBundleExecutable'])
                    self.assertEqual(output['CFBundleIdentifier'], env['PRODUCT_BUNDLE_IDENTIFIER'])
                    if version == '2':
                        self.assertNotIn('MDObsoleteKey', output)
                self.assertEqual(source_plist.read_bytes(), original)
            backup = root / '.monkeydev/Test-Info.plist.backup'
            self.assertEqual(plistlib.loads(backup.read_bytes())['CFBundleVersion'], '1')

    def test_first_build_preserves_edits_with_a_different_input(self):
        with tempfile.TemporaryDirectory(prefix='monkeydev-first-plist-') as temp:
            root = Path(temp)
            inputs, products, env = self.pack_fixture(root)
            app = inputs / 'Input.app'
            shutil.copytree(ROOT / 'Resource/TargetApp.app', app)
            (app / 'TargetApp').rename(app / 'OriginalExecutable')
            source = app / 'Info.plist'
            original = plistlib.loads(source.read_bytes())
            original.update(CFBundleExecutable='OriginalExecutable', CFBundleVersion='99',
                            DTSDKName='iphoneos27.0', NSMicrophoneUsageDescription='From IPA')
            # The input has no storyboard; do not import the template's Main.
            original.pop('UIMainStoryboardFile', None)
            project = root / 'Test/Info.plist'
            edits = plistlib.loads(project.read_bytes())
            overrides = {
                'CFBundleDisplayName': 'Edited before first build',
                'NSCameraUsageDescription': 'My camera permission',
                'CFBundleURLTypes': [{'CFBundleURLSchemes': ['my-scheme']}],
                'CustomSettings': {'enabled': True, 'data': b'\x00\xff'},
            }
            edits.update(overrides)
            project.write_bytes(plistlib.dumps(edits))
            before = project.read_bytes()
            for version in ['99', '100']:
                original['CFBundleVersion'] = version
                source.write_bytes(plistlib.dumps(original))
                input_bytes = source.read_bytes()
                result = self.run_pack(env)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                for path in [project, products / 'Test.app/Info.plist']:
                    info = plistlib.loads(path.read_bytes())
                    for key, value in overrides.items():
                        self.assertEqual(info[key], value)
                    self.assertEqual(info['CFBundleVersion'], version)
                    self.assertEqual(info['CFBundleExecutable'], 'OriginalExecutable')
                    self.assertEqual(info['DTSDKName'], 'iphoneos27.0')
                    self.assertEqual(info['NSMicrophoneUsageDescription'], 'From IPA')
                    self.assertNotIn('UIMainStoryboardFile', info)
                self.assertEqual(source.read_bytes(), input_bytes)
                if version == '99':
                    self.assertEqual((root / '.monkeydev/Test-Info.plist.backup').read_bytes(), before)

    def test_plist_backup_and_history_are_ignored_by_git(self):
        with tempfile.TemporaryDirectory(prefix='monkeydev-plist-git-') as temp:
            root = Path(temp)
            _, _, env = self.pack_fixture(root)
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            result = self.run_pack(env)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            for name in ['Test-Info.plist.backup', 'Test.plist', '.gitignore']:
                path = root / '.monkeydev' / name
                self.assertTrue(path.is_file())
                result = subprocess.run(['git', 'check-ignore', '-q', str(path)], cwd=root)
                self.assertEqual(result.returncode, 0, str(path))
            self.assertFalse(list(root.glob('.monkeydev-*-Info.plist.backup')))

    def test_xcode_plist_edits_survive_input_updates(self):
        with tempfile.TemporaryDirectory(prefix='monkeydev-plist-edits-') as temp:
            root = Path(temp)
            inputs, products, env = self.pack_fixture(root)
            app = inputs / 'Input.app'
            shutil.copytree(ROOT / 'Resource/TargetApp.app', app)
            source = app / 'Info.plist'
            original = plistlib.loads(source.read_bytes())
            project = root / 'Test/Info.plist'
            result = self.run_pack(env)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            edits = plistlib.loads(project.read_bytes())
            edits['CFBundleDisplayName'] = 'Edited in Xcode'
            edits['NSCameraUsageDescription'] = 'My camera description'
            edits['CFBundleURLTypes'] = [{'CFBundleURLSchemes': ['custom-scheme']}]
            project.write_bytes(plistlib.dumps(edits))
            for version in ['2', '3', '3']:
                info = {**original, 'CFBundleVersion': version,
                        'NSMicrophoneUsageDescription': 'Input ' + version}
                source.write_bytes(plistlib.dumps(info))
                result = self.run_pack(env)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                output = plistlib.loads((products / 'Test.app/Info.plist').read_bytes())
                self.assertEqual(output['CFBundleVersion'], version)
                self.assertEqual(output['NSMicrophoneUsageDescription'], 'Input ' + version)
                for key in ['CFBundleDisplayName', 'NSCameraUsageDescription', 'CFBundleURLTypes']:
                    self.assertEqual(output[key], edits[key])
            # Local edit history survives removal of build products (Xcode Clean).
            shutil.rmtree(products / 'Test.app')
            result = self.run_pack(env)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(plistlib.loads((products / 'Test.app/Info.plist').read_bytes())['CFBundleDisplayName'],
                             edits['CFBundleDisplayName'])
            edits = plistlib.loads(project.read_bytes())
            del edits['NSCameraUsageDescription']
            project.write_bytes(plistlib.dumps(edits))
            result = self.run_pack(env)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn('NSCameraUsageDescription', plistlib.loads((products / 'Test.app/Info.plist').read_bytes()))

    def test_device_restriction_removed_after_plist_replacement_and_final_phase(self):
        with tempfile.TemporaryDirectory(prefix='monkeydev-final-plist-') as temp:
            root = Path(temp)
            inputs, products, env = self.pack_fixture(root)
            app = inputs / 'Input.app'
            shutil.copytree(ROOT / 'Resource/TargetApp.app', app)
            info = plistlib.loads((app / 'Info.plist').read_bytes())
            info['UISupportedDevices'] = ['iPhone1,1']
            (app / 'Info.plist').write_bytes(plistlib.dumps(info))
            original = (app / 'Info.plist').read_bytes()
            project_plist = root / 'Test/Info.plist'
            project = plistlib.loads(project_plist.read_bytes())
            project['CFBundleExecutable'] = 'Test'
            project_plist.write_bytes(plistlib.dumps(project))
            result = self.run_pack(env)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            output = products / 'Test.app/Info.plist'
            self.assertNotIn('UISupportedDevices', plistlib.loads(output.read_bytes()))
            # Simulate Xcode ProcessInfoPlistFile restoring the source plist.
            shutil.copy2(project_plist, output)
            self.assertIn('UISupportedDevices', plistlib.loads(output.read_bytes()))
            result = subprocess.run(['/bin/bash', str(ROOT / 'Tools/pack.sh'), 'codesign'],
                                    env={**env, 'CODE_SIGNING_ALLOWED': 'NO'},
                                    capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn('UISupportedDevices', plistlib.loads(output.read_bytes()))
            self.assertEqual((app / 'Info.plist').read_bytes(), original)

    def test_replaced_ipa_refreshes_input_and_does_not_merge_old_files(self):
        with tempfile.TemporaryDirectory(prefix='monkeydev IPA replacement-') as temp:
            root = Path(temp)
            inputs, products, env = self.pack_fixture(root)
            cached = inputs / 'Input.app'
            shutil.copytree(ROOT / 'Resource/TargetApp.app', cached)
            (cached / 'version.txt').write_text('legacy extracted app')
            legacy = root / 'Test/tmp/Invalid.app'
            legacy.mkdir(parents=True)
            (legacy / 'Info.plist').write_text('stale extraction')
            ipa = inputs / 'Input.ipa'
            output = products / 'Test.app'
            for version, bundle in [('one', 'Input.app'), ('two', 'Input.app'),
                                    ('three', 'Replacement.app')]:
                with zipfile.ZipFile(ipa, 'w') as archive:
                    demo = ROOT / 'Resource/TargetApp.app'
                    for file in demo.rglob('*'):
                        if file.is_file() and file.name != 'Info.plist':
                            archive.write(file, f'Payload/{bundle}/{file.relative_to(demo)}')
                    info = plistlib.loads((demo / 'Info.plist').read_bytes())
                    info['CFBundleVersion'] = {'one': '1', 'two': '2', 'three': '3'}[version]
                    archive.writestr(f'Payload/{bundle}/Info.plist', plistlib.dumps(info))
                    archive.writestr(f'Payload/{bundle}/version.txt', version)
                    archive.writestr(f'Payload/{bundle}/only-{version}.txt', version)
                result = self.run_pack(env)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual((output / 'version.txt').read_text(), version)
                self.assertEqual(plistlib.loads((output / 'Info.plist').read_bytes())['CFBundleVersion'],
                                 info['CFBundleVersion'])
                self.assertEqual(sorted(p.name for p in output.glob('only-*.txt')),
                                 ['only-' + version + '.txt'])
                self.assertEqual((cached / 'version.txt').read_text(), 'legacy extracted app')
                self.assertEqual(sorted(p.name for p in inputs.glob('*.app')), ['Input.app'])
                self.assertFalse((products / '.monkeydev-input-Test').exists())
            result = self.run_pack(env)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual((output / 'version.txt').read_text(), 'three')
            # Corrupt or ambiguous archives must not fall back to the old App.
            before = {str(p.relative_to(output)): p.read_bytes()
                      for p in output.rglob('*') if p.is_file()}
            state = products / '.monkeydev-Test.pack-files'
            previous_state = state.read_bytes()
            for kind in ['corrupt', 'empty', 'multiple']:
                with self.subTest(archive=kind):
                    if kind == 'corrupt':
                        ipa.write_text('invalid zip')
                    else:
                        with zipfile.ZipFile(ipa, 'w') as archive:
                            if kind == 'multiple':
                                for name in ['One.app', 'Two.app']:
                                    archive.writestr(f'Payload/{name}/Info.plist', 'ambiguous')
                    result = self.run_pack(env)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(before, {str(p.relative_to(output)): p.read_bytes()
                                             for p in output.rglob('*') if p.is_file()})
                    self.assertEqual(state.read_bytes(), previous_state)
                    self.assertFalse((products / '.monkeydev-input-Test').exists())

    def test_missing_or_uncopyable_dylib_preserves_previous_product(self):
        with tempfile.TemporaryDirectory(prefix='monkeydev dylib failure-') as temp:
            root = Path(temp)
            inputs, products, env = self.pack_fixture(root)
            shutil.copytree(ROOT / 'Resource/TargetApp.app', inputs / 'Input.app')
            result = self.run_pack(env)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            output = products / 'Test.app'
            before = {str(p.relative_to(output)): p.read_bytes()
                      for p in output.rglob('*') if p.is_file()}
            state = products / '.monkeydev-Test.pack-files'
            previous_state = state.read_bytes()
            env['MONKEYDEV_INSERT_DYLIB'] = 'YES'
            result = self.run_pack(env)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Project dylib not found', result.stderr)
            self.assertEqual(before, {str(p.relative_to(output)): p.read_bytes()
                                     for p in output.rglob('*') if p.is_file()})
            self.assertEqual(state.read_bytes(), previous_state)
            # Simulate a copy failure even though the source passes preflight.
            dylib = products / 'libTestDylib.dylib'
            shutil.copy2(inputs / 'Input.app/TargetApp', dylib)
            programs = root / 'programs'
            programs.mkdir()
            stub = programs / 'cp'
            stub.write_text('''#!/bin/bash
for argument in "$@"; do
    if [[ "$argument" == "$MD_TEST_DYLIB" ]]; then exit 1; fi
done
exec /bin/cp "$@"
''')
            stub.chmod(0o755)
            env.update(PATH=str(programs) + ':' + os.environ['PATH'], MD_TEST_DYLIB=str(dylib))
            result = self.run_pack(env)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Cannot copy project dylib', result.stderr)
            self.assertEqual(before, {str(p.relative_to(output)): p.read_bytes()
                                     for p in output.rglob('*') if p.is_file()})
            self.assertEqual(state.read_bytes(), previous_state)
            self.assertFalse(list(products.glob('.monkeydev-repack.*')))
            self.assertFalse((products / '.monkeydev-input-Test').exists())
            # With a real arm64 dylib restored, initial and incremental injection
            # must succeed and leave exactly one load command in the product.
            source = root / 'library.c'
            source.write_text('int monkeydev_test_library(void) { return 1; }\n')
            subprocess.run(['xcrun', '--sdk', 'iphoneos', 'clang', '-arch', 'arm64',
                            '-miphoneos-version-min=15.0', '-dynamiclib', str(source),
                            '-o', str(dylib)], check=True, capture_output=True)
            env['PATH'] = os.environ['PATH']
            for _ in range(2):
                result = self.run_pack(env)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual((output / 'Frameworks/libTestDylib.dylib').read_bytes(), dylib.read_bytes())
                loads = subprocess.check_output(['xcrun', 'otool', '-L', str(output / 'TargetApp')], text=True)
                self.assertEqual(loads.count('@executable_path/Frameworks/libTestDylib.dylib'), 1)

    def test_repack_replaces_old_input_and_preserves_xcode_profile(self):
        with tempfile.TemporaryDirectory(prefix='monkeydev-repack-') as temp:
            root = Path(temp)
            target = root / 'Test'
            input_app = target / 'TargetApp/Input.app'
            input_app.parent.mkdir(parents=True)
            shutil.copytree(ROOT / 'Resource/TargetApp.app', input_app)
            shutil.copy2(input_app / 'Info.plist', target / 'Info.plist')
            products = root / 'Products'
            products.mkdir()
            output = products / 'Test.app'
            output.mkdir()
            # Migrate a pre-manifest product with an unsupported stale library.
            (output / 'Frameworks').mkdir()
            (output / 'Frameworks/StaleFat.dylib').write_bytes(bytes.fromhex('cafebabe') + bytes(32))
            # Xcode's current profile must win over the input's original profile.
            profile = b'current Xcode provisioning profile'
            (output / 'embedded.mobileprovision').write_bytes(profile)
            (input_app / 'embedded.mobileprovision').write_bytes(b'input profile')
            old_frameworks = input_app / 'Frameworks'
            old_frameworks.mkdir(exist_ok=True)
            old_library = old_frameworks / 'PreviousOnly.dylib'
            shutil.copy2(input_app / 'TargetApp', old_library)
            old_resource = input_app / 'PreviousOnly.txt'
            old_resource.write_text('old input resource')
            env = dict(os.environ, MonkeyDevPath=str(ROOT), SRCROOT=str(root),
                       PROJECT_DIR=str(root), TARGET_NAME='Test', BUILT_PRODUCTS_DIR=str(products),
                       TARGET_BUILD_DIR=str(products), FULL_PRODUCT_NAME='Test.app',
                       MONKEYDEV_MINIMAL='YES', MONKEYDEV_INSERT_DYLIB='NO',
                       MONKEYDEV_REVEAL='NO', MONKEYDEV_CLASS_DUMP='NO',
                       MONKEYDEV_RESTORE_SYMBOL='NO', PRODUCT_BUNDLE_IDENTIFIER='com.example.repack',
                       CONFIGURATION='Debug', PLATFORM_NAME='iphoneos')
            def pack():
                return subprocess.run(['/bin/bash', str(ROOT / 'Tools/pack.sh')], env=env,
                                      capture_output=True, text=True, timeout=30)
            result = pack()
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((output / 'Frameworks/PreviousOnly.dylib').exists())
            self.assertFalse((output / 'Frameworks/StaleFat.dylib').exists())
            self.assertFalse(list(products.glob('.monkeydev-repack.*')))
            self.assertFalse(list((target / 'tmp').rglob('*.app')))
            # Simulate Xcode Copy Resources/CopyFiles after the packaging phase.
            # Subsequent incremental builds may skip these unchanged tasks.
            (output / 'Cached.storyboardc').mkdir()
            (output / 'Cached.storyboardc/View.nib').write_bytes(b'compiled Xcode resource')
            (output / 'Frameworks/XcodeEmbedded.framework').mkdir()
            (output / 'Frameworks/XcodeEmbedded.framework/resource').write_text('Xcode-owned')
            (output / '_CodeSignature').mkdir()
            (output / '_CodeSignature/CodeResources').write_text('obsolete signature')
            old_library.unlink()
            old_resource.unlink()
            (input_app / 'CurrentOnly.txt').write_text('new input resource')
            for _ in range(2):
                result = pack()
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertFalse((output / 'Frameworks/PreviousOnly.dylib').exists())
                self.assertFalse((output / 'Frameworks/StaleFat.dylib').exists())
                self.assertFalse((output / 'PreviousOnly.txt').exists())
                self.assertEqual((output / 'CurrentOnly.txt').read_text(), 'new input resource')
                self.assertEqual((output / 'embedded.mobileprovision').read_bytes(), profile)
                self.assertEqual((input_app / 'embedded.mobileprovision').read_bytes(), b'input profile')
                self.assertEqual((output / 'Cached.storyboardc/View.nib').read_bytes(), b'compiled Xcode resource')
                self.assertEqual((output / 'Frameworks/XcodeEmbedded.framework/resource').read_text(), 'Xcode-owned')
                self.assertFalse((output / '_CodeSignature').exists())
            before = {str(p.relative_to(output)): p.read_bytes() for p in output.rglob('*') if p.is_file()}
            state = products / '.monkeydev-Test.pack-files'
            previous_state = state.read_bytes()
            (input_app / 'TargetApp').write_bytes(b'invalid executable')
            result = pack()
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(before, {str(p.relative_to(output)): p.read_bytes()
                                      for p in output.rglob('*') if p.is_file()})
            self.assertEqual(state.read_bytes(), previous_state)
            self.assertFalse(list(products.glob('.monkeydev-repack.*')))

    def test_staging_stays_outside_xcode_source_groups(self):
        with tempfile.TemporaryDirectory(prefix='monkeydev-stage-location-') as temp:
            root = Path(temp)
            source_root = root / 'Sources'
            source_root.mkdir()
            products = root / 'Build Products'
            products.mkdir()
            input_app = source_root / 'Input.app'
            input_app.mkdir()
            (input_app / 'Info.plist').write_bytes(plistlib.dumps({'CFBundleExecutable': 'Example'}))
            output = products / 'Built.app'
            output.mkdir()
            (output / 'previous').write_text('old product')
            definitions = (ROOT / 'Tools/pack.sh').read_text().split('\nif [[ "$1" == "codesign" ]]; then')[0]
            env = dict(os.environ, MonkeyDevPath=str(ROOT), SRCROOT=str(source_root), TARGET_NAME='Test')
            result = subprocess.run(['/bin/bash', '-c', definitions + '''
BUILD_APP_PATH="$1"
replaceBuildApp "$2"
[[ "$repackWork" == "$3"/.monkeydev-repack.* ]] || exit 9
[[ ! -e "$TEMP_PATH" ]] || exit 10
exit 7
''', 'stage-test', str(output), str(input_app), str(products)],
                                    env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 7, result.stdout + result.stderr)
            self.assertEqual((output / 'previous').read_text(), 'old product')
            self.assertFalse(list(products.glob('.monkeydev-repack.*')))

    def test_invalid_input_preserves_existing_product(self):
        with tempfile.TemporaryDirectory(prefix='monkeydev-repack-failure-') as temp:
            root = Path(temp)
            output = root / 'Built.app'
            output.mkdir()
            (output / 'keep').write_text('previous product')
            staging = root / 'tmp'
            staging.mkdir()
            definitions = (ROOT / 'Tools/pack.sh').read_text().split('\nif [[ "$1" == "codesign" ]]; then')[0]
            env = dict(os.environ, MonkeyDevPath=str(ROOT), SRCROOT=str(root), TARGET_NAME='Test')
            result = subprocess.run(['/bin/bash', '-c', definitions +
                                     '\nTEMP_PATH="$1"; BUILD_APP_PATH="$2"; replaceBuildApp "$3"',
                                     'copy-test', str(staging), str(output), str(root / 'Missing.app')],
                                    env=env, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((output / 'keep').read_text(), 'previous product')

    def test_cleanup_keeps_input_and_removes_manifest_references(self):
        with tempfile.TemporaryDirectory(prefix='monkeydev-metadata-') as temp:
            root = Path(temp)
            app = root / 'Input.app'
            (app / 'SC_Info').mkdir(parents=True)
            (app / 'PlugIns/widgetextension.appex').mkdir(parents=True)
            (app / 'Watch').mkdir()
            manifest = {'SinfReplicationPaths': ['PlugIns/widgetextension.appex/SC_Info/widgetextension.sinf']}
            (app / 'SC_Info/Manifest.plist').write_bytes(plistlib.dumps(manifest))
            (app / 'Info.plist').write_bytes(plistlib.dumps({
                'CFBundleExecutable': 'Example', 'CFBundleIdentifier': 'com.example.test',
                'CFBundlePackageType': 'APPL', 'UISupportedDevices': ['old-device'],
            }))
            source = root / 'main.c'
            source.write_text('int main(void) { return 0; }\n')
            sdk = subprocess.check_output(['xcrun', '--sdk', 'iphoneos', '--show-sdk-path'], text=True).strip()
            subprocess.run(['xcrun', 'clang', '-target', 'arm64-apple-ios15.0', '-isysroot', sdk,
                            str(source), '-o', str(app / 'Example')], check=True)
            output = root / 'Built.app'
            shutil.copytree(app, output)
            (output / 'Frameworks').mkdir()
            # A retired runtime left by an old build would fail native verify.
            (output / 'Frameworks/libsubstrate.dylib').write_bytes(bytes.fromhex('cafebabe') + bytes(32))
            (output / 'Frameworks/RevealServer.framework').mkdir()
            (output / 'Frameworks/RevealServer.framework/RevealServer').write_bytes(bytes.fromhex('cafebabe') + bytes(32))
            for name in ['libcycript.dylib', 'libcycript.cy', 'libcycript.db']:
                (output / 'Frameworks' / name).write_bytes(bytes.fromhex('cafebabe') + bytes(32))
            # Load the production functions without invoking the command dispatcher.
            definitions = (ROOT / 'Tools/pack.sh').read_text().split('\nif [[ "$1" == "codesign" ]]; then')[0]
            env = dict(os.environ, MonkeyDevPath=str(ROOT), SRCROOT=str(root), TARGET_NAME='Test')
            result = subprocess.run(['/bin/bash', '-c', definitions + '\ncheckApp "$1" "$2"',
                                     'metadata-test', str(output), str(app)], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse((output / 'Frameworks/libsubstrate.dylib').exists())
            self.assertFalse((output / 'Frameworks/RevealServer.framework').exists())
            for name in ['libcycript.dylib', 'libcycript.cy', 'libcycript.db']:
                self.assertFalse((output / 'Frameworks' / name).exists())
            # Preserve the same-named library when it belongs to the input App.
            (app / 'Frameworks').mkdir()
            shutil.copy2(app / 'Example', app / 'Frameworks/libsubstrate.dylib')
            shutil.copy2(app / 'Frameworks/libsubstrate.dylib', output / 'Frameworks/libsubstrate.dylib')
            result = subprocess.run(['/bin/bash', '-c', definitions + '\ncheckApp "$1" "$2"',
                                     'metadata-test', str(output), str(app)], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual((output / 'Frameworks/libsubstrate.dylib').read_bytes(), (app / 'Example').read_bytes())
            for directory in ['SC_Info', 'PlugIns', 'Watch']:
                self.assertFalse((output / directory).exists())
                self.assertTrue((app / directory).exists())
            self.assertNotIn('UISupportedDevices', plistlib.loads((output / 'Info.plist').read_bytes()))
            self.assertEqual(plistlib.loads((app / 'SC_Info/Manifest.plist').read_bytes()), manifest)

if __name__ == '__main__':
    unittest.main()
