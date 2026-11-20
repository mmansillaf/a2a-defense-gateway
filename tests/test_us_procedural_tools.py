"""
Test Suite for US Federal and State Procedural Deadline Calculation Engine.
Verifies FRCP Rule 6, FRAP Rule 26, 5 U.S.C. § 6103, and State Rules.
"""

from datetime import date

from us_procedural_tools import (
    USDeadlineInput,
    compute_us_procedural_deadline,
    get_us_federal_holidays,
)


def test_federal_holidays_in_lieu_rule():
    """Verifica que los feriados federales apliquen correctamente la regla in-lieu."""
    # En 2026, July 4 es Sábado -> Observado Viernes July 3
    holidays_2026 = get_us_federal_holidays(2026)
    assert date(2026, 7, 3) in holidays_2026  # Independence Day observed Friday

    # Thanksgiving 2026 es Nov 26 (4to jueves)
    assert date(2026, 11, 26) in holidays_2026

    # Juneteenth 2026 es Viernes June 19
    assert date(2026, 6, 19) in holidays_2026


def test_frcp_6_regular_business_day_no_roll():
    """Un plazo que vence en día hábil no feriado no debe rolar."""
    # Lunes 2026-06-01 + 14 días = Lunes 2026-06-15 (Hábil)
    payload = USDeadlineInput(
        trigger_date=date(2026, 6, 1),
        period_days=14,
        jurisdiction="FEDERAL",
        service_method="ELECTRONIC",
    )
    res = compute_us_procedural_deadline(payload)
    assert res.deadline_date == date(2026, 6, 15)
    assert res.terminal_day_rolled is False
    assert res.service_extension_days == 0
    assert "23:59:59 (America/New_York)" in res.deadline_time


def test_frcp_6_weekend_roll_forward():
    """Un plazo que vence en domingo debe rolar al lunes siguiente."""
    # Lunes 2026-06-01 + 20 días = Domingo 2026-06-21 -> Rola al Lunes 2026-06-22
    payload = USDeadlineInput(
        trigger_date=date(2026, 6, 1),
        period_days=20,
        jurisdiction="FEDERAL",
        service_method="ELECTRONIC",
    )
    res = compute_us_procedural_deadline(payload)
    assert res.deadline_date == date(2026, 6, 22)
    assert res.terminal_day_rolled is True
    assert "Sunday" in (res.roll_reason or "")


def test_frcp_6d_three_day_mail_extension():
    """Notificación por correo suma 3 días bajo FRCP 6(d)."""
    # Lunes 2026-06-01 + 14 días + 3 días correo = Jueves 2026-06-18
    payload = USDeadlineInput(
        trigger_date=date(2026, 6, 1),
        period_days=14,
        jurisdiction="FEDERAL",
        service_method="POSTAL_MAIL",
    )
    res = compute_us_procedural_deadline(payload)
    assert res.service_extension_days == 3
    assert res.deadline_date == date(2026, 6, 18)
    assert any("FRCP Rule 6(d)" in cit for cit in res.statutory_citations)


def test_california_ccp_electronic_service_extension():
    """En California, el servicio electrónico añade 2 días bajo CCP § 1010.6."""
    # Lunes 2026-06-01 + 10 días + 2 días = Sábado 2026-06-13 -> Rola al Lunes 2026-06-15
    payload = USDeadlineInput(
        trigger_date=date(2026, 6, 1),
        period_days=10,
        jurisdiction="CALIFORNIA",
        service_method="ELECTRONIC",
        court_timezone="America/Los_Angeles",
    )
    res = compute_us_procedural_deadline(payload)
    assert res.service_extension_days == 2
    assert res.deadline_date == date(2026, 6, 15)
    assert res.terminal_day_rolled is True
    assert any("1010.6" in cit for cit in res.statutory_citations)
    assert "America/Los_Angeles" in res.deadline_time


def test_new_york_cplr_mail_extension():
    """En Nueva York, servicio por correo añade 5 días bajo CPLR § 2103(b)(2)."""
    payload = USDeadlineInput(
        trigger_date=date(2026, 6, 1),
        period_days=20,
        jurisdiction="NEW_YORK",
        service_method="POSTAL_MAIL",
    )
    res = compute_us_procedural_deadline(payload)
    assert res.service_extension_days == 5
    # 2026-06-01 + 25 días = Viernes 2026-06-26
    assert res.deadline_date == date(2026, 6, 26)
    assert any("2103(b)(2)" in cit for cit in res.statutory_citations)


def test_texas_trcp_mail_extension():
    """En Texas, servicio por correo añade 3 días bajo TRCP 21a."""
    payload = USDeadlineInput(
        trigger_date=date(2026, 6, 1),
        period_days=14,
        jurisdiction="TEXAS",
        service_method="POSTAL_MAIL",
    )
    res = compute_us_procedural_deadline(payload)
    assert res.service_extension_days == 3
    assert res.deadline_date == date(2026, 6, 18)
    assert any("21a" in cit for cit in res.statutory_citations)
