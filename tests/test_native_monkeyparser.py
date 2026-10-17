"""MONKEYPARSER_BIN=/path/to/monkeyparser python3 -m unittest discover -s tests -p test_native_monkeyparser.py -v"""
import os
from pathlib import Path
import plistlib
import struct
import subprocess
import tempfile
import unittest


TOOL = os.environ.get("MONKEYPARSER_BIN")


@unittest.skipUnless(TOOL, "set MONKEYPARSER_BIN to a native build")
class NativeParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = tempfile.TemporaryDirectory(prefix="monkeyparser-fixtures-")
        cls.addClassCleanup(cls.scratch.cleanup)
        cls.root = Path(cls.scratch.name)
        source = cls.root / "main.c"
        source.write_text("int main(void) { return 0; }\n")
        sdk = subprocess.check_output(["xcrun", "--sdk", "iphoneos", "--show-sdk-path"], text=True).strip()
        cls.fixture = cls.root / "fixture"
        subprocess.run(["xcrun", "clang", "-target", "arm64-apple-ios15.0", "-isysroot", sdk,
                        "-Wl,-headerpad,0x1000", str(source), "-o", str(cls.fixture)], check=True)
        cls.original = cls.fixture.read_bytes()

    def setUp(self):
        self.case = Path(tempfile.mkdtemp(dir=self.root))
        self.input = self.case / "input"
        self.input.write_bytes(self.original)
        self.output = self.case / "output"

    def run_tool(self, *args):
        env = {**os.environ, "MONKEYDEV_CLASS_DUMP": "NO", "MONKEYDEV_RESTORE_SYMBOL": "NO"}
        return subprocess.run([TOOL, *map(str, args)], capture_output=True, text=True, timeout=5, env=env)

    def install(self, payload="@executable_path/Frameworks/libSmoke.dylib", output=True):
        args = ["install", "-c", "load", "-p", payload, "-t", self.input]
        if output:
            args += ["-o", self.output]
        return self.run_tool(*args)

    def assert_rejected_unchanged(self):
        before = self.input.read_bytes()
        self.output.write_bytes(b"existing output must survive")
        result = self.install()
        self.assertGreater(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.input.read_bytes(), before)
        self.assertEqual(self.output.read_bytes(), b"existing output must survive")

    def test_inject_and_repeat_preserves_input(self):
        self.assertEqual(self.install().returncode, 0)
        self.assertEqual(self.input.read_bytes(), self.original)
        self.input = self.output
        before = self.input.read_bytes()
        self.assertEqual(self.install(output=False).returncode, 0)
        self.assertEqual(self.input.read_bytes(), before)
        loads = subprocess.check_output(["xcrun", "otool", "-L", str(self.input)], text=True)
        self.assertEqual(loads.count("@executable_path/Frameworks/libSmoke.dylib"), 1)

    def test_no_header_space_preserves_files(self):
        self.output.write_bytes(b"existing output must survive")
        result = self.install("@executable_path/" + "a" * 20000)
        self.assertGreater(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.input.read_bytes(), self.original)
        self.assertEqual(self.output.read_bytes(), b"existing output must survive")

    def test_same_output_path_is_rejected(self):
        self.output = self.input
        result = self.install()
        self.assertGreater(result.returncode, 0)
        self.assertEqual(self.input.read_bytes(), self.original)

    def test_hardlink_output_is_rejected(self):
        os.link(self.input, self.output)
        result = self.install()
        self.assertGreater(result.returncode, 0)
        self.assertEqual(self.input.read_bytes(), self.original)

    def test_truncated_header(self):
        self.input.write_bytes(self.original[:4])
        self.assert_rejected_unchanged()

    def test_invalid_magic(self):
        self.input.write_bytes(b"not a Mach-O file")
        self.assert_rejected_unchanged()

    def test_zero_command_size(self):
        data = bytearray(self.original)
        struct.pack_into("<I", data, 36, 0)
        self.input.write_bytes(data)
        self.assert_rejected_unchanged()

    def test_command_table_outside_file(self):
        data = bytearray(self.original)
        struct.pack_into("<I", data, 20, 0xFFFFFFFF)
        self.input.write_bytes(data)
        self.assert_rejected_unchanged()

    def test_arm64e_is_explicitly_unsupported(self):
        data = bytearray(self.original)
        struct.pack_into("<I", data, 8, 2)
        self.input.write_bytes(data)
        self.assert_rejected_unchanged()

    def test_fat_is_explicitly_unsupported(self):
        self.input.write_bytes(struct.pack(">II", 0xCAFEBABE, 1) + b"\0" * 100)
        self.assert_rejected_unchanged()

    def test_invalid_dylib_name_offset(self):
        data = bytearray(self.original)
        offset = 32
        while offset < 32 + struct.unpack_from("<I", data, 20)[0]:
            kind, size = struct.unpack_from("<II", data, offset)
            if kind == 0xC:
                struct.pack_into("<I", data, offset + 8, size)
                break
            offset += size
        else:
            self.fail("fixture has no LC_LOAD_DYLIB")
        self.input.write_bytes(data)
        self.assert_rejected_unchanged()

    def test_segment_outside_file(self):
        data = bytearray(self.original)
        offset = 32
        while offset < 32 + struct.unpack_from("<I", data, 20)[0]:
            kind, size = struct.unpack_from("<II", data, offset)
            if kind == 0x19:
                struct.pack_into("<Q", data, offset + 40, len(data) + 1)
                break
            offset += size
        self.input.write_bytes(data)
        self.assert_rejected_unchanged()

    def test_encrypted_image_rejected(self):
        data = bytearray(self.original)
        end = 32 + struct.unpack_from("<I", data, 20)[0]
        data[end:end + 24] = struct.pack("<IIIIII", 0x2C, 24, 0, 0, 1, 0)
        struct.pack_into("<I", data, 16, struct.unpack_from("<I", data, 16)[0] + 1)
        struct.pack_into("<I", data, 20, struct.unpack_from("<I", data, 20)[0] + 24)
        self.input.write_bytes(data)
        self.assert_rejected_unchanged()

    def test_unknown_load_command_type(self):
        self.output.write_bytes(b"existing output must survive")
        result = self.run_tool("install", "-c", "invalid", "-p", "@rpath/test.dylib",
                               "-t", self.input, "-o", self.output)
        self.assertGreater(result.returncode, 0)
        self.assertEqual(self.output.read_bytes(), b"existing output must survive")

    def test_failed_output_copy_is_an_error(self):
        self.output = self.case / "missing-parent" / "output"
        result = self.install()
        self.assertGreater(result.returncode, 0)
        self.assertEqual(self.input.read_bytes(), self.original)

    def test_verify_is_read_only(self):
        app = self.case / "Example.app"
        app.mkdir()
        executable = app / "Example"
        executable.write_bytes(self.original)
        (app / "Info.plist").write_bytes(plistlib.dumps({"CFBundleExecutable": "Example"}))
        result = self.run_tool("verify", "-t", app)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(executable.read_bytes(), self.original)

    def test_verify_rejects_bad_nested_image_without_writes(self):
        app = self.case / "Example.app"
        app.mkdir()
        executable = app / "Example"
        executable.write_bytes(self.original)
        (app / "Info.plist").write_bytes(plistlib.dumps({"CFBundleExecutable": "Example"}))
        nested = app / "broken.dylib"
        nested.write_bytes(self.original[:4])
        result = self.run_tool("verify", "-t", app)
        self.assertGreater(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(executable.read_bytes(), self.original)
        self.assertEqual(nested.read_bytes(), self.original[:4])


if __name__ == "__main__":
    unittest.main()
