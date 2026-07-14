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
