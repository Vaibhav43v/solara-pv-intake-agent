"""Rule-based extractor (offline, deterministic baseline).
In LLM mode (agent/llm.py) the model proposes fields; these rules still run as a
safety floor for seriousness signals so the LLM can never DOWN-grade urgency."""
import json
import pathlib
import re

RSI = json.loads((pathlib.Path(__file__).parent.parent / "data" / "reference_safety_info.json").read_text())["products"]

# canonical event -> patterns (English, Hinglish, clinical shorthand)
EVENTS = {
    "death": r"\bdied\b|\bdeath\b|\bfatal\b",
    "myocardial infarction": r"myocardial infarction|\bMI\b",
    "stevens-johnson syndrome": r"stevens[- ]johnson",
    "angioedema": r"angioedema",
    "seizure": r"seizure|convulsion|\bfits?\b",
    "loss of consciousness": r"loss of consciousness|unconscious|fainted",
    "jaundice": r"jaundice",
    "raised liver enzymes": r"liver enzymes",
    "chest pain": r"chest pain",
    "difficulty breathing": r"difficulty breathing|breathing trouble|\bwheeze|\bSOB\b|shortness of breath|breathless",
    "hypotension": r"BP\s*[4-8]\d/|hypotension",
    "facial swelling": r"facial swelling|swelling of (the )?face",
    "ankle swelling": r"swelling around the ankles|ankle swelling",
    "muscle pain": r"muscle pain|myalgia",
    "hives": r"\bhives\b|urticaria",
    "rash": r"\brash\b",
    "itching": r"itch|khujli",
    "skin dryness": r"skin (a little |very )?dry|dry skin",
    "dry cough": r"dry cough",
    "nausea": r"nausea",
    "vomiting": r"vomit|ulti",
    "dizziness": r"dizz|chakkar|light-headed",
    "drowsiness": r"drows",
    "headache": r"headache",
    "fatigue": r"fatigue|tired",
    "abdominal discomfort": r"abdominal discomfort",
    "stomach upset": r"stomach upset",
    "palpitations": r"racing heart|palpitation",
}
AMBIGUOUS = r"'weak'|'spots'|'allergy'|'swelling'|'woozy'|became unwell|\ba reaction\b|\ba problem\b"
LISTED_ALIASES = {"hives": "rash", "stomach upset": "stomach upset"}


def _first(pat, text, flags=re.I):
    m = re.search(pat, text, flags)
    return m.group(1) if m else None


def extract(text: str, channel: str = "") -> dict:
    t = text
    low = t.lower()
    case = {"patient": {}, "suspect_product": None, "dose": None, "frequency": None,
            "events": [], "verbatim": re.findall(r"'([^']{2,40})'", t), "flags": [],
            "seriousness_indicators": [], "evidence": {}}

    # --- patient ---
    age = (_first(r"(\d{1,3})[- ]year[- ]old", t) or _first(r"(\d{1,3}) saal", t)
           or _first(r"\b(\d{1,3})\s*/\s*[MF]\b", t) or _first(r"\((\d{2})\)", t)
           or _first(r"(\d{1,3}) years old", t))
    if age:
        case["patient"]["age"] = int(age)
    elif re.search(r"\bchild\b|\bboy\b|\bgirl\b|\binfant\b", low):
        case["patient"]["age_group"] = "child"
    if re.search(r"\b(female|woman|girl|mummy|mother|she|her)\b|/F\b", t, re.I):
        case["patient"]["sex"] = "female"
    elif re.search(r"\b(male|man|boy|father|he|his)\b|/M\b", t, re.I):
        case["patient"]["sex"] = "male"
    ini = _first(r"initials\s+([A-Z]\.?\s?[A-Z]\.?)", t, 0)
    if ini:
        case["patient"]["initials"] = ini
    ages = set(re.findall(r"(\d{1,3}) years old", t))
    if len(ages) > 1:
        case["flags"].append("Contradiction: age " + " vs ".join(sorted(ages)))
        case["patient"].pop("age", None)

    # --- product ---
    if re.search(r"another company|not solara|other manufacturer", low):
        case["flags"].append("Non-company product")
        case["suspect_product"] = _first(r"after (\w+) \d", t) or "Non-Solara product"
    for p in RSI:
        if p.lower() in low:
            case["suspect_product"] = p
            case["evidence"]["product"] = p
            break
    if case["suspect_product"] in RSI:
        strengths = re.findall(case["suspect_product"] + r"\s+(\d+(?:\.\d+)?\s*(?:mg|g)\b|\d{2,4}\b)", t, re.I)
        strengths = list(dict.fromkeys(s.replace(" ", "") for s in strengths))
        if len(strengths) > 1:
            case["flags"].append("Contradiction: strength " + " vs ".join(strengths))
        elif strengths:
            s = strengths[0]
            case["dose"] = s if re.search(r"mg|g$", s) else s + " mg"
    freq = {"once daily": r"once daily|\bOD\b|\bdaily\b", "twice daily": r"twice daily|\bBD\b"}
    for k, p in freq.items():
        if re.search(p, t):
            case["frequency"] = k
            break

    # --- events ---
    for canon, pat in EVENTS.items():
        m = re.search(pat, t, re.I)
        if m:
            case["events"].append(canon)
            case["evidence"][canon] = m.group(0)
    if "facial swelling" in case["events"] or "angioedema" in case["events"]:
        case["events"] = [e for e in case["events"] if e != "ankle swelling"]
    if re.search(AMBIGUOUS, t, re.I):
        case["flags"].append("Ambiguous verbatim – needs clarification")
    if re.search(r"not working|not controlling|no effect|sugars still", low):
        case["events"].append("lack of efficacy")

    # --- seriousness indicators (deterministic floor) ---
    S = [("Death", r"\bdied\b|\bdeath\b|\bfatal"),
         ("Hospitalisation", r"admitted|admit karna|hospitali[sz]ed|\bICU\b|\bPICU\b|burns unit|kept in .*ICU"),
         ("Life-threatening", r"adrenaline|angioedema|BP\s*[4-8]\d/|life-threatening|anaphyla"),
         ("Possible – human review", r"emergency|urgent|breathing|unwell|discharged|\bSOB\b")]
    for label, pat in S:
        m = re.search(pat, t, re.I)
        if m:
            case["seriousness_indicators"].append(label)
            case["evidence"][label] = m.group(0)

    # --- special situations ---
    SP = [("Pregnancy", r"pregnan"), ("Overdose", r"overdose|swallowed about|\d+ tablets"),
          ("Medication error", r"instead of the prescribed|dispensing .* instead|medication error"),
          ("Lack of efficacy", r"not working|not controlling|sugars still"), ("Off-label", r"off-label"),
          ("Literature", r"abstract|journal|we report")]
    for label, pat in SP:
        if re.search(pat, t, re.I):
            case["flags"].append(label)
    a = case["patient"].get("age")
    if (a is not None and a < 18) or case["patient"].get("age_group") == "child":
        case["flags"].append("Paediatric")
    if re.search(r"broken blister|crumbled|no patient took", low):
        case["flags"].append("Quality complaint – no AE")
        case["events"] = []
    if re.search(r"stopped .* still taking|stopped.*then later says", low):
        case["flags"].append("Contradiction: treatment status")
    if re.search(r"before the first dose", low) or (re.search(r"header states", low) and re.search(r"narrative says", low)):
        case["flags"].append("Contradiction: chronology")
    if re.search(r"second email|update|follow-up report|later sends", low):
        case["flags"].append("Follow-up")
    return case
