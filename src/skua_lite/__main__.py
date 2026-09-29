"""Entry point: python -m skua_lite [--mode farming] [--server Yorumi]."""
from __future__ import annotations

import argparse
import sys

from . import config, runner
from .mode import RunMode


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="skua-lite",
        description="Bot AQW ringan berbasis Python (headless, tanpa Flash).",
    )
    ap.add_argument(
        "--mode",
        choices=[mode.value for mode in RunMode],
        default=None,
        help="pilihan flow: assistant (Yulgar+AI/Admin) atau farming (tanpa AI/Admin).",
    )
    ap.add_argument("--server", default=config.DEFAULT_SERVER,
                    help=f"nama server AQW (default: {config.DEFAULT_SERVER})")
    ap.add_argument("--map", dest="map_name", default=None,
                    help="map tujuan join (default mengikuti mode yang dipilih)")
    args = ap.parse_args(argv)
    return runner.run(
        server_name=args.server,
        target_map=args.map_name,
        mode=None if args.mode is None else RunMode(args.mode),
    )


if __name__ == "__main__":
    sys.exit(main())
