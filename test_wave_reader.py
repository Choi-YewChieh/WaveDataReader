import struct
import tempfile
import unittest
from pathlib import Path

from wave_reader import WaveData, build_tmc_header, max_positive, read_wave


class TestMaxPositive(unittest.TestCase):
    def test_widths(self):
        self.assertEqual(max_positive(1), 127)
        self.assertEqual(max_positive(2), 32767)
        self.assertEqual(max_positive(4), 2147483647)

    def test_invalid(self):
        with self.assertRaises(ValueError):
            max_positive(3)


class TestWaveDataOutput(unittest.TestCase):
    def test_to_string(self):
        w = WaveData(
            points=[0.012566288, 0.02513208],
            source_path="x.txt",
            file_type="txt",
        )
        self.assertEqual(w.to_string(), "0.012566288,0.02513208")
        self.assertEqual(w.point_count, 2)

    def test_to_binary_int16_no_tmc(self):
        w = WaveData(points=[1.0, -1.0, 0.0], source_path="x", file_type="txt")
        payload = w.to_binary(bytes_per_point=2, with_tmc=False)
        self.assertEqual(payload, struct.pack("<hhh", 32767, -32767, 0))

    def test_to_binary_with_tmc(self):
        w = WaveData(points=[1.0, -1.0], source_path="x", file_type="txt")
        data = w.to_binary(bytes_per_point=2, with_tmc=True)
        self.assertTrue(data.startswith(b"#9000000002"))
        self.assertEqual(data[11:], struct.pack("<hh", 32767, -32767))

    def test_clamp(self):
        w = WaveData(points=[2.0, -2.0], source_path="x", file_type="txt")
        payload = w.to_binary(bytes_per_point=2, with_tmc=False)
        self.assertEqual(payload, struct.pack("<hh", 32767, -32767))


class TestTmcGuard(unittest.TestCase):
    def test_build_tmc_rejects_large_count(self):
        with self.assertRaises(ValueError):
            build_tmc_header(10**9)


class TestReadText(unittest.TestCase):
    def test_read_txt_lines(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "a.txt"
            p.write_text("0.012566288\n0.02513208\n\n0.037696879\n", encoding="utf-8")
            w = read_wave(p)
            self.assertEqual(w.file_type, "txt")
            self.assertEqual(w.point_count, 3)
            self.assertAlmostEqual(w.points[0], 0.012566288)
            self.assertEqual(
                w.to_string().split(",")[0],
                format(0.012566288, ".15g"),
            )

    def test_read_csv_inline_commas(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "a.csv"
            p.write_text("0.1,0.2\n0.3\n", encoding="utf-8")
            w = read_wave(p)
            self.assertEqual(w.points, [0.1, 0.2, 0.3])

    def test_bad_number_reports_line(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "bad.txt"
            p.write_text("1.0\nnot_a_number\n", encoding="utf-8")
            with self.assertRaises(ValueError) as ctx:
                read_wave(p)
            self.assertIn("2", str(ctx.exception))

    def test_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            read_wave(Path("definitely_missing_wave_xyz.txt"))

    def test_unknown_extension(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "a.bin"
            p.write_text("1.0\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                read_wave(p)


class TestReadArb(unittest.TestCase):
    def test_read_arb_normalized(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "a.arb"
            raw = struct.pack("<hhh", 32767, -32767, 0)
            p.write_bytes(raw)
            w = read_wave(p, bytes_per_point=2)
            self.assertEqual(w.file_type, "arb")
            self.assertEqual(w.point_count, 3)
            self.assertAlmostEqual(w.points[0], 1.0)
            self.assertAlmostEqual(w.points[1], -1.0)
            self.assertAlmostEqual(w.points[2], 0.0)

    def test_arb_roundtrip_payload(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "a.arb"
            raw = struct.pack("<hh", 32767, -32767)
            p.write_bytes(raw)
            w = read_wave(p, bytes_per_point=2)
            out = w.to_binary(bytes_per_point=2, with_tmc=False)
            self.assertEqual(out, raw)

    def test_arb_length_not_divisible(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "a.arb"
            p.write_bytes(b"\x00\x01\x02")
            with self.assertRaises(ValueError) as ctx:
                read_wave(p, bytes_per_point=2)
            msg = str(ctx.exception)
            self.assertIn("3", msg)
            self.assertIn("2", msg)

    def test_sample_arb_if_present(self):
        sample = Path(__file__).resolve().parent / "wave.arb"
        if not sample.is_file():
            self.skipTest("wave.arb sample not present")
        raw = sample.read_bytes()
        w = read_wave(sample, bytes_per_point=2)
        self.assertEqual(w.point_count, len(raw) // 2)
        self.assertEqual(w.to_binary(2, with_tmc=False), raw)


class TestSampleFiles(unittest.TestCase):
    def test_sample_txt(self):
        sample = Path(__file__).resolve().parent / "wave.txt"
        if not sample.is_file():
            self.skipTest("wave.txt not present")
        lines = [ln.strip() for ln in sample.read_text(encoding="utf-8").splitlines() if ln.strip()]
        w = read_wave(sample)
        self.assertEqual(w.point_count, len(lines))
        self.assertAlmostEqual(w.points[0], float(lines[0]))
        head = w.to_string().split(",")[:3]
        self.assertEqual(head[0], format(float(lines[0]), ".15g"))

    def test_sample_csv(self):
        sample = Path(__file__).resolve().parent / "wave.csv"
        if not sample.is_file():
            self.skipTest("wave.csv not present")
        w = read_wave(sample)
        self.assertGreater(w.point_count, 0)
        data = w.to_binary(2, with_tmc=True)
        self.assertTrue(data.startswith(b"#9"))
        count = int(data[2:11].decode("ascii"))
        self.assertEqual(count, w.point_count)
        self.assertEqual(len(data) - 11, w.point_count * 2)


if __name__ == "__main__":
    unittest.main()
