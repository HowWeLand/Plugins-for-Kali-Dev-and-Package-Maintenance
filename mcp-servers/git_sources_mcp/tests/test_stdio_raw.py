"""The teaching test: speak raw JSON-RPC to the server over stdio.

No SDK on the client side — just a subprocess and newline-delimited JSON.
This is exactly what Claude Code / Codex CLI / Gemini CLI do under the hood
(design doc §1): initialize, tools/list, tools/call. If this test passes,
any MCP client can drive the server.
"""
import json
import os
import select
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"


def _send(proc, obj):
    proc.stdin.write(json.dumps(obj) + "\n")
    proc.stdin.flush()


def _recv(proc, timeout=30):
    ready, _, _ = select.select([proc.stdout], [], [], timeout)
    assert ready, "server did not respond within timeout"
    line = proc.stdout.readline()
    assert line, "server closed stdout"
    return json.loads(line)


def test_raw_jsonrpc_session(tmp_path):
    cfg = tmp_path / "sources.toml"
    cfg.write_text(
        f'workdir = "{tmp_path}/sources"\n'
        "[packages.demo]\n"
        'upstream = "https://example.invalid/demo.git"\n'
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC)
    proc = subprocess.Popen(
        [sys.executable, "-m", "git_sources_mcp", "--config", str(cfg)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        text=True,
    )
    try:
        # 1. Handshake: versions and capabilities are exchanged first.
        _send(proc, {
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "raw-test", "version": "0"},
            },
        })
        resp = _recv(proc)
        assert resp["id"] == 1
        assert resp["result"]["serverInfo"]["name"] == "git_sources_mcp"

        # 2. Client confirms it is ready (a notification: no id, no reply).
        _send(proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})

        # 3. Discovery: the tools and their schemas.
        _send(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        resp = _recv(proc)
        names = {t["name"] for t in resp["result"]["tools"]}
        assert names == {
            "gitsrc_list_packages", "gitsrc_sync", "gitsrc_log",
            "gitsrc_show_file", "gitsrc_list_tree", "gitsrc_grep",
            "gitsrc_find_init_scripts",
        }

        # 4. A call. list_packages needs no git and no network.
        _send(proc, {
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "gitsrc_list_packages", "arguments": {"params": {}}},
        })
        resp = _recv(proc)
        text = resp["result"]["content"][0]["text"]
        assert "demo" in text and "not synced" in text

        # 5. The allowlist rejection travels the wire as a result, not a crash.
        _send(proc, {
            "jsonrpc": "2.0", "id": 4, "method": "tools/call",
            "params": {
                "name": "gitsrc_log",
                "arguments": {"params": {"package": "unlisted"}},
            },
        })
        resp = _recv(proc)
        text = resp["result"]["content"][0]["text"]
        assert "not in the allowlist" in text
    finally:
        proc.terminate()
        proc.wait(timeout=10)
