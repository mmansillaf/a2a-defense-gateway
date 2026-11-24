import pytest
from agents.moltbook_interactive_executor import (
    MoltbookInteractiveExecutor,
    ExecutionCommand,
    CommandType,
)


@pytest.fixture
def executor():
    return MoltbookInteractiveExecutor(max_requests_per_hour=5)


def test_parse_run_command_code_block(executor):
    text = "@a2adefensegateway run ```python\nprint(2 + 2)\n```"
    cmd = executor.parse_command(text, commenter="alice")
    assert cmd is not None
    assert cmd.command_type == CommandType.RUN_CODE
    assert "print(2 + 2)" in cmd.payload


def test_parse_run_command_inline(executor):
    text = "@a2adefensegateway run print(sum([1, 2, 3]))"
    cmd = executor.parse_command(text, commenter="bob")
    assert cmd is not None
    assert cmd.command_type == CommandType.RUN_CODE
    assert "print(sum([1, 2, 3]))" in cmd.payload


def test_parse_tool_command(executor):
    text = '@a2adefensegateway tool compute_procedural_deadline {"start_date": "2026-11-25", "business_days": 5}'
    cmd = executor.parse_command(text, commenter="charlie")
    assert cmd is not None
    assert cmd.command_type == CommandType.TOOL_CALL
    assert cmd.tool_name == "compute_procedural_deadline"
    assert "business_days" in cmd.payload


def test_parse_ping_and_help(executor):
    cmd_ping = executor.parse_command("@a2adefensegateway ping", commenter="dave")
    assert cmd_ping.command_type == CommandType.PING

    cmd_help = executor.parse_command("@a2adefensegateway help", commenter="dave")
    assert cmd_help.command_type == CommandType.HELP


def test_non_command_returns_none(executor):
    text = "Great post about L402 and zero trust! Thanks @a2adefensegateway"
    cmd = executor.parse_command(text, commenter="eve")
    assert cmd is None


def test_rate_limiting(executor):
    commenter = "spammer_bot"
    text = "@a2adefensegateway run print('hello')"
    for _ in range(5):
        reply = executor.handle_interaction(text, commenter=commenter)
        assert "Límite de tasa" not in reply

    # 6th attempt should be blocked
    reply_blocked = executor.handle_interaction(text, commenter=commenter)
    assert "Límite de tasa excedido" in reply_blocked


def test_security_rejection_malicious_ast(executor):
    malicious_code = "@a2adefensegateway run import os; os.system('cat /etc/passwd')"
    reply = executor.handle_interaction(malicious_code, commenter="attacker")
    assert "RECHAZADO POR SEGURIDAD" in reply
    assert "vulnerabilidad" in reply.lower() or "bloquead" in reply.lower()


def test_safe_execution_success(executor):
    code = "@a2adefensegateway run result = [x**2 for x in range(5)]; print(result)"
    reply = executor.handle_interaction(code, commenter="student_agent")
    assert "EJECUCIÓN DETERMINISTA EXITOSA" in reply
    assert "[0, 1, 4, 9, 16]" in reply
    assert "Why-Trail" in reply
