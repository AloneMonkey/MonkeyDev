"""Installer integration checks: isolated DESTDIR, no sudo or user-home writes."""
from pathlib import Path
import hashlib
import os
import platform
import plistlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

@unittest.skipUnless(platform.system() == 'Darwin' and platform.machine() == 'arm64', 'requires Apple Silicon/Xcode')
class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='monkeydev-installer test-')
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.source = self.work / 'source'
        self.source.mkdir()
        for item in ['bin', 'Tools', 'Frameworks', 'MFrameworks', 'Librarys', 'Resource', 'include']:
            shutil.copytree(ROOT / item, self.source / item)
        self.templates = self.work / 'raw templates'
        self.templates.mkdir()
        # Complete-template fixture exercises installation without network or patching.
        data = {
            'Nodes': ['Trace/old.s'], 'Definitions': {},
            'Project': {'SharedSettings': {'ARCHS': 'arm64', 'ENABLE_USER_SCRIPT_SANDBOXING': 'NO'},
                        'Configurations': {'Debug': {}}},
            'Targets': [{'SharedSettings': {}, 'BuildPhases': []}],
        }
        for name in ['Base', 'MonkeyApp', 'MonkeyAppLibrary']:
            directory = self.templates / (name + '.xctemplate')
            directory.mkdir()
            (directory / 'TemplateInfo.plist').write_bytes(plistlib.dumps(data))
        for name in ['___PACKAGENAMEASIDENTIFIER___.m', 'Logos/___PACKAGENAMEASIDENTIFIER___.xm',
                     'Logos/___PACKAGENAMEASIDENTIFIER___.mm', 'fishhook/fishhook.c', 'fishhook/fishhook.h',
                     'Tools/LLDBTools.h', 'Tools/LLDBTools.mm', 'Trace/MDMethodTrace.h', 'Trace/MDMethodTrace.mm']:
            path = self.templates / 'MonkeyAppLibrary.xctemplate' / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('// template fixture\n')
        self.dump = self.work / 'dump'
        self.dump.mkdir()
        for name in ['dump.py', 'dump.js']: (self.dump / name).write_text('# fixture\n')
        self.destination = self.work / 'package'
        self.prefix = self.destination / 'opt/MonkeyDev'
        self.env = dict(os.environ, MONKEYDEV_DESTDIR=str(self.destination),
                        MONKEYDEV_SOURCE_DIR=str(self.source), MONKEYDEV_TEMPLATES_DIR=str(self.templates),
                        MONKEYDEV_DUMP_DIR=str(self.dump))

    def run_install(self, updater=False, shell_command=False):
        script = self.source / ('bin/md-update' if updater else 'bin/md-install')
        command = ['/bin/sh', '-c', script.read_text()] if shell_command else ['/bin/bash', str(script)]
        result = subprocess.run(command,
                                env=self.env, capture_output=True, text=True, timeout=45)
        return result

    def fingerprint(self):
        return {str(p.relative_to(self.prefix)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in self.prefix.rglob('*') if p.is_file() and not p.is_symlink()}

    def test_fresh_install_and_repeat_update(self):
        retired = ['Tools/Removed Helper.sh', 'Resource/removed.txt']
        for name in retired:
            (self.source / name).write_text('first release only')
        (self.source / 'SKILL.md').write_text('# MonkeyDev\n')
        result = self.run_install(shell_command=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('Packaging mode', result.stdout)
        receipt = plistlib.loads((self.prefix / 'install-receipt.plist').read_bytes())
        self.assertEqual(receipt['sourceMode'], 'local')
        self.assertEqual(receipt['installerVersion'], '3.0')
        self.assertEqual(receipt['templatesRef'], 'b2dc8f7a40f33a13617959b98c61e799d1a2503c')
        for name in ['bin/monkeyparser', 'bin/class-dump', 'Tools/reveal.sh', 'Tools/lookin.sh', 'Librarys/Lookin/LookinServer.framework/LookinServer', 'Librarys/Lookin/LookinServer.framework/Info.plist', 'Librarys/Lookin/LookinServer.framework/LICENSE', 'Librarys/Lookin/LookinServer-1.2.8-source.tar.gz', 'Tools/info-plist.js', 'Tools/tweak-deploy.sh', 'Tools/cocoapods-compat.rb', 'Librarys/roothide/libsubstrate.tbd', 'Librarys/roothide/libroothide.tbd', 'Librarys/roothide/include/roothide.h', 'Librarys/roothide/include/module.modulemap', 'Librarys/roothide/LICENSE',
                     'templates/MonkeyAppLibrary.xctemplate/Tools/LLDBTools.mm']:
            self.assertTrue((self.prefix / name).is_file(), name)
        checks = subprocess.run(['shasum', '-a', '256', '-c', 'install-files.sha256'], cwd=self.prefix, capture_output=True)
        self.assertEqual(checks.returncode, 0, checks.stderr)
        # Only files owned by the previous release are removed on update.
        for name in retired:
            (self.source / name).unlink()
        (self.source / 'SKILL.md').unlink()
        (self.prefix / 'Frameworks/User.dylib').write_text('preserve')
        (self.prefix / 'Tools/User Helper.sh').write_text('preserve user script')
        (self.prefix / 'templates/RemovedTemplate.xctemplate').mkdir()
        old_installer = (self.prefix / 'bin/md-install').read_bytes()
        result = self.run_install(updater=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.prefix / 'Frameworks/User.dylib').read_text(), 'preserve')
        self.assertEqual((self.prefix / 'Tools/User Helper.sh').read_text(), 'preserve user script')
        for name in retired + ['SKILL.md']:
            self.assertFalse((self.prefix / name).exists(), name)
        self.assertFalse((self.prefix / 'templates/RemovedTemplate.xctemplate').exists())
        self.assertEqual((self.prefix / 'bin/md-install').read_bytes(), old_installer)
        self.assertFalse(list(self.prefix.parent.glob('.monkeydev-install.*')))
        (self.prefix / 'Frameworks/User.dylib').write_text('user updated their library')
        doctor = subprocess.run(['/bin/bash', str(self.prefix / 'bin/md-doctor')], capture_output=True, text=True)
        self.assertEqual(doctor.returncode, 0, doctor.stdout + doctor.stderr)
        # Hashes do not cover executable bits; diagnose permission loss separately.
        for name in ['monkeyparser', 'class-dump']:
            tool = self.prefix / 'bin' / name
            mode = tool.stat().st_mode & 0o777
            tool.chmod(0o644)
            try:
                doctor = subprocess.run(['/bin/bash', str(self.prefix / 'bin/md-doctor')], capture_output=True, text=True)
                self.assertNotEqual(doctor.returncode, 0)
                self.assertIn(name + ' is not executable:', doctor.stdout)
            finally:
                tool.chmod(mode)
        with (self.prefix / 'Tools/pack.sh').open('a') as file:
            file.write('\n# modified release file\n')
        doctor = subprocess.run(['/bin/bash', str(self.prefix / 'bin/md-doctor')], capture_output=True, text=True)
        self.assertNotEqual(doctor.returncode, 0)
        self.assertIn('differ from the receipt', doctor.stdout)

    def test_manifest_cannot_remove_files_outside_the_staged_installation(self):
        external = self.work / 'Xcode.app/Contents/Resources'
        external.mkdir(parents=True)
        protected = external / 'Embedded-Device.xcspec'
        protected.write_text('preserve Xcode specification')
        self.prefix.mkdir(parents=True)
        manifest = self.prefix / 'install-files.sha256'
        for relative in ['../../Xcode.app/Contents/Resources/Embedded-Device.xcspec',
                         'Tools/External/Embedded-Device.xcspec']:
            with self.subTest(path=relative):
                tools = self.prefix / 'Tools'
                tools.mkdir(exist_ok=True)
                link = tools / 'External'
                if not link.is_symlink(): link.symlink_to(external)
                manifest.write_text('0' * 64 + '  ' + relative + '\n')
                before = self.fingerprint()
                result = self.run_install()
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(protected.read_text(), 'preserve Xcode specification')
                self.assertEqual(before, self.fingerprint())

    def run_user_install(self):
        # Exercise the real user-integration branch against an isolated home and
        # prefix. These substitutions exist only in this temporary test harness.
        script = (self.source / 'bin/md-install').read_text()
        script = script.replace('MonkeyDevPath="${destination}/opt/MonkeyDev"',
                                'MonkeyDevPath="$MD_TEST_PREFIX"')
        script = script.replace('[[ "$EUID" == 0 ]] || fail "Run md-install with sudo."', ':')
        script = script.replace('userHome="$(/usr/bin/dscl . -read "/Users/$installUser" NFSHomeDirectory | sed \'s/^NFSHomeDirectory: //\')"',
                                'userHome="$MD_TEST_HOME"')
        harness = self.work / 'user-install.sh'
        harness.write_text(script)
        programs = self.work / 'xcode-tools'
        programs.mkdir(exist_ok=True)
        developer = self.work / 'Xcode.app/Contents/Developer'
        sdk = developer / 'Platforms/iPhoneOS.platform/Developer/SDKs/iPhoneOS.sdk'
        sdk.mkdir(parents=True, exist_ok=True)
        # Select an isolated fake Xcode, so even an accidental SDK-relative
        # modification would hit the fixture and be caught by its fingerprint.
        for name, content in {
            'xcodebuild': '#!/bin/bash\nprintf "Xcode 27.0\\nBuild version test\\n"\n',
            'xcrun': '#!/bin/bash\nprintf "%s\\n" "$MD_TEST_SDK"\n',
        }.items():
            command = programs / name
            command.write_text(content)
            command.chmod(0o755)
        env = {**self.env, 'MONKEYDEV_DESTDIR': '', 'SUDO_USER': os.environ['USER'],
               'MD_TEST_HOME': str(self.work / 'home'), 'MD_TEST_PREFIX': str(self.prefix),
               'MD_TEST_SDK': str(sdk), 'PATH': str(programs) + ':' + os.environ['PATH']}
        return subprocess.run(['/bin/bash', str(harness)], env=env,
                              capture_output=True, text=True, timeout=45)

    def test_foreign_template_link_is_preserved_on_install_and_update(self):
        home = self.work / 'home'
        link = home / 'Library/Developer/Xcode/Templates/MonkeyDev'
        link.parent.mkdir(parents=True)
        profile = home / '.zshrc'
        profile.write_text('# user configuration\n')
        external = self.work / 'other-templates'
        external.mkdir()
        (external / 'custom').write_text('keep template')
        for existing_install in [False, True]:
            with self.subTest(existing_install=existing_install):
                if existing_install:
                    self.prefix.mkdir(parents=True)
                    (self.prefix / 'previous').write_text('keep installation')
                # Also cover a dangling foreign registration.
                target = external if not existing_install else self.work / 'missing-templates'
                link.symlink_to(target)
                before = self.fingerprint() if self.prefix.exists() else None
                result = self.run_user_install()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('not our registration', result.stderr)
                self.assertEqual(os.readlink(link), str(target))
                self.assertEqual((external / 'custom').read_text(), 'keep template')
                self.assertEqual(profile.read_text(), '# user configuration\n')
                self.assertEqual(self.fingerprint() if self.prefix.exists() else None, before)
                self.assertFalse((self.prefix.parent / '.monkeydev-install.lock').exists())
                link.unlink()

    def test_symlinked_profile_is_preserved_on_install_and_update(self):
        home = self.work / 'home'
        home.mkdir()
        target = self.work / 'dotfiles/zshrc'
        target.parent.mkdir()
        target.write_text('# dotfiles configuration\n')
        profile = home / '.zshrc'
        profile.symlink_to(target)
        link = home / 'Library/Developer/Xcode/Templates/MonkeyDev'
        for existing_install in [False, True]:
            with self.subTest(existing_install=existing_install):
                if existing_install:
                    self.prefix.mkdir(parents=True)
                    (self.prefix / 'previous').write_text('keep installation')
                    link.parent.mkdir(parents=True)
                    link.symlink_to('/opt/MonkeyDev/templates')
                before = self.fingerprint() if self.prefix.exists() else None
                result = self.run_user_install()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('Shell profile is a symlink', result.stderr)
                self.assertEqual(os.readlink(profile), str(target))
                self.assertEqual(target.read_text(), '# dotfiles configuration\n')
                self.assertEqual(self.fingerprint() if self.prefix.exists() else None, before)
                if existing_install:
                    self.assertEqual(os.readlink(link), '/opt/MonkeyDev/templates')
                else:
                    self.assertFalse(link.is_symlink())
                self.assertFalse((self.prefix.parent / '.monkeydev-install.lock').exists())

    def test_user_install_preserves_xcode_projects_and_other_templates(self):
        home = self.work / 'home'
        templates = home / 'Library/Developer/Xcode/Templates'
        other = templates / 'My Templates/Custom.xctemplate/TemplateInfo.plist'
        other.parent.mkdir(parents=True)
        other.write_text('custom template')
        project = home / 'Documents/Example/Example.xcodeproj/project.pbxproj'
        project.parent.mkdir(parents=True)
        project.write_text('existing user project')
        specification = self.work / 'Xcode.app/Contents/PlugIns/Embedded-Device.xcspec'
        specification.parent.mkdir(parents=True)
        specification.write_text('original Xcode specification')
        profile = home / '.zshrc'
        profile.write_text('# existing user configuration\nexport USER_SETTING=keep\n')
        def protected_files():
            return {str(p.relative_to(self.work)): (p.read_bytes(), p.stat().st_mode & 0o777)
                    for p in [specification, project, other]}
        before_protected = protected_files()
        for _ in range(2):
            result = self.run_user_install()
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(specification.read_text(), 'original Xcode specification')
            self.assertEqual(project.read_text(), 'existing user project')
            self.assertEqual(other.read_text(), 'custom template')
            self.assertEqual(os.readlink(templates / 'MonkeyDev'), '/opt/MonkeyDev/templates')
            self.assertEqual(before_protected, protected_files())
        self.assertEqual(profile.read_text(), '# existing user configuration\nexport USER_SETTING=keep\n'
                         '\n# >>> MonkeyDev >>>\n'
                         'export MonkeyDevPath=/opt/MonkeyDev\n'
                         'export MonkeyDevDeviceIP=\n'
                         'export PATH=/opt/MonkeyDev/bin:$PATH\n'
                         '# <<< MonkeyDev <<<\n')
        # A real user directory must never be replaced with our symlink.
        link = templates / 'MonkeyDev'
        link.unlink()
        link.mkdir()
        (link / 'custom').write_text('user-owned directory')
        before = self.fingerprint()
        result = self.run_user_install()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Template path is not a symlink', result.stderr)
        self.assertEqual((link / 'custom').read_text(), 'user-owned directory')
        self.assertEqual(before, self.fingerprint())
        # Restore the fixture registration, then uninstall the updated release.
        # Settings outside the dedicated installation directory must survive.
        shutil.rmtree(link)
        link.symlink_to('/opt/MonkeyDev/templates')
        with profile.open('a') as file:
            file.write('\nexport ADDED_AFTER_INSTALL=keep\n')
        user_file = self.prefix / 'Frameworks/User.dylib'
        user_file.write_text('user-owned library')
        script = (self.source / 'bin/md-uninstall').read_text()
        script = script.replace('MonkeyDevPath="${destination}/opt/MonkeyDev"',
                                'MonkeyDevPath="$MD_TEST_PREFIX"')
        script = script.replace('[[ "$EUID" == 0 ]] || fail "Run md-uninstall with sudo."', ':')
        script = script.replace('userHome="$(/usr/bin/dscl . -read "/Users/$installUser" NFSHomeDirectory | sed \'s/^NFSHomeDirectory: //\')"',
                                'userHome="$MD_TEST_HOME"')
        harness = self.work / 'user-uninstall.sh'
        harness.write_text(script)
        env = {**os.environ, 'MONKEYDEV_DESTDIR': '', 'SUDO_USER': os.environ['USER'],
               'MD_TEST_HOME': str(home), 'MD_TEST_PREFIX': str(self.prefix)}
        result = subprocess.run(['/bin/bash', str(harness)], env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(profile.read_text(), '# existing user configuration\nexport USER_SETTING=keep\n'
                         '\nexport ADDED_AFTER_INSTALL=keep\n')
        self.assertFalse(self.prefix.exists())
        self.assertFalse(link.is_symlink())
        self.assertEqual(before_protected, protected_files())

    def test_doctor_checks_logos_permissions_without_requiring_theos_installation(self):
        home = self.work / 'home'
        (home / 'theos/bin').mkdir(parents=True)
        (home / 'theos/vendor/include/logos').mkdir(parents=True)
        (home / 'theos/vendor/include/logos/logos.h').touch()
        processor = home / 'theos/bin/logos.pl'
        processor.write_text('#!/usr/bin/perl\n')
        env = dict(os.environ, HOME=str(home))
        env.pop('SUDO_USER', None)
        def doctor():
            return subprocess.run(['/bin/bash', str(self.source / 'bin/md-doctor')],
                                  env=env, capture_output=True, text=True)
        processor.chmod(0o644)
        result = doctor()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Logos processor is not executable:', result.stdout)
        processor.chmod(0o755)
        result = doctor()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        processor.unlink()
        result = doctor()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('Install Theos as your normal user', result.stdout)

    def test_incomplete_source_leaves_previous_installation(self):
        self.prefix.mkdir(parents=True)
        (self.prefix / 'previous').write_text('unchanged')
        # An old installed copy must not mask a missing file in the new release.
        (self.prefix / 'Tools').mkdir()
        (self.prefix / 'Tools/reveal.sh').write_text('old release')
        before = self.fingerprint()
        (self.source / 'Tools/reveal.sh').unlink()
        result = self.run_install()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Missing required release file: Tools/reveal.sh', result.stderr)
        self.assertEqual(before, self.fingerprint())
        self.assertFalse(list(self.prefix.parent.glob('.monkeydev-install.*')))

    def test_template_failure_leaves_previous_installation(self):
        self.prefix.mkdir(parents=True)
        (self.prefix / 'previous').write_text('unchanged')
        before = self.fingerprint()
        (self.templates / 'MonkeyAppLibrary.xctemplate/TemplateInfo.plist').unlink()
        result = self.run_install()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(before, self.fingerprint())

    def test_missing_maintained_sources_cannot_fall_back_to_previous_release(self):
        result = self.run_install()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        before = self.fingerprint()
        maintained = ['bin/md-uninstall', 'bin/createIPA.command', 'Tools/tweak-deploy.sh', 'Tools/info-plist.js', 'Tools/cocoapods-compat.rb', 'Librarys/roothide/libsubstrate.tbd', 'Librarys/roothide/libroothide.tbd', 'Librarys/roothide/include/roothide.h', 'Librarys/roothide/include/module.modulemap', 'Librarys/roothide/LICENSE',
                      'Resource/TargetApp.app/Info.plist', 'Resource/TargetApp.app/TargetApp']
        for name in maintained:
            with self.subTest(file=name):
                source = self.source / name
                saved = source.read_bytes()
                source.unlink()
                try:
                    result = self.run_install(updater=True)
                    self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn('Missing required release file: ' + name, result.stderr)
                    self.assertEqual(before, self.fingerprint())
                    self.assertFalse(list(self.prefix.parent.glob('.monkeydev-install.*')))
                finally:
                    source.write_bytes(saved)

    def test_runtime_install_does_not_require_or_ship_development_files(self):
        (self.source / 'docs').mkdir()
        (self.source / 'docs/local-notes.md').write_text('local development record')
        # Local-only scripts and source patches must not be distributed either.
        result = self.run_install()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for name in ['docs', 'Tools/native', 'Tools/build-class-dump-arm64.sh',
                     'Tools/build-monkeyparser-arm64.sh']:
            self.assertFalse((self.prefix / name).exists(), name)
        # Earlier development installs recorded these paths in their manifest.
        # Updating must retire them without treating them as runtime inputs.
        retired = ['docs/old-notes.md', 'Tools/native/Old.h',
                   'Tools/build-class-dump-arm64.sh', 'Tools/build-monkeyparser-arm64.sh']
        with (self.prefix / 'install-files.sha256').open('a') as manifest:
            for name in retired:
                path = self.prefix / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('previous development release')
                manifest.write(hashlib.sha256(path.read_bytes()).hexdigest() + '  ' + name + '\n')
        if (self.source / 'Tools/native').exists():
            shutil.rmtree(self.source / 'Tools/native')
        for name in ['build-class-dump-arm64.sh', 'build-monkeyparser-arm64.sh']:
            (self.source / 'Tools' / name).unlink(missing_ok=True)
        result = self.run_install(updater=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for name in retired:
            self.assertFalse((self.prefix / name).exists(), name)
        for name in ['Tools/pack.sh', 'Tools/mpack.sh', 'Tools/reveal.sh', 'Tools/lookin.sh', 'Librarys/Lookin/LookinServer.framework/LookinServer', 'Librarys/Lookin/LookinServer.framework/Info.plist', 'Librarys/Lookin/LookinServer.framework/LICENSE', 'Librarys/Lookin/LookinServer-1.2.8-source.tar.gz',
                     'templates/MonkeyAppLibrary.xctemplate/Trace/MDMethodTrace.mm']:
            self.assertTrue((self.prefix / name).is_file(), name)
        checks = subprocess.run(['shasum', '-a', '256', '-c', 'install-files.sha256'],
                                cwd=self.prefix, capture_output=True)
        self.assertEqual(checks.returncode, 0, checks.stderr)

    def test_templates_are_installed_without_modification(self):
        result = self.run_install()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for source in self.templates.rglob('*'):
            if source.is_file():
                self.assertEqual(source.read_bytes(),
                    (self.prefix / 'templates' / source.relative_to(self.templates)).read_bytes())

    def test_old_or_incomplete_templates_leave_previous_installation(self):
        result = self.run_install()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        before = self.fingerprint()
        file = self.templates / 'Base.xctemplate/TemplateInfo.plist'
        data = plistlib.loads(file.read_bytes())
        data['Project']['SharedSettings']['ARCHS'] = 'armv7 arm64'
        file.write_bytes(plistlib.dumps(data))
        result = self.run_install(updater=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Incompatible template', result.stderr)
        self.assertEqual(before, self.fingerprint())
        data['Project']['SharedSettings']['ARCHS'] = 'arm64'
        file.write_bytes(plistlib.dumps(data))
        (self.templates / 'MonkeyAppLibrary.xctemplate/Trace/MDMethodTrace.mm').unlink()
        result = self.run_install(updater=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Missing template source', result.stderr)
        self.assertEqual(before, self.fingerprint())

    def test_non_native_tool_is_rejected(self):
        (self.source / 'bin/monkeyparser').write_text('not a native binary')
        result = self.run_install()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('thin native arm64', result.stderr)
        self.assertFalse(self.prefix.exists())

    def test_missing_optional_download_leaves_previous_installation(self):
        self.prefix.mkdir(parents=True)
        (self.prefix / 'previous').write_text('unchanged')
        before = self.fingerprint()
        (self.dump / 'dump.js').unlink()
        result = self.run_install()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(before, self.fingerprint())

    def test_publish_failure_rolls_back_previous_directory(self):
        self.prefix.mkdir(parents=True)
        (self.prefix / 'previous').write_text('unchanged')
        before = self.fingerprint()
        programs = self.work / 'programs'
        programs.mkdir()
        stub = programs / 'mv'
        stub.write_text('''#!/bin/bash
if [[ "$1" == *"/.monkeydev-install."*"/MonkeyDev" && "$2" == "$MD_TEST_TARGET" ]]; then
    echo 'simulated publication failure' >&2
    exit 1
fi
exec /bin/mv "$@"
''')
        stub.chmod(0o755)
        self.env.update(PATH=str(programs) + ':' + os.environ['PATH'], MD_TEST_TARGET=str(self.prefix.resolve()))
        result = self.run_install()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('simulated publication failure', result.stderr)
        self.assertEqual(before, self.fingerprint())
        self.assertFalse(list(self.prefix.parent.glob('.monkeydev-install.*')))

    def test_concurrent_install_lock_preserves_existing_lock(self):
        lock = self.prefix.parent / '.monkeydev-install.lock'
        lock.mkdir(parents=True)
        (lock / 'pid').write_text('test-owner')
        result = self.run_install()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('installer lock exists', result.stderr)
        self.assertEqual((lock / 'pid').read_text(), 'test-owner')

    def test_failed_rollback_preserves_recovery_files(self):
        self.prefix.mkdir(parents=True)
        (self.prefix / 'previous').write_text('recover me')
        programs = self.work / 'programs'
        programs.mkdir()
        stub = programs / 'mv'
        stub.write_text('''#!/bin/bash
if [[ "$1" == *"/.monkeydev-install."* && "$2" == "$MD_TEST_TARGET" ]]; then
    exit 1
fi
exec /bin/mv "$@"
''')
        stub.chmod(0o755)
        self.env.update(PATH=str(programs) + ':' + os.environ['PATH'], MD_TEST_TARGET=str(self.prefix.resolve()))
        result = self.run_install()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('recovery files and installer lock retained', result.stderr)
        recovery = list(self.prefix.parent.glob('.monkeydev-install.*/previous/previous'))
        self.assertEqual(len(recovery), 1)
        self.assertEqual(recovery[0].read_text(), 'recover me')

if __name__ == '__main__': unittest.main()
