"""Solara PV Intake Agent – PoC web app (Python standard library only).
Run:  python app.py   then open http://localhost:8000
Optional LLM mode:  set ANTHROPIC_API_KEY, then tick "Use LLM" in the UI."""
import csv
import json
import pathlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from agent import audit
from agent.pipeline import process

ROOT = pathlib.Path(__file__).parent
TODAY = "2026-10-25"  # demo date so clocks are reproducible
CASES = {}


def load_demo_queue():
    for r in csv.DictReader(open(ROOT / "data" / "golden_dataset.csv", encoding="utf-8")):
        res = process(r["Case_ID"], r["Original_Report"], r["Source_Channel"], r["Company_Awareness_Date"],
                      r["PV_Receipt_Date"], r["Market"], existing=[c["extraction"] for c in CASES.values()],
                      today=TODAY)
        CASES[r["Case_ID"]] = res


class H(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            return self._send(200, (ROOT / "ui" / "index.html").read_bytes(), "text/html; charset=utf-8")
        if self.path == "/api/cases":
            return self._send(200, list(CASES.values()))
        if self.path == "/api/audit":
            lines = (audit.LOG.read_text().strip().splitlines() if audit.LOG.exists() else [])[-50:]
            return self._send(200, {"chain_valid": audit.verify(), "entries": [json.loads(x) for x in lines]})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or "{}")
        if self.path == "/api/process":
            cid = f"NEW-{len([k for k in CASES if k.startswith('NEW')]) + 1:03d}"
            res = process(cid, body["text"], body.get("channel", "Doctor email"), body.get("awareness_date"),
                          body.get("receipt_date"), body.get("market", "IN"),
                          existing=[c["extraction"] for c in CASES.values()], use_llm=body.get("use_llm", False),
                          today=TODAY)
            CASES[cid] = res
            return self._send(200, res)
        if self.path == "/api/decision":
            c = CASES.get(body["case_id"])
            if not c:
                return self._send(404, {"error": "unknown case"})
            c["status"] = {"accept": "Accepted by PV processor", "escalate": "Escalated to safety physician",
                           "followup": "Follow-up requested", "reject": "AI draft rejected – manual processing"}[body["action"]]
            audit.record(c["case_id"], body.get("user", "pv.processor@solara (demo)"), "HUMAN_" + body["action"].upper(),
                         {"comment": body.get("comment", ""), "edits": body.get("edits", {})})
            return self._send(200, c)
        self._send(404, {"error": "not found"})


if __name__ == "__main__":
    if audit.LOG.exists():
        audit.LOG.unlink()
    load_demo_queue()
    print("Solara PV Intake Agent PoC running on http://localhost:8000")
    ThreadingHTTPServer(("0.0.0.0", 8000), H).serve_forever()
