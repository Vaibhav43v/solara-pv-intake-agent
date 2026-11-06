"""Append-only, hash-chained audit log (tamper-evident). One JSON line per event."""
import hashlib
import json
import pathlib
import datetime as dt

LOG = pathlib.Path(__file__).parent.parent / "audit_log.jsonl"


def _last_hash():
    if not LOG.exists():
        return "GENESIS"
    lines = LOG.read_text().strip().splitlines()
    return json.loads(lines[-1])["hash"] if lines else "GENESIS"


def record(case_id: str, actor: str, action: str, detail: dict):
    entry = {"ts": dt.datetime.now(dt.timezone.utc).isoformat(), "case_id": case_id, "actor": actor,
             "action": action, "detail": detail, "prev": _last_hash()}
    entry["hash"] = hashlib.sha256(json.dumps(entry, sort_keys=True).encode()).hexdigest()
    with LOG.open("a") as fh:
        fh.write(json.dumps(entry) + "\n")
    return entry


def verify():
    prev = "GENESIS"
    for line in LOG.read_text().strip().splitlines() if LOG.exists() else []:
        e = json.loads(line)
        h = e.pop("hash")
        if e["prev"] != prev or hashlib.sha256(json.dumps(e, sort_keys=True).encode()).hexdigest() != h:
            return False
        prev = h
    return True
