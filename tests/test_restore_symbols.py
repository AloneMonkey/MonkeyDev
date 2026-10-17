"""Compare restored methods with known compiler symbols, including dyld indices."""
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOL = Path(os.environ.get('MONKEYPARSER_BIN', ROOT / 'bin/monkeyparser'))


def commands(data):
    offset = 32
    for _ in range(struct.unpack_from('<I', data, 16)[0]):
        cmd, size = struct.unpack_from('<II', data, offset)
        yield cmd, offset
        offset += size


def symbols(data):
    offset = next(offset for cmd, offset in commands(data) if cmd == 2)
    symoff, count, stroff, size = struct.unpack_from('<4I', data, offset + 8)
    names = []
    values = {}
    for index in range(count):
        name, kind, section, desc, value = struct.unpack_from('<IBBHQ', data, symoff + index * 16)
        text = data[stroff + name:data.index(b'\0', stroff + name)].decode()
        names.append(text)
        if kind & 14 == 14:
            values[text] = value
    return names, values


def indirect_names(data):
    offset = next(offset for cmd, offset in commands(data) if cmd == 11)
    table, count = struct.unpack_from('<II', data, offset + 56)
    names, _ = symbols(data)
    return [names[value] if value < 0x80000000 else value
            for value in struct.unpack_from('<' + 'I' * count, data, table)]


@unittest.skipUnless(Path('/usr/bin/xcrun').exists(), 'requires Xcode')
class RestoreSymbolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='monkeydev-restore-symbols-')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name)
        sdk = subprocess.check_output(['xcrun', '--sdk', 'iphoneos', '--show-sdk-path'], text=True).strip()
        cls.inputs = {}
        for name, flags in [('modern', []), ('big-chained', ['-Wl,-no_objc_relative_method_lists']),
                            ('relative-legacy', ['-Wl,-no_fixup_chains']),
                            ('big-legacy', ['-Wl,-no_fixup_chains', '-Wl,-no_objc_relative_method_lists'])]:
            path = cls.root / name
            subprocess.run(['xcrun', 'clang', '-target', 'arm64-apple-ios15.0', '-isysroot', sdk,
                            '-fobjc-arc', '-O0', '-Wl,-no_objc_category_merging', *flags,
                            str(ROOT / 'tests/restore_symbols_fixture.m'), '-framework', 'Foundation',
                            '-o', str(path)], check=True)
            expected = {k: v for k, v in symbols(path.read_bytes())[1].items()
                        if k.startswith(('-[', '+['))}
            subprocess.run(['xcrun', 'strip', '-S', '-x', str(path)], check=True)
            cls.inputs[name] = (path.read_bytes(), expected)

    def setUp(self):
        self.case = Path(tempfile.mkdtemp(dir=self.root))
        self.input = self.case / 'input'
        self.output = self.case / 'output'

    def restore(self):
        return subprocess.run([str(TOOL), 'restoresymbol', '-t', str(self.input), '-o', str(self.output)],
                              capture_output=True, text=True, timeout=30)

    def test_known_methods_and_dynamic_link_indices(self):
        for name, (data, expected) in self.inputs.items():
            with self.subTest(name=name):
                self.input.write_bytes(data)
                self.output.unlink(missing_ok=True)
                self.assertFalse(any(x.startswith(('-[', '+[')) for x in symbols(data)[0]))
                result = self.restore()
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                after = self.output.read_bytes()
                restored = symbols(after)[1]
                for method, address in expected.items():
                    if 'MDRestoreExternal' in method and 'legacy' in name:
                        continue  # External categories without chained imports are reported/skipped.
                    self.assertEqual(restored.get(method), address, method)
                self.assertEqual(indirect_names(data), indirect_names(after))
                self.assertEqual(self.input.read_bytes(), data)
                repeated = self.case / 'repeated'
                result = subprocess.run([str(TOOL), 'restoresymbol', '-t', str(self.output), '-o', str(repeated)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(repeated.read_bytes(), after)

    def assert_rejected_unchanged(self, data):
        self.input.write_bytes(data)
        self.output.write_bytes(b'existing output')
        result = self.restore()
        self.assertGreater(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.input.read_bytes(), data)
        self.assertEqual(self.output.read_bytes(), b'existing output')

    def test_relative_method_count_out_of_range(self):
        data = bytearray(self.inputs['modern'][0])
        for cmd, offset in commands(data):
            if cmd != 0x19:
                continue
            count = struct.unpack_from('<I', data, offset + 64)[0]
            for i in range(count):
                section = offset + 72 + 80 * i
                if data[section:section + 16].rstrip(b'\0') == b'__objc_methlist':
                    fileoff = struct.unpack_from('<I', data, section + 48)[0]
                    struct.pack_into('<I', data, fileoff + 4, 0xffffffff)
                    self.assert_rejected_unchanged(data)
                    return
        self.fail('fixture has no relative method list')

    def test_unsupported_chained_pointer_format(self):
        data = bytearray(self.inputs['modern'][0])
        offset = next(offset for cmd, offset in commands(data) if cmd == 0x80000034)
        start = struct.unpack_from('<I', data, offset + 8)[0]
        starts = start + struct.unpack_from('<I', data, start + 4)[0]
        count = struct.unpack_from('<I', data, starts)[0]
        for i in range(count):
            relative = struct.unpack_from('<I', data, starts + 4 + i * 4)[0]
            if relative:
                struct.pack_into('<H', data, starts + relative + 6, 12)
                self.assert_rejected_unchanged(data)
                return
        self.fail('fixture has no chained starts')

    def test_output_alias_is_rejected(self):
        self.input.write_bytes(self.inputs['modern'][0])
        os.link(self.input, self.output)
        result = self.restore()
        self.assertGreater(result.returncode, 0)
        self.assertEqual(self.input.read_bytes(), self.inputs['modern'][0])

    def test_inplace_restore_preserves_executable_permissions(self):
        self.input.write_bytes(self.inputs['modern'][0])
        self.input.chmod(0o751)
        result = subprocess.run([str(TOOL), 'restoresymbol', '-t', str(self.input)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.input.stat().st_mode & 0o777, 0o751)
        self.assertIn('-[MDRestoreFixture add:]', symbols(self.input.read_bytes())[1])

    def test_resign_keeps_symbols_and_valid_linkedit(self):
        self.input.write_bytes(self.inputs['modern'][0])
        result = self.restore()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        before = symbols(self.output.read_bytes())[1]
        subprocess.run(['codesign', '--force', '--sign', '-', str(self.output)], check=True)
        subprocess.run(['codesign', '--verify', '--strict', str(self.output)], check=True)
        self.assertEqual(symbols(self.output.read_bytes())[1], before)
        result = subprocess.run([str(ROOT / 'bin/monkeyparser'), 'verify', '-t', str(self.output)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

if __name__ == '__main__':
    unittest.main()
