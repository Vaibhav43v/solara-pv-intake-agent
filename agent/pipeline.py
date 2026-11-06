"""Intake agent pipeline: guard -> extract (rules or LLM) -> validate -> triage -> clock -> draft.
The agent PROPOSES. A PV processor / safety physician DECIDES. Nothing is submitted."""
import re
from . import guards, clock, audit
from .extract import extract, RSI

VERSION = "solara-intake-poc 0.2 (rules)"


def check_validity(c, channel, text):
    """ICH E2D four minimum criteria."""
    low = text.lower()
    if "Quality complaint – no AE" in c["flags"]:
        return "No – not an adverse event", []
    if "Non-company product" in c["flags"]:
        return "No – non-company product", []
    patient_ok = bool(c["patient"]) or bool(re.search(
        r"\b(caller|customer|woman|man)\b (reports|reported|says|calls|using|taking)|\bher\b|\bhis\b|\bpatient (taking .{0,60})?reported\b", low))
    reporter_ok = not re.search(r"anonymous|no name", low)
    product_ok = c["suspect_product"] not in (None, "Unknown")
    event_ok = bool(c["events"]) or bool(c["verbatim"]) or "Ambiguous verbatim – needs clarification" in c["flags"] or bool(re.search(r"pregnan|instead of the prescribed", low))
    missing = [n for n, ok in [("identifiable patient", patient_ok), ("identifiable reporter", reporter_ok),
                               ("suspect product", product_ok), ("adverse event", event_ok)] if not ok]
    if not product_ok:
        return "No – suspect product missing", missing
    if not event_ok:
        return "No – event missing", missing
    if not reporter_ok:
        return "No – reporter not identifiable", missing
    if not patient_ok:
        return "Pending follow-up", missing
    return "Yes", missing


def triage(c):
    s = c["seriousness_indicators"]
    hard = [x for x in s if x in ("Death", "Hospitalisation", "Life-threatening")]
    if hard:
        return "P1", hard[0]
    if re.search(r"emergency|urgent", c.get("_text", ""), re.I):
        return "P1", "Possible – human review"
    if s:
        return "P2", s[0]
    if any(f in c["flags"] for f in ("Pregnancy", "Overdose", "Medication error", "Lack of efficacy", "Off-label", "Paediatric")):
        return "P2", "None reported"
    return "P3", "None reported"


def expectedness(c):
    prod = c["suspect_product"]
    if prod in RSI and ("Ambiguous verbatim – needs clarification" in c["flags"] or "lack of efficacy" in c["events"]):
        return "Needs review"
    if prod not in RSI or not c["events"]:
        return "Not applicable"
    listed = RSI[prod]["listed"]
    clinical = [e for e in c["events"] if e not in ("death", "lack of efficacy")] or c["events"]
    return "Listed" if all(e in listed for e in clinical) else "Unlisted"


def follow_up_questions(c, missing):
    q = [f"Obtain {m}" for m in missing]
    if not c["dose"]:
        q.append("Confirm strength and dose")
    if not c["patient"].get("age"):
        q.append("Confirm patient age")
    if c["seriousness_indicators"]:
        q.append("Obtain discharge summary / clinical records")
    q += [f"Resolve: {f}" for f in c["flags"] if f.startswith("Contradiction")]
    return q


def draft_narrative(c, channel, priority):
    p = c["patient"]
    who = " ".join(x for x in [f"{p['age']}-year-old" if "age" in p else "", p.get("sex", ""), "patient"] if x)
    ev = ", ".join(c["events"]) or "an unspecified event"
    dose = f" {c['dose']}" if c["dose"] else ""
    freq = f" {c['frequency']}" if c["frequency"] else ""
    s = (f"[AI DRAFT – for PV review] A report was received via {channel.lower()} concerning a {who} "
         f"treated with {c['suspect_product'] or 'an unidentified product'}{dose}{freq}, who experienced {ev}.")
    if c["seriousness_indicators"]:
        s += f" The report mentions: {', '.join(c['evidence'].get(x, x) for x in c['seriousness_indicators'])}."
    s += " Causality has not been assessed. Outcome as reported only; no information has been inferred."
    return s


def find_duplicates(c, existing):
    hits = []
    for e in existing:
        same_prod = e["suspect_product"] and e["suspect_product"] == c["suspect_product"]
        shared = set(e["events"]) & set(c["events"])
        same_age = e["patient"].get("age") and e["patient"].get("age") == c["patient"].get("age")
        if same_prod and shared and (same_age or len(shared) >= 1 and e["patient"].get("age") is None):
            hits.append({"case_id": e["case_id"], "matched_on": ["product", *sorted(shared)] + (["age"] if same_age else [])})
    return hits


def process(case_id, text, channel, awareness_date=None, receipt_date=None, market="IN",
            existing=None, use_llm=False, today=None):
    masked, pii = guards.mask_pii(text)
    injected = guards.detect_injection(text)
    c = extract(masked, channel)
    c["_text"] = masked
    engine = VERSION
    if use_llm:
        from . import llm
        c, engine = llm.enrich(masked, c)
    c["case_id"] = case_id
    validity, missing = check_validity(c, channel, masked)
    priority, seriousness = triage(c)
    expedited = priority in ("P1", "P2") and seriousness != "None reported"
    clk = clock.compute_clock(awareness_date, receipt_date, market, expedited, today)
    if clk["handoff_lag_days"]:
        c["flags"].append(f"Late hand-off: {clk['handoff_lag_days']} days between awareness and PV receipt")
    if injected:
        c["flags"].append("Prompt-injection attempt ignored")
    if pii:
        c["flags"].append("PII masked: " + ", ".join(pii))
    dups = find_duplicates(c, existing or [])
    if dups:
        c["flags"].append("Possible duplicate – human decision")
    c.pop("_text", None)
    result = {"case_id": case_id, "channel": channel, "engine": engine, "source_text_masked": masked,
              "extraction": c, "valid_icsr": validity, "missing_minimum_criteria": missing,
              "triage_priority": priority, "seriousness_indicator": seriousness,
              "expectedness_suggestion": expectedness(c), "clock": clk, "duplicates": dups,
              "follow_up": follow_up_questions(c, missing), "narrative_draft": draft_narrative(c, channel, priority),
              "causality": "Not assessed – safety physician decision", "status": "Awaiting human review"}
    audit.record(case_id, engine, "AI_PROPOSAL", {"priority": priority, "valid": validity, "due": clk["due_date"],
                                                  "injection": injected, "pii": pii})
    return result
