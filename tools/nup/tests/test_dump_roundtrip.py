from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from nup.access import extract_dump
from nup.pack import pack
from nup.read import NupReader


def file_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*") if path.is_file()
    }


class DumpRoundTripTests(unittest.TestCase):
    def test_pack_then_unpack_preserves_every_file_byte(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            source = work / "source"
            payloads = {
                "base/exefs/main": b"\x00NSO0\xff" + bytes(range(256)) * 4,
                "base/exefs/main.npdm": b"NPDM\x00binary\xffdata",
                "base/romfs/message.txt": "Switch 2 dump ✓\n".encode("utf-8"),
                "base/romfs/empty.bin": b"",
                "base/romfs/.listing": b"dump-tool listing bytes\x00",
                "base/romfs/repeated.bin": b"NUP round trip " * 32_000,
                "updates/458752/exefs/subsdk0": bytes(reversed(range(256))) * 17,
                "updates/458752/romfs/update.dat": b"update payload\x00\xff",
                "dlc/040074a01bf13001/0/romfs/dlc.dat": b"dlc payload\x00\xfe",
                "dlc/040074a01bf13001/7/romfs/second-dlc.dat": b"second add-on",
            }
            for relative, data in payloads.items():
                path = source / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            (source / "base" / "romfs" / "empty-folder").mkdir()

            package = work / "game.nup"
            restored = work / "restored"
            repacked = work / "repacked.nup"
            restored_again = work / "restored-again"
            pack(str(package), str(source), keep_listings=True)
            progress: list[tuple[int, int, str]] = []
            with NupReader(str(package)) as reader:
                written = extract_dump(reader, str(restored),
                                       lambda done, total, name: progress.append((done, total, name)))

            self.assertEqual(written, len(payloads))
            self.assertEqual(progress[-1][:2], (len(payloads), len(payloads)))
            self.assertEqual(file_hashes(source), file_hashes(restored))
            source_dirs = {
                path.relative_to(source).as_posix()
                for path in source.rglob("*") if path.is_dir()
            }
            restored_dirs = {
                path.relative_to(restored).as_posix()
                for path in restored.rglob("*") if path.is_dir()
            }
            self.assertEqual(source_dirs, restored_dirs)

            pack(str(repacked), str(restored), keep_listings=True)
            with NupReader(str(repacked)) as reader:
                extract_dump(reader, str(restored_again))
            self.assertEqual(file_hashes(source), file_hashes(restored_again))
            restored_again_dirs = {
                path.relative_to(restored_again).as_posix()
                for path in restored_again.rglob("*") if path.is_dir()
            }
            self.assertEqual(source_dirs, restored_again_dirs)


if __name__ == "__main__":
    unittest.main()
