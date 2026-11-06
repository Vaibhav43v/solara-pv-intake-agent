"""Deterministic regulatory clock. NEVER delegated to an LLM.

Day 0 = the earliest date ANY Solara employee or channel became aware of the
minimum information (e.g. the sales rep's visit date, not the date the note
reached the PV inbox). Rules come from data/market_rules.json (illustrative)."""
import datetime as dt
import json
import pathlib

RULES = json.loads((pathlib.Path(__file__).parent.parent / "data" / "market_rules.json").read_text())


def compute_clock(awareness_date: str, receipt_date: str, market: str, expedited: bool, today: str = None):
    rule = RULES["markets"].get(market or RULES["default_market"], RULES["markets"][RULES["default_market"]])
    dates = [d for d in (awareness_date, receipt_date) if d]
    day0 = min(dt.date.fromisoformat(d) for d in dates) if dates else None
    out = {"market": market, "authority": rule["authority"], "day0": day0.isoformat() if day0 else None,
           "handoff_lag_days": None, "expedited": expedited, "due_date": None, "days_left": None,
           "rule": f"{rule['serious_expedited_days']} {rule['clock_basis']}"}
    if awareness_date and receipt_date:
        out["handoff_lag_days"] = (dt.date.fromisoformat(receipt_date) - dt.date.fromisoformat(awareness_date)).days
    if expedited and day0:
        due = day0 + dt.timedelta(days=rule["serious_expedited_days"])
        out["due_date"] = due.isoformat()
        ref = dt.date.fromisoformat(today) if today else dt.date.today()
        out["days_left"] = (due - ref).days
    return out
