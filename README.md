# Solara PV Intake Agent: Proof of Concept

An AI-assisted **adverse-event intake and triage agent** for a mid-sized pharma pharmacovigilance (PV) team. It was built for the HashedIn by Deloitte LSHC case study.

> **The problem it targets:** 18% of serious, unexpected cases miss the regulatory deadline. Most of them were not hard cases. They **sat unread in an inbox or call log for days**. So this PoC focuses on getting the *clock* and the *queue* right first. It does not try to automate medical judgement.

## Try it without installing anything
**Live static demo:** https://YOUR-USERNAME.github.io/solara-pv-intake-agent/ (60 pre-computed synthetic cases; click a case, then Escalate / Accept).
The full agent (live "New report" processing and the hash-chained audit log) runs locally; see below.

## What it does

| Step | What happens | AI or deterministic |
|---|---|---|
| 1. Guard | Masks PII (Aadhaar, phone, email) and detects prompt-injection text inside reports | Deterministic |
| 2. Extract | Pulls patient, product, dose, frequency, events, reporter verbatim, and the source quote for every field | Rules (offline) or LLM, with the rules acting as a safety floor |
| 3. Validate | Checks the four ICH E2D minimum criteria (patient, reporter, product, event). Incomplete cases are held for follow-up, never discarded | Deterministic |
| 4. Triage | P1 (death, hospitalisation, life-threatening, ER/urgent), P2 (possible serious or special situation), P3 | Deterministic. The LLM can only *raise* urgency |
| 5. Clock | **Day 0 = first awareness by any Solara employee** (for example the sales rep's visit date). Due date comes from a per-market rule table | Deterministic. Never an LLM |
| 6. Draft | Expectedness suggestion against the RSI, duplicate candidates, follow-up questions and a factual narrative draft | Suggestion only |
| 7. Human decision | Accept, escalate to the safety physician, request follow-up, or reject. Causality is always "Not assessed – safety physician decision" | Human |
| 8. Audit | Every AI proposal and human action goes to an append-only, **hash-chained** log | Deterministic |

## Run it (Python 3.9+, no installs needed)

```bash
python app.py                 # opens the demo queue of 60 golden-set cases at http://localhost:8000
python -m eval.run_eval       # scores the agent against the golden dataset
```

Optional LLM mode: `export ANTHROPIC_API_KEY=...` (and optionally `ANTHROPIC_MODEL`). Then tick **Use LLM** in the UI or run `python -m eval.run_eval --llm`. If the API fails, the agent falls back to rules so intake is never blocked.

## Results on the golden dataset (60 synthetic cases, rules mode)

| Check | Score |
|---|---|
| **P1 recall (serious cases caught)** | **16/16** |
| No under-triage | 60/60 |
| Triage exact | 59/60 (1 over-triage: a safe direction) |
| Day-0 and due date | 60/60 |
| Product extraction | 58/60 |
| Expectedness suggestion | 56/60 |
| ICSR validity | 54/60 |

The first run (v0.1) **missed one P1**: an emergency-department visit was routed P2. The golden set caught it, the triage rule was fixed in v0.2, and the miss is logged in `Error_Analysis`. The eval loop exists to catch exactly this kind of miss.

These scores come from a small synthetic set whose labels have not been adjudicated by a PV physician. They show the method works. They are **not** evidence of clinical validity.

## Golden dataset
`data/Solara_Golden_Dataset_v2.xlsx` (full workbook with evaluation criteria, test results and error analysis) and `data/golden_dataset.csv` (the same 60 cases for the evaluator).

## Repository

```
agent/   guards.py · extract.py · pipeline.py · clock.py · audit.py · llm.py
data/    golden_dataset.csv · reference_safety_info.json (fictional RSI) · market_rules.json (illustrative)
eval/    run_eval.py · results.csv · summary.json
ui/      index.html (single-page review workbench)
```

## Explicitly out of scope for the PoC
Real patient data, licensed MedDRA coding, E2B(R3) submission, safety-database write-back, and any autonomous causality, seriousness or submission decision. All products are fictional. Regulatory timelines are illustrative and must be verified by Regulatory Affairs.
