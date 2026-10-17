"""Uninstall only isolated fixture installations; never /opt or real profiles."""
from pathlib import Path
import hashlib
import os
import plistlib
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

@unittest.skipUnless(Path('/usr/libexec/PlistBuddy').exists(), 'requires macOS')
class UninstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='monkeydev-uninstall-')
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.destination = self.work / 'package'
        self.prefix = self.destination / 'opt/MonkeyDev'
        self.home = self.work / 'home'
        self.home.mkdir()
        self.template = self.home / 'Library/Developer/Xcode/Templates/MonkeyDev'
        self.template.parent.mkdir(parents=True)
        self.manifest = self.prefix / 'install-files.sha256'
        self.receipt = self.prefix / 'install-receipt.plist'
        self.owned = ['bin/md', 'Tools/Helper With Spaces.sh', 'templates/MonkeyApp.xctemplate/TemplateInfo.plist']
        for name in self.owned:
            path = self.prefix / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('installed file: ' + name)
        self.manifest.write_text(''.join(hashlib.sha256((self.prefix / name).read_bytes()).hexdigest()
                                        + '  ' + name + '\n' for name in self.owned))
        self.metadata = {'installerVersion': '3.0', 'fileHashes': 'install-files.sha256'}
        self.write_receipt()

    def write_receipt(self):
        self.receipt.write_bytes(plistlib.dumps(self.metadata))

    def snapshot(self, root=None):
        root = root or self.prefix
        return {str(p.relative_to(root)): ('link', os.readlink(p)) if p.is_symlink()
                else ('file', p.read_bytes(), p.stat().st_mode & 0o777)
                for p in root.rglob('*') if p.is_symlink() or p.is_file()}

    def run_uninstall(self, user=False):
        env = dict(os.environ, MONKEYDEV_DESTDIR=str(self.destination))
        script = ROOT / 'bin/md-uninstall'
        if user:
            text = script.read_text()
            text = text.replace('MonkeyDevPath="${destination}/opt/MonkeyDev"',
                                'MonkeyDevPath="$MD_TEST_PREFIX"')
            text = text.replace('[[ "$EUID" == 0 ]] || fail "Run md-uninstall with sudo."', ':')
            text = text.replace('userHome="$(/usr/bin/dscl . -read "/Users/$installUser" NFSHomeDirectory | sed \'s/^NFSHomeDirectory: //\')"',
                                'userHome="$MD_TEST_HOME"')
            script = self.work / 'uninstall-harness.sh'
            script.write_text(text)
            env.update(MONKEYDEV_DESTDIR='', SUDO_USER=os.environ['USER'],
                       MD_TEST_PREFIX=str(self.prefix), MD_TEST_HOME=str(self.home))
        return subprocess.run(['/bin/bash', str(script)], env=env,
                              capture_output=True, text=True, timeout=20)

    def test_clean_installation_is_removed(self):
        result = self.run_uninstall()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.prefix.exists())

    def test_dedicated_directory_is_removed_but_external_files_are_preserved(self):
        extra = self.prefix / 'Frameworks/User.dylib'
        extra.parent.mkdir()
        extra.write_text('user library')
        project = self.home / 'Example.xcodeproj/project.pbxproj'
        project.parent.mkdir()
        project.write_text('existing project')
        specification = self.work / 'Xcode.app/Contents/Resources/Embedded-Device.xcspec'
        specification.parent.mkdir(parents=True)
        specification.write_text('existing Xcode')
        result = self.run_uninstall()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.prefix.exists())
        self.assertEqual(project.read_text(), 'existing project')
        self.assertEqual(specification.read_text(), 'existing Xcode')
        for name in self.owned + ['install-files.sha256', 'install-receipt.plist']:
            self.assertFalse((self.prefix / name).exists())

    def test_modified_files_do_not_block_dedicated_directory_removal(self):
        (self.prefix / self.owned[-1]).write_text('user modification')
        result = self.run_uninstall()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.prefix.exists())

    def test_missing_manifest_does_not_block_removal(self):
        self.manifest.unlink()
        result = self.run_uninstall()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.prefix.exists())

    def test_missing_receipt_refuses_to_guess(self):
        self.receipt.unlink()
        before = self.snapshot()
        result = self.run_uninstall()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(before, self.snapshot())

    def test_manifest_paths_are_not_used_for_deletion(self):
        external = self.work / 'keep.txt'
        external.write_text('keep')
        with self.manifest.open('a') as file:
            file.write('0' * 64 + '  ../../keep.txt\n')
        result = self.run_uninstall()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.prefix.exists())
        self.assertEqual(external.read_text(), 'keep')

    def test_symlink_cannot_redirect_uninstall_outside_installation(self):
        external = self.work / 'Xcode.app'
        external.mkdir()
        (external / 'specification').write_text('keep')
        (self.prefix / 'Tools/External').symlink_to(external)
        with self.manifest.open('a') as file:
            file.write(hashlib.sha256(b'keep').hexdigest() + '  Tools/External/specification\n')
        result = self.run_uninstall()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.prefix.exists())
        self.assertEqual((external / 'specification').read_text(), 'keep')

    def test_other_template_registration_is_not_removed(self):
        self.template.symlink_to(self.work / 'user-templates')
        before = self.snapshot()
        result = self.run_uninstall(user=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(os.readlink(self.template), str(self.work / 'user-templates'))
        self.assertEqual(before, self.snapshot())

    def test_replaced_release_file_link_does_not_delete_its_target(self):
        external = self.work / 'user-script'
        external.write_text('user script')
        path = self.prefix / self.owned[0]
        path.unlink()
        path.symlink_to(external)
        result = self.run_uninstall()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.prefix.exists())
        self.assertEqual(external.read_text(), 'user script')

    def test_symlinked_installation_directory_is_not_followed(self):
        original = self.prefix.parent / 'user-directory'
        self.prefix.rename(original)
        self.prefix.symlink_to(original)
        before = self.snapshot(original)
        result = self.run_uninstall()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('must not be a symlink', result.stderr)
        self.assertEqual(before, self.snapshot(original))

    def test_unrecorded_shell_configuration_is_not_changed(self):
        profile = self.home / '.zshrc'
        text = 'export MonkeyDevPath=/opt/MonkeyDev\nexport PATH=/opt/homebrew/bin:/opt/MonkeyDev/bin:$PATH\n'
        profile.write_text(text)
        self.template.symlink_to('/opt/MonkeyDev/templates')
        result = self.run_uninstall(user=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(profile.read_text(), text)
        self.assertFalse(self.template.is_symlink())

    def setup_owned_profile_block(self):
        profile = self.home / '.zshrc'
        before = 'export PATH=/opt/homebrew/bin:/opt/MonkeyDev/bin:$PATH\n'
        block = '\n# >>> MonkeyDev >>>\nexport MonkeyDevDeviceIP=\n# <<< MonkeyDev <<<\n'
        after = '\nexport CUSTOM_SETTING=keep\n'
        profile.write_text(before + block + after)
        profile.chmod(0o640)
        self.metadata['profileEdits'] = [{'path': str(profile), 'text': block}]
        self.write_receipt()
        return profile, before, block, after

    def test_only_recorded_shell_text_is_removed(self):
        profile, before, block, after = self.setup_owned_profile_block()
        result = self.run_uninstall(user=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(profile.read_text(), before + after)
        self.assertEqual(profile.stat().st_mode & 0o777, 0o640)

    def test_edited_shell_block_stops_before_any_deletion(self):
        profile, before, block, after = self.setup_owned_profile_block()
        profile.write_text(before + block.replace('DeviceIP=', 'DeviceIP=custom') + after)
        original_profile = profile.read_bytes()
        original_install = self.snapshot()
        result = self.run_uninstall(user=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('managed shell block changed', result.stderr)
        self.assertEqual(original_profile, profile.read_bytes())
        self.assertEqual(original_install, self.snapshot())

    def test_receipt_cannot_claim_arbitrary_user_path_settings(self):
        profile, before, block, after = self.setup_owned_profile_block()
        block = block.replace('export MonkeyDevDeviceIP=', 'export PATH=/opt/homebrew/bin:$PATH')
        profile.write_text(before + block + after)
        self.metadata['profileEdits'][0]['text'] = block
        self.write_receipt()
        original_profile = profile.read_bytes()
        original_install = self.snapshot()
        result = self.run_uninstall(user=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('unrecognized shell additions', result.stderr)
        self.assertEqual(original_profile, profile.read_bytes())
        self.assertEqual(original_install, self.snapshot())

if __name__ == '__main__': unittest.main()
