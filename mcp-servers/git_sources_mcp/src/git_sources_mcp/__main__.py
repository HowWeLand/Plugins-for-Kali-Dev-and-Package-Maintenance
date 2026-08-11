"""Entry point: python -m git_sources_mcp --config /abs/path/sources.toml

stdio discipline (design doc §3): stdout belongs to the JSON-RPC stream, so
all diagnostics — including config errors at startup — go to stderr.
"""
from __future__ import annotations

import argparse
import logging
import sys

from .config import ConfigError, load_config
from .tools import init_state, mcp


def main() -> int:
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s: %(message)s",
    )
    parser = argparse.ArgumentParser(
        prog="git_sources_mcp",
        description="Scoped read-only MCP server for allowlisted git repos.",
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Absolute path to sources.toml (the allowlist).",
    )
    args = parser.parse_args()

    try:
        cfg = load_config(args.config)
    except ConfigError as e:
        logging.error("%s", e)
        return 2

    init_state(cfg)
    logging.info(
        "git_sources_mcp starting: %d package(s) allowlisted, workdir=%s",
        len(cfg.packages),
        cfg.workdir,
    )
    mcp.run()  # stdio transport
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
