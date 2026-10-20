"""Verify path SDK ABI and absence of a runtime dependency when unused."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SDK = ROOT / 'Librarys/roothide'

@unittest.skipUnless(shutil.which('xcrun'), 'requires Xcode')
class RootHideSDKTests(unittest.TestCase):
    def command(self, args):
        result = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def test_used_and_unused_api_in_executables_and_dylibs(self):
        sysroot = self.command(['xcrun', '--sdk', 'iphoneos', '--show-sdk-path']).strip()
        sources = {
            'c': '#include <roothide.h>\nconst char *path(void) { return jbroot("/Library/Fixture"); }\n',
            'mm': '#include <roothide.h>\nNSString *objcPath(void) { return jbroot(@"/Library/Fixture"); }\nstd::string cppPath(void) { return jbroot(std::string("/Library/Fixture")); }\n',
        }
        with tempfile.TemporaryDirectory(prefix='md roothide sdk ') as tmp:
            work = Path(tmp)
            constructor = work / 'constructor.c'
            constructor.write_text('#include <stdio.h>\n__attribute__((constructor)) static void init(void) { puts("third-party initializer"); }\n')
            self.command(['xcrun', 'clang', '-target', 'arm64-apple-ios15.0', '-isysroot', sysroot,
                          '-dynamiclib', str(constructor), '-Wl,-install_name,@rpath/libConstructor.dylib',
                          '-o', str(work / 'libConstructor.dylib')])
            for language, body in sources.items():
                for used in (False, True):
                    for dylib in (False, True):
                        with self.subTest(language=language, used=used, dylib=dylib):
                            source = work / ('fixture.' + language)
                            text = body if used else '#include <roothide.h>\n'
                            text += 'int main(void) { return 0; }\n'
                            source.write_text(text)
                            binary = work / 'fixture'
                            args = ['xcrun', 'clang++' if language == 'mm' else 'clang',
                                    '-target', 'arm64-apple-ios15.0', '-isysroot', sysroot,
                                    '-I' + str(SDK / 'include'), '-L' + str(SDK),
                                    '-fmodules', '-fmodules-cache-path=' + str(work / 'ModuleCache'),
                                    '-L' + str(work), '-lConstructor']
                            if language == 'mm':
                                args += ['-fcxx-modules', '-fobjc-arc', '-framework', 'Foundation']
                            if dylib:
                                args += ['-dynamiclib']
                            self.command(args + [str(source), '-o', str(binary)])
                            linked = self.command(['otool', '-L', str(binary)])
                            self.assertIn('@rpath/libConstructor.dylib', linked)
                            dependency = '@loader_path/.jbroot/usr/lib/libroothide.dylib'
                            if used:
                                self.assertIn(dependency, linked)
                                self.assertIn('jbroot', self.command(['nm', '-u', str(binary)]))
                            else:
                                self.assertNotIn('libroothide', linked)
                                self.assertNotIn('jbroot', self.command(['nm', '-u', str(binary)]))

if __name__ == '__main__':
    unittest.main()
