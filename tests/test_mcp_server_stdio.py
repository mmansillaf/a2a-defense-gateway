import json
import subprocess
import sys
from pathlib import Path


def test_mcp_server_stdio_initialize_and_tools_list(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parent.parent
    server_script = repo_root / "agents" / "mcp_server.py"
    ledger_path = tmp_path / "test_ledger.jsonl"

    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "compute_procedural_deadline",
                "arguments": {
                    "fecha_inicio": "2026-05-01",
                    "dias_plazo": 3,
                    "tipo_dias": "HABILES_JUDICIALES",
                },
            },
        },
    ]

    input_payload = "\n".join(json.dumps(r) for r in requests) + "\n"

    proc = subprocess.run(
        [sys.executable, str(server_script)],
        input=input_payload,
        text=True,
        capture_output=True,
        check=False,
        cwd=str(repo_root),
        env={"PYTHONPATH": str(repo_root / "agents"), "A2A_LEDGER_PATH": str(ledger_path)},
        timeout=10,
    )

    assert proc.returncode == 0
    lines = [line.strip() for line in proc.stdout.strip().split("\n") if line.strip()]
    assert len(lines) == 3

    init_res = json.loads(lines[0])
    assert init_res["id"] == 1
    assert init_res["result"]["serverInfo"]["name"] == "a2a-defense-monetization-gateway"

    tools_res = json.loads(lines[1])
    assert tools_res["id"] == 2
    tools = tools_res["result"]["tools"]
    assert len(tools) == 56

    call_res = json.loads(lines[2])
    assert call_res["id"] == 3
    content_text = json.loads(call_res["result"]["content"][0]["text"])
    assert "fecha_vencimiento" in content_text
