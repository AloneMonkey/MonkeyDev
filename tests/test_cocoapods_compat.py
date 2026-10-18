"""Exercise CocoaPods integration without changing an installed gem or user project."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
POD = Path('/opt/homebrew/bin/pod')
RUBY = Path('/opt/homebrew/opt/ruby/bin/ruby')
GEMS = Path('/opt/homebrew/opt/cocoapods/libexec')


@unittest.skipUnless(POD.exists() and RUBY.exists() and GEMS.exists(), 'requires Homebrew CocoaPods')
class CocoaPodsCompatibilityTests(unittest.TestCase):
    def test_install_preserves_project_and_rejects_unknown_copy_destination(self):
        with tempfile.TemporaryDirectory(prefix='monkeydev pod ') as directory:
            work = Path(directory)
            helper = ROOT / 'Tools/cocoapods-compat.rb'
            env = dict(os.environ, GEM_HOME=str(GEMS), COCOAPODS_DISABLE_STATS='true')
            fixture = r'''
require 'json'
require ARGV[1]
path = File.join(ARGV[0], 'Host.xcodeproj')
project = Xcodeproj::Project.new(path, false, 77)
target = project.new_target(:application, 'Host', :ios, '15.0')
target.build_configurations.each { |c| c.build_settings['MONKEYDEV_TEST_MARKER'] = 'preserve' }
script = target.new_shell_script_build_phase('Preserved script')
script.shell_script = "echo first\necho second"
copy = target.new_copy_files_build_phase('Preserved frameworks')
copy.dst_subfolder_spec = '10'
file = project.frameworks_group.new_file('Existing.framework')
copy.add_file_reference(file).settings = {'ATTRIBUTES' => ['CodeSignOnCopy']}
project.save
plist = Xcodeproj::Plist.read_from_path(project.path + 'project.pbxproj')
plist['objectVersion'] = '110'
plist['objects'][script.uuid]['shellScript'] = ['echo first', 'echo second']
entry = plist['objects'][copy.uuid]
entry.delete('dstSubfolderSpec')
entry['dstSubfolder'] = 'Frameworks'
Xcodeproj::Plist.write_to_path(plist, project.path + 'project.pbxproj')
puts JSON.generate({'script' => script.uuid, 'copy' => copy.uuid})
'''
            setup = subprocess.run([str(RUBY), '-e', fixture, str(work), str(helper)],
                                   env=env, capture_output=True, text=True)
            self.assertEqual(setup.returncode, 0, setup.stderr)
            identifiers = json.loads(setup.stdout)
            plugin = work / 'Plugin'
            plugin.mkdir()
            (plugin / 'Plugin.m').write_text('void monkeydev_plugin_fixture(void) {}\n')
            (plugin / 'Plugin.podspec').write_text('''Pod::Spec.new do |s|
  s.name = 'Plugin'
  s.version = '1.0'
  s.summary = 'Local integration fixture'
  s.homepage = 'https://example.com/Plugin'
  s.license = { :type => 'BSD' }
  s.author = 'Test'
  s.source = { :git => 'https://example.com/Plugin.git', :tag => s.version }
  s.ios.deployment_target = '15.0'
  s.source_files = '*.m'
end
''')
            (work / 'Podfile').write_text(
                'require ' + json.dumps(str(helper)) + "\nplatform :ios, '15.0'\n"
                "target 'Host' do\n  use_frameworks! :linkage => :dynamic\n"
                "  pod 'Plugin', :path => './Plugin'\nend\n")
            result = subprocess.run([str(POD), 'install', '--no-repo-update'], cwd=work,
                                    env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((work / 'Host.xcworkspace').is_dir())
            # Existing workspaces must also survive a repeated pod install.
            repeat = subprocess.run([str(POD), 'install', '--no-repo-update'], cwd=work,
                                    env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(repeat.returncode, 0, repeat.stdout + repeat.stderr)
            host = json.loads(subprocess.check_output([
                'plutil', '-convert', 'json', '-o', '-', str(work / 'Host.xcodeproj/project.pbxproj')]))
            self.assertEqual(str(host['objectVersion']), '110')
            objects = host['objects']
            self.assertEqual(objects[identifiers['script']]['shellScript'], 'echo first\necho second')
            phase = objects[identifiers['copy']]
            self.assertEqual(str(phase['dstSubfolderSpec']), '10')
            self.assertEqual(objects[phase['files'][0]]['settings']['ATTRIBUTES'], ['CodeSignOnCopy'])
            markers = [o['buildSettings']['MONKEYDEV_TEST_MARKER'] for o in objects.values()
                       if 'MONKEYDEV_TEST_MARKER' in o.get('buildSettings', {})]
            self.assertEqual(markers, ['preserve', 'preserve'])
            # A newer destination must fail before CocoaPods can discard it.
            project_file = work / 'Host.xcodeproj/project.pbxproj'
            mutate = r'''
require 'xcodeproj'
data = Xcodeproj::Plist.read_from_path(ARGV[0])
entry = data['objects'][ARGV[1]]
entry.delete('dstSubfolderSpec')
entry['dstSubfolder'] = 'PlugIns'
Xcodeproj::Plist.write_to_path(data, ARGV[0])
'''
            subprocess.run([str(RUBY), '-e', mutate, str(project_file), identifiers['copy']],
                           env=env, check=True, capture_output=True, text=True)
            before = project_file.read_bytes()
            rejected = subprocess.run([str(POD), 'install', '--no-repo-update'], cwd=work,
                                      env=env, capture_output=True, text=True, timeout=60)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn('cannot safely read Copy Files destination "PlugIns"',
                          rejected.stdout + rejected.stderr)
            self.assertEqual(project_file.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
