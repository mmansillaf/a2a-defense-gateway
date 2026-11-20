"""
US Federal and State Procedural Deadline Calculation Engine.
Enforces FRCP Rule 6, FRAP Rule 26, FRCrP Rule 45, FRBP Rule 9006,
and State Court Rules (California CCP, New York CPLR, Texas TRCP, Florida Fla. R. Jud. Admin. 2.514).
Erradicates computational and calendar hallucinations for US legal proceedings.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel, Field


def get_us_federal_holidays(year: int) -> set[date]:
    """Retorna los 11 feriados federales oficiales (5 U.S.C. § 6103) con regla in-lieu observada."""
    fixed = {
        date(year, 1, 1),   # New Year's Day
        date(year, 6, 19),  # Juneteenth National Independence Day
        date(year, 7, 4),   # Independence Day
        date(year, 11, 11), # Veterans Day
        date(year, 12, 25), # Christmas Day
    }

    # Floating Mondays
    # Martin Luther King Jr. Day: 3rd Monday in January
    mlk = date(year, 1, 1) + timedelta(days=(0 - date(year, 1, 1).weekday() + 7) % 7 + 14)
    # Washington's Birthday (Presidents' Day): 3rd Monday in February
    presidents = date(year, 2, 1) + timedelta(days=(0 - date(year, 2, 1).weekday() + 7) % 7 + 14)
    # Memorial Day: Last Monday in May
    last_may = date(year, 5, 31)
    memorial = last_may - timedelta(days=(last_may.weekday() - 0) % 7)
    # Labor Day: 1st Monday in September
    labor = date(year, 9, 1) + timedelta(days=(0 - date(year, 9, 1).weekday() + 7) % 7)
    # Columbus Day: 2nd Monday in October
    columbus = date(year, 10, 1) + timedelta(days=(0 - date(year, 10, 1).weekday() + 7) % 7 + 7)
    # Thanksgiving: 4th Thursday in November
    thanksgiving = date(year, 11, 1) + timedelta(days=(3 - date(year, 11, 1).weekday() + 7) % 7 + 21)

    all_raw = fixed | {mlk, presidents, memorial, labor, columbus, thanksgiving}

    # Regla In-Lieu (5 U.S.C. § 6103(b)): Sábado -> Viernes anterior; Domingo -> Lunes siguiente
    observed: set[date] = set()
    for h in all_raw:
        if h.weekday() == 5:  # Saturday
            observed.add(h - timedelta(days=1))
        elif h.weekday() == 6:  # Sunday
            observed.add(h + timedelta(days=1))
        else:
            observed.add(h)

    return observed


def get_state_holidays(year: int, jurisdiction: str) -> set[date]:
    """Retorna feriados legales específicos adicionales por estado."""
    base = get_us_federal_holidays(year)
    extra: set[date] = set()

    if jurisdiction == "CALIFORNIA":
        # César Chávez Day: March 31
        extra.add(date(year, 3, 31))
        # Day after Thanksgiving (4th Friday of November)
        nov1 = date(year, 11, 1)
        thurs4 = nov1 + timedelta(days=(3 - nov1.weekday() + 7) % 7 + 21)
        extra.add(thurs4 + timedelta(days=1))
    elif jurisdiction == "NEW_YORK":
        # Lincoln's Birthday: Feb 12
        extra.add(date(year, 2, 12))
    elif jurisdiction == "TEXAS":
        # Texas Independence Day: March 2
        extra.add(date(year, 3, 2))
        # San Jacinto Day: April 21
        extra.add(date(year, 4, 21))
        # Lyndon B. Johnson Day: August 27
        extra.add(date(year, 8, 27))

    # Regla in-lieu para feriados estatales
    observed_extra: set[date] = set()
    for h in extra:
        if h.weekday() == 5:
            observed_extra.add(h - timedelta(days=1))
        elif h.weekday() == 6:
            observed_extra.add(h + timedelta(days=1))
        else:
            observed_extra.add(h)

    return base | observed_extra


class USDeadlineInput(BaseModel):
    trigger_date: date = Field(..., description="Fecha inicial del acto o notificación (YYYY-MM-DD)")
    period_days: int = Field(..., gt=0, le=730, description="Cantidad de días a computar")
    jurisdiction: Literal["FEDERAL", "CALIFORNIA", "NEW_YORK", "TEXAS", "FLORIDA"] = Field(
        default="FEDERAL",
        description="Jurisdicción procesal aplicable",
    )
    service_method: Literal["ELECTRONIC", "POSTAL_MAIL", "OVERNIGHT_DELIVERY", "HAND_DELIVERY"] = Field(
        default="ELECTRONIC",
        description="Método de notificación procesal",
    )
    court_rule: Literal["FRCP_6", "FRAP_26", "FRCrP_45", "FRBP_9006", "STATE_DEFAULT"] = Field(
        default="FRCP_6",
        description="Cuerpo normativo específico",
    )
    court_timezone: str = Field(
        default="America/New_York",
        description="Zona horaria IANA del tribunal (ej. America/New_York, America/Los_Angeles)",
    )


class USDeadlineOutput(BaseModel):
    doc_id: str
    trigger_date: date
    deadline_date: date
    deadline_time: str
    base_period_days: int
    service_extension_days: int
    total_calendar_days_elapsed: int
    terminal_day_rolled: bool
    roll_reason: str | None
    discounted_legal_holidays: list[date]
    jurisdiction: str
    statutory_citations: list[str]


def compute_us_procedural_deadline(payload: USDeadlineInput) -> USDeadlineOutput:
    """
    Calcula de forma determinista la fecha y hora de vencimiento procesal en EE.UU.
    Cumple con el estándar post-2009 de exclusión de día 0, conteo continuo y roll-forward terminal.
    """
    service_ext = 0
    citations: list[str] = []

    # 1. Extensiones estatutarias por método de notificación (The "Mailbox / Service" Rules)
    if payload.jurisdiction == "FEDERAL":
        if payload.service_method == "POSTAL_MAIL":
            service_ext = 3
            citations.append("FRCP Rule 6(d) / FRAP Rule 26(c) (+3 days added for service by mail)")
    elif payload.jurisdiction == "CALIFORNIA":
        if payload.service_method == "ELECTRONIC":
            service_ext = 2
            citations.append("Cal. CCP § 1010.6(a)(4)(A) (+2 court days for electronic service)")
        elif payload.service_method == "POSTAL_MAIL":
            service_ext = 5
            citations.append("Cal. CCP § 1013(a) (+5 calendar days for mail within California)")
        elif payload.service_method == "OVERNIGHT_DELIVERY":
            service_ext = 2
            citations.append("Cal. CCP § 1013(c) (+2 calendar days for express overnight delivery)")
    elif payload.jurisdiction == "NEW_YORK":
        if payload.service_method == "POSTAL_MAIL":
            service_ext = 5
            citations.append("NY CPLR § 2103(b)(2) (+5 days for service by regular mail)")
        elif payload.service_method == "OVERNIGHT_DELIVERY":
            service_ext = 1
            citations.append("NY CPLR § 2103(b)(6) (+1 business day for overnight delivery)")
    elif payload.jurisdiction == "TEXAS":
        if payload.service_method in ("POSTAL_MAIL", "OVERNIGHT_DELIVERY"):
            service_ext = 3
            citations.append("Tex. R. Civ. P. 21a(c) (+3 days for mail or commercial delivery)")
    elif payload.jurisdiction == "FLORIDA" and payload.service_method == "POSTAL_MAIL":
        service_ext = 5
        citations.append("Fla. R. Jud. Admin. 2.514(b) (+5 days for service by mail)")

    total_days = payload.period_days + service_ext

    # 2. Cómputo base: Excluir día inicial (Día 0) y contar días corridos
    current_date = payload.trigger_date + timedelta(days=total_days)
    citations.append(f"{payload.court_rule}(a)(1)(A)-(B) (Exclude trigger day, count every intermediate day)")

    # 3. Identificación de feriados en la ventana temporal relevante
    holidays = (
        get_state_holidays(current_date.year, payload.jurisdiction)
        | get_state_holidays(current_date.year + 1, payload.jurisdiction)
        | get_state_holidays(current_date.year - 1, payload.jurisdiction)
    )

    # 4. Regla Terminal (Roll-forward): Si el último día es sábado, domingo o feriado
    rolled = False
    roll_reason: str | None = None
    discounted_holidays: list[date] = []

    while current_date.weekday() in (5, 6) or current_date in holidays:
        rolled = True
        if current_date.weekday() == 5:
            roll_reason = f"Final day fell on Saturday ({current_date.isoformat()})"
        elif current_date.weekday() == 6:
            roll_reason = f"Final day fell on Sunday ({current_date.isoformat()})"
        else:
            discounted_holidays.append(current_date)
            roll_reason = f"Final day fell on legal holiday ({current_date.isoformat()})"
        current_date += timedelta(days=1)

    if rolled:
        citations.append(f"{payload.court_rule}(a)(1)(C) (Extended to next accessible court day)")

    elapsed = (current_date - payload.trigger_date).days

    return USDeadlineOutput(
        doc_id=f"US-DEADLINE-{payload.jurisdiction}-{current_date.isoformat()}",
        trigger_date=payload.trigger_date,
        deadline_date=current_date,
        deadline_time=f"23:59:59 ({payload.court_timezone})",
        base_period_days=payload.period_days,
        service_extension_days=service_ext,
        total_calendar_days_elapsed=elapsed,
        terminal_day_rolled=rolled,
        roll_reason=roll_reason,
        discounted_legal_holidays=discounted_holidays,
        jurisdiction=payload.jurisdiction,
        statutory_citations=citations,
    )
