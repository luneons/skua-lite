"""Entry point: python -m skua_lite [--mode farming] [--server Yorumi]."""
from __future__ import annotations

import argparse
import ipaddress
import os
import sys

from . import config, runner
from .mode import RunMode


def _is_loopback(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


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
    ap.add_argument("--mcp-only", action="store_true",
                    help="jalankan server MCP status saja; tidak login ke AQW")
    ap.add_argument("--mcp-host", default=None,
                    help="alamat bind MCP (default: SKUA_MCP_HOST atau 127.0.0.1)")
    ap.add_argument("--mcp-port", type=int, default=None,
                    help="port MCP (default: SKUA_MCP_PORT atau 8765)")
    ap.add_argument(
        "--mcp-token", default=None,
        help="Bearer token MCP (disarankan SKUA_MCP_TOKEN; argumen CLI terlihat di process list/history)",
    )
    args = ap.parse_args(argv)

    explicit_mcp_options = (args.mcp_host, args.mcp_port, args.mcp_token)
    if not args.mcp_only:
        if any(value is not None for value in explicit_mcp_options):
            ap.error("opsi --mcp-* hanya berlaku bersama --mcp-only")
        # MCP environment variables are deliberately ignored for normal startup.
        return runner.run(
            server_name=args.server,
            target_map=args.map_name,
            mode=None if args.mode is None else RunMode(args.mode),
        )

    host = args.mcp_host or os.getenv("SKUA_MCP_HOST") or "127.0.0.1"
    raw_port = args.mcp_port if args.mcp_port is not None else os.getenv("SKUA_MCP_PORT")
    if raw_port is None or raw_port == "":
        port = 8765
    else:
        try:
            port = int(raw_port)
        except (TypeError, ValueError):
            ap.error("SKUA_MCP_PORT/--mcp-port harus berupa angka 1-65535")
        if not 1 <= port <= 65535:
            ap.error("SKUA_MCP_PORT/--mcp-port harus berupa angka 1-65535")

    token = args.mcp_token or os.getenv("SKUA_MCP_TOKEN")
    if not token:
        ap.error("--mcp-token atau SKUA_MCP_TOKEN wajib saat MCP diaktifkan")

    if not _is_loopback(host):
        print(
            "PERINGATAN: MCP bind ke alamat non-loopback melalui HTTP plaintext; "
            "token Bearer dapat disadap. Gunakan TLS reverse proxy + firewall.",
            file=sys.stderr,
        )

    from .mcp_server import serve
    try:
        serve(host, port, token)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
