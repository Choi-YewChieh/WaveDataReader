# Wave Data Reader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现波表文件（txt/csv/arb）读取，并输出逗号分隔字符串或带 TMC 头的小端有符号二进制，供功能验证与仪器下发。

**Architecture:** 单模块 `wave_reader.py`：`read_wave()` 解析为统一 `WaveData`（归一化 float ≈ [-1, 1]），经 `to_string()` / `to_binary()` 输出；`demo.py` 做 CLI 验证；`test_wave_reader.py` 覆盖读写与 TMC。

**Tech Stack:** Python 3.10+ 标准库（`struct`、`pathlib`、`argparse`）；测试用 `unittest`（无需安装 pytest）。

**Spec:** `docs/superpowers/specs/2026-07-14-wave-data-reader-design.md`

---

## File Structure

| File | Responsibility |
|------|----------------|
| `wave_reader.py` | `max_positive`, `WaveData`, `read_wave`, txt/csv/arb 解析, TMC 封装 |
| `test_wave_reader.py` | 单元测试（合成小文件 + 可选样例） |
| `demo.py` | CLI：读文件、打印预览、可选保存二进制 |
| `wave.txt` / `wave.csv` / `wave.arb` | 已有样例（只读，不修改） |

**Note:** 仓库当前可能尚未 `git init`。若无 `.git`，跳过各 Task 的 Commit 步骤，或先由用户确认后再初始化并提交。

---

### Task 1: Core helpers + WaveData.to_string / to_binary (TDD)

**Files:**
- Create: `test_wave_reader.py`
- Create: `wave_reader.py`

- [ ] **Step 1: Write failing tests for helpers and WaveData conversion**

Create `test_wave_reader.py`:

```python
import struct
import unittest
from pathlib import Path

from wave_reader import WaveData, max_positive, read_wave


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
        w = WaveData(points=[0.012566288, 0.02513208], source_path="x.txt", file_type="txt")
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

    def test_tmc_too_many_points(self):
        w = WaveData(points=[0.0] * (10**9), source_path="x", file_type="txt")
        # Avoid allocating 1e9: test via monkeypatch of point_count property if needed.
        # Instead construct and override:
        w._points = [0.0]  # will set point_count via property from points
        # Use a stub: only check the guard by calling with patched count — see implementation
        # For this plan: raise when len(points) >= 10**9 in to_binary.
        # Skip huge alloc: unit-test the header builder separately in Task 2 if preferred.
        pass  # replaced below


class TestTmcGuard(unittest.TestCase):
    def test_build_tmc_rejects_large_count(self):
        from wave_reader import build_tmc_header
        with self.assertRaises(ValueError):
            build_tmc_header(10**9)


if __name__ == "__main__":
    unittest.main()
```

Simplify `TestWaveDataOutput`: remove the broken huge-list test; keep `TestTmcGuard` only.

Final `test_wave_reader.py` for this task (complete file so far):

```python
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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd "d:\Code Project\WaveDataReader"
python -m unittest test_wave_reader.py -v
```

Expected: FAIL / ImportError（`wave_reader` 尚不存在或符号未定义）。

- [ ] **Step 3: Implement minimal `wave_reader.py` for these tests**

Create `wave_reader.py`:

```python
from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Union

PathLike = Union[str, Path]

_FMT = {1: "<b", 2: "<h", 4: "<i"}
_MAX_P = {1: 127, 2: 32767, 4: 2147483647}


def max_positive(bytes_per_point: int) -> int:
    if bytes_per_point not in _MAX_P:
        raise ValueError(
            f"unsupported bytes_per_point={bytes_per_point}; expected one of {sorted(_MAX_P)}"
        )
    return _MAX_P[bytes_per_point]


def build_tmc_header(point_count: int) -> bytes:
    if point_count < 0 or point_count >= 10**9:
        raise ValueError(f"TMC point_count out of range for 9 digits: {point_count}")
    return f"#9{point_count:09d}".encode("ascii")


def _quantize(points: Iterable[float], bytes_per_point: int) -> bytes:
    max_p = max_positive(bytes_per_point)
    fmt = _FMT[bytes_per_point]
    out = bytearray()
    for v in points:
        code = int(round(v * max_p))
        if code > max_p:
            code = max_p
        elif code < -max_p:
            code = -max_p
        out.extend(struct.pack(fmt, code))
    return bytes(out)


@dataclass
class WaveData:
    points: List[float]
    source_path: str
    file_type: str

    @property
    def point_count(self) -> int:
        return len(self.points)

    def to_string(self) -> str:
        # Preserve plain decimal text without spaces; use default float str then
        # strip scientific notation by formatting when needed.
        parts = []
        for v in self.points:
            s = format(v, ".15g")
            parts.append(s)
        return ",".join(parts)

    def to_binary(self, bytes_per_point: int = 2, with_tmc: bool = True) -> bytes:
        payload = _quantize(self.points, bytes_per_point)
        if not with_tmc:
            return payload
        return build_tmc_header(self.point_count) + payload


def read_wave(
    path: PathLike,
    file_type: Optional[str] = None,
    bytes_per_point: int = 2,
) -> WaveData:
    raise NotImplementedError("read_wave not implemented yet")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m unittest test_wave_reader.TestMaxPositive test_wave_reader.TestWaveDataOutput test_wave_reader.TestTmcGuard -v
```

Expected: PASS（全部通过）。

- [ ] **Step 5: Commit (if git available)**

```bash
git add wave_reader.py test_wave_reader.py
git commit -m "feat: add WaveData string/binary output and TMC helper"
```

若无 git 仓库则跳过。

---

### Task 2: read_wave for txt/csv

**Files:**
- Modify: `wave_reader.py`
- Modify: `test_wave_reader.py`

- [ ] **Step 1: Write failing tests for text readers**

Append to `test_wave_reader.py`:

```python
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
```

- [ ] **Step 2: Run new tests — expect fail**

```bash
python -m unittest test_wave_reader.TestReadText -v
```

Expected: FAIL（`NotImplementedError` 或解析未实现）。

- [ ] **Step 3: Implement txt/csv parsing in `read_wave`**

Replace `read_wave` and add helpers in `wave_reader.py`:

```python
def _infer_file_type(path: Path, file_type: Optional[str]) -> str:
    if file_type:
        return file_type.lower().lstrip(".")
    suffix = path.suffix.lower().lstrip(".")
    if suffix in {"txt", "csv", "arb"}:
        return suffix
    raise ValueError(f"unknown file type for {path}; pass file_type explicitly")


def _parse_text_points(path: Path) -> List[float]:
    points: List[float] = []
    text = path.read_text(encoding="utf-8")
    for line_no, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        tokens = line.split(",") if "," in line else [line]
        for tok in tokens:
            tok = tok.strip()
            if not tok:
                continue
            try:
                points.append(float(tok))
            except ValueError as exc:
                raise ValueError(
                    f"invalid number at {path}:{line_no}: {tok!r}"
                ) from exc
    return points


def read_wave(
    path: PathLike,
    file_type: Optional[str] = None,
    bytes_per_point: int = 2,
) -> WaveData:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"wave file not found: {p}")
    ftype = _infer_file_type(p, file_type)
    if ftype in {"txt", "csv"}:
        points = _parse_text_points(p)
        return WaveData(points=points, source_path=str(p), file_type=ftype)
    if ftype == "arb":
        raise NotImplementedError("arb reader in Task 3")
    raise ValueError(f"unsupported file_type: {ftype}")
```

- [ ] **Step 4: Run tests — expect pass**

```bash
python -m unittest test_wave_reader.TestReadText -v
```

Expected: PASS。

- [ ] **Step 5: Commit (if git available)**

```bash
git add wave_reader.py test_wave_reader.py
git commit -m "feat: read txt/csv wave point files"
```

---

### Task 3: read_wave for arb + round-trip

**Files:**
- Modify: `wave_reader.py`
- Modify: `test_wave_reader.py`

- [ ] **Step 1: Write failing arb tests**

Append:

```python
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
```

- [ ] **Step 2: Run — expect fail**

```bash
python -m unittest test_wave_reader.TestReadArb -v
```

Expected: FAIL（arb 未实现）。

- [ ] **Step 3: Implement arb reader**

In `wave_reader.py`:

```python
def _parse_arb_points(path: Path, bytes_per_point: int) -> List[float]:
    max_p = max_positive(bytes_per_point)
    fmt = _FMT[bytes_per_point]
    data = path.read_bytes()
    if len(data) % bytes_per_point != 0:
        raise ValueError(
            f"arb length {len(data)} not divisible by bytes_per_point={bytes_per_point}: {path}"
        )
    points: List[float] = []
    for i in range(0, len(data), bytes_per_point):
        (code,) = struct.unpack(fmt, data[i : i + bytes_per_point])
        points.append(code / max_p)
    return points
```

Update `read_wave` arb branch:

```python
    if ftype == "arb":
        points = _parse_arb_points(p, bytes_per_point)
        return WaveData(points=points, source_path=str(p), file_type=ftype)
```

- [ ] **Step 4: Run — expect pass**

```bash
python -m unittest test_wave_reader.TestReadArb -v
```

Expected: PASS（含本地 `wave.arb` 往返）。

- [ ] **Step 5: Commit (if git available)**

```bash
git add wave_reader.py test_wave_reader.py
git commit -m "feat: read arb binary wave points with normalize/roundtrip"
```

---

### Task 4: Sample txt/csv integration checks

**Files:**
- Modify: `test_wave_reader.py`

- [ ] **Step 1: Add sample file tests**

```python
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
```

- [ ] **Step 2: Run full suite**

```bash
python -m unittest test_wave_reader.py -v
```

Expected: ALL PASS。

- [ ] **Step 3: Commit (if git available)**

```bash
git add test_wave_reader.py
git commit -m "test: cover sample wave.txt/csv TMC output"
```

---

### Task 5: demo.py CLI

**Files:**
- Create: `demo.py`

- [ ] **Step 1: Implement demo CLI**

Create `demo.py`:

```python
#!/usr/bin/env python3
"""CLI to verify wave file reading and TMC binary output."""

from __future__ import annotations

import argparse
from pathlib import Path

from wave_reader import read_wave


def main() -> None:
    parser = argparse.ArgumentParser(description="Wave data reader demo")
    parser.add_argument("path", type=Path, help="wave file (.txt/.csv/.arb)")
    parser.add_argument("--file-type", default=None, help="override type: txt|csv|arb")
    parser.add_argument("--bytes", type=int, default=2, dest="bytes_per_point")
    parser.add_argument("--out", choices=["string", "binary"], default="string")
    parser.add_argument("--tmc", action="store_true", help="prepend TMC header (binary out)")
    parser.add_argument("--no-tmc", action="store_true", help="raw payload only")
    parser.add_argument("--save", type=Path, default=None, help="write output to file")
    parser.add_argument("--preview", type=int, default=8, help="string points to preview")
    args = parser.parse_args()

    wave = read_wave(args.path, file_type=args.file_type, bytes_per_point=args.bytes_per_point)
    print(f"file: {wave.source_path}")
    print(f"type: {wave.file_type}")
    print(f"points: {wave.point_count}")

    if args.out == "string":
        text = wave.to_string()
        preview = ",".join(text.split(",")[: args.preview])
        print(f"string preview ({args.preview} points): {preview}...")
        if args.save:
            args.save.write_text(text, encoding="utf-8")
            print(f"saved: {args.save}")
    else:
        with_tmc = True
        if args.no_tmc:
            with_tmc = False
        elif not args.tmc:
            with_tmc = True  # default on for binary per instrument use
        data = wave.to_binary(bytes_per_point=args.bytes_per_point, with_tmc=with_tmc)
        if with_tmc:
            print(f"TMC header: {data[:11]!r}")
            print(f"payload bytes: {len(data) - 11}")
        else:
            print(f"payload bytes: {len(data)}")
        print(f"total bytes: {len(data)}")
        if args.save:
            args.save.write_bytes(data)
            print(f"saved: {args.save}")


if __name__ == "__main__":
    main()
```

Default binary：带 TMC（仪器下发友好）。`--no-tmc` 关；`--tmc` 显式开（与默认一致）。

- [ ] **Step 2: Manual smoke**

```bash
python demo.py wave.txt --out string --preview 5
python demo.py wave.arb --bytes 2 --out binary --tmc --save out.bin
python -c "p=open('out.bin','rb').read(); print(p[:11], len(p))"
```

Expected: 打印点数与预览；`out.bin` 以 `b'#9000002000'` 一类头开头（样例 arb 为 2000 点）。

- [ ] **Step 3: Commit (if git available)**

```bash
git add demo.py
git commit -m "feat: add demo CLI for wave read and TMC export"
```

---

### Task 6: Spec coverage self-check

- [ ] **Step 1: Verify against spec checklist**

| Spec item | Covered by |
|-----------|------------|
| txt/csv read | Task 2 |
| arb read + normalize | Task 3 |
| string output | Task 1 |
| binary LE + quantize + clamp | Task 1 |
| TMC `#9` + 9-digit count | Task 1 |
| bytes_per_point 1/2/4 | Task 1 (`max_positive`) + arb Task 3 |
| errors (missing, type, line, length, TMC) | Tasks 1–3 |
| demo CLI | Task 5 |
| sample verification | Tasks 3–4 |

- [ ] **Step 2: Run full unittest once more**

```bash
python -m unittest test_wave_reader.py -v
```

Expected: PASS。

---

## Self-Review (plan vs spec)

1. **Spec coverage:** 全部表项有对应 Task；VISA/仪器通信明确 Out of Scope。  
2. **Placeholder scan:** 已去掉“huge list / pass”半成品测试；`read_wave` 分 Task 递进实现。  
3. **Type consistency:** `WaveData.points/source_path/file_type`、`to_string()`、`to_binary(bytes_per_point, with_tmc)`、`read_wave(path, file_type, bytes_per_point)`、`build_tmc_header`、`max_positive` 全程一致。  
4. **注：** txt/csv 字符串用 `format(v, ".15g")`，可能与原文精确字符略有差异；测试用 `AlmostEqual` / `.15g` 对齐，不以原文 byte-identical 字符串为硬要求（除非后续要求原样透传文本）。

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-14-wave-data-reader.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — 每个 Task 派一个新子代理，任务间两次审查，迭代快  
2. **Inline Execution** — 本会话按 executing-plans 连续执行，带检查点  

Which approach?
