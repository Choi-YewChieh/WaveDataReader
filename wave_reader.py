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
        points = _parse_arb_points(p, bytes_per_point)
        return WaveData(points=points, source_path=str(p), file_type=ftype)
    raise ValueError(f"unsupported file_type: {ftype}")
