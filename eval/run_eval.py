"""Score the agent against the golden dataset. Usage: python -m eval.run_eval [--llm]"""
import csv, json, sys, pathlib, collections
from agent.pipeline import process

ROOT = pathlib.Path(__file__).parent.parent
rows = list(csv.DictReader(open(ROOT / "data" / "golden_dataset.csv", encoding="utf-8")))
use_llm = "--llm" in sys.argv
done, results = [], []
score = collections.Counter(); fails = []
for r in rows:
    res = process(r["Case_ID"], r["Original_Report"], r["Source_Channel"], r["Company_Awareness_Date"],
                  r["PV_Receipt_Date"], r["Market"], existing=[d["extraction"] for d in done],
                  use_llm=use_llm, today="2026-11-06")
    done.append(res)
    exp_p, got_p = r["Expected_Triage_Priority"], res["triage_priority"]
    rank = {"P1": 1, "P2": 2, "P3": 3}
    checks = {
        "triage_exact": got_p == exp_p,
        "no_under_triage": rank[got_p] <= rank[exp_p],
        "validity": res["valid_icsr"].split(" –")[0] == r["Expected_Valid_ICSR"].split(" –")[0],
        "product": (res["extraction"]["suspect_product"] or "Unknown").split(" ")[0].lower()
                   == ("unknown" if r["Expected_Suspect_Drug"].startswith("Not stated") else r["Expected_Suspect_Drug"].split(" ")[0].lower()),
        "expectedness": res["expectedness_suggestion"] == r["Expected_Expectedness_Suggestion"],
        "due_date": (res["clock"]["due_date"] or "") == r["Expected_Due_Date"],
    }
    for k, v in checks.items():
        score[k] += v
    p1 = exp_p == "P1"
    score["p1_total"] += p1; score["p1_caught"] += p1 and got_p == "P1"
    bad = [k for k, v in checks.items() if not v]
    if bad:
        fails.append((r["Case_ID"], r["Scenario_Category"], bad, f"exp {exp_p}/{r['Expected_Valid_ICSR']}/{r['Expected_Expectedness_Suggestion']}",
                      f"got {got_p}/{res['valid_icsr']}/{res['expectedness_suggestion']}"))
    results.append({"Case_ID": r["Case_ID"], "engine": res["engine"], "priority": got_p, "valid": res["valid_icsr"],
                    "expectedness": res["expectedness_suggestion"], "due": res["clock"]["due_date"],
                    "flags": "; ".join(res["extraction"]["flags"]), "events": ", ".join(res["extraction"]["events"]),
                    "pass": "PASS" if not bad else "FAIL: " + ",".join(bad)})
n = len(rows)
summary = {k: f"{score[k]}/{n} ({100*score[k]/n:.0f}%)" for k in
           ["triage_exact", "no_under_triage", "validity", "product", "expectedness", "due_date"]}
summary["P1_recall"] = f"{score['p1_caught']}/{score['p1_total']}"
out = ROOT / "eval" / "results.csv"
with open(out, "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=results[0].keys()); w.writeheader(); w.writerows(results)
(ROOT / "eval" / "summary.json").write_text(json.dumps(summary, indent=2))
print(json.dumps(summary, indent=2))
for f in fails: print(*f)
