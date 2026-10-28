#!/usr/bin/env python3
"""PaperFamiliar V1.2 G1-G5 Web App evidence-contract checker (NOT an independent QA runner).

Only checks stored declarations and evidence paths. It cannot authenticate Muse, attest
real hardware, detect fake logs, or replace a user signature. All five gate records
must bind to one final commit. The script deliberately fails on a fresh handoff pack.

Exit 0: complete contract; 2: absent/failed gate; 3: malformed schema/declaration;
4: missing user decision (after otherwise successful QA), else fail closed.
"""
from __future__ import annotations
import argparse
import csv
import json
import re
import sys
from pathlib import Path

GATES = [f"G{i}" for i in range(1, 6)]
BROWSER_ENGINES = {"chromium", "firefox", "webkit"}
VALID_HOSTS = {"windows11_x64", "macos_apple_silicon_arm64", "linux_x64", "linux_arm64", "linux_ci", "other_local"}
SHA = re.compile(r"^[a-f0-9]{40}$")

class Invalid(Exception):
    pass


def read_json(path: Path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Invalid(f"Cannot read JSON {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise Invalid(f"Expected object: {path}")
    return data


def path_ok(root: Path, relative: str):
    if not isinstance(relative, str) or not relative.strip():
        raise Invalid("Evidence path missing/empty")
    p = Path(relative)
    if p.is_absolute() or ".." in p.parts:
        raise Invalid(f"Evidence escapes repo root: {relative!r}")
    full = (root / p).resolve()
    try:
        full.relative_to(root.resolve())
    except ValueError as exc:
        raise Invalid(f"Evidence symlink escapes repo: {relative!r}") from exc
    if not full.is_file() or full.stat().st_size <= 0:
        raise Invalid(f"Missing/empty evidence: {relative}")
    return full


def required_keys(obj, keys, what):
    missing = set(keys) - set(obj)
    if missing:
        raise Invalid(f"{what}: missing {', '.join(sorted(missing))}")


def validate_record(root, path, gate, is_verdict):
    doc = read_json(path)
    required_keys(doc, ["schema_version", "gate", "commit_sha", "run_id", "created_at",
                        "status", "environment_fingerprint", "tested_platforms", "browsers_tested",
                        "executed_commands", "checks", "failed_gates", "evidence_paths",
                        "network_isolation_proof"], path.name)
    if doc["schema_version"] != "1.2" or doc["gate"] != gate:
        raise Invalid(f"Wrong schema or gate in {path.name}")
    if not isinstance(doc["commit_sha"], str) or not SHA.fullmatch(doc["commit_sha"]):
        raise Invalid(f"Invalid SHA in {path.name}")
    if not isinstance(doc["run_id"], str) or len(doc["run_id"]) < 8:
        raise Invalid(f"Invalid run ID in {path.name}")
    if not isinstance(doc["environment_fingerprint"], str) or len(doc["environment_fingerprint"]) < 10:
        raise Invalid(f"Missing environment fingerprint in {path.name}")
    if not isinstance(doc["tested_platforms"], list) or not doc["tested_platforms"]:
        raise Invalid(f"No tested platforms in {path.name}")
    if not set(doc["tested_platforms"]).issubset(VALID_HOSTS):
        raise Invalid(f"Unknown host platform in {path.name}")
    if not isinstance(doc["browsers_tested"], list) or not set(doc["browsers_tested"]).issubset(BROWSER_ENGINES):
        raise Invalid(f"Invalid browser engines in {path.name}")
    if not isinstance(doc["executed_commands"], list) or not doc["executed_commands"]:
        raise Invalid(f"No executed commands in {path.name}")
    for cmd in doc["executed_commands"]:
        required_keys(cmd, ["command", "exit_code", "platform", "log_path"], path.name)
        if not isinstance(cmd["exit_code"], int):
            raise Invalid(f"Non-integer command exit code in {path.name}")
        path_ok(root, cmd["log_path"])
    if not isinstance(doc["checks"], list) or not doc["checks"]:
        raise Invalid(f"Missing checks in {path.name}")
    check_map = {}
    for c in doc["checks"]:
        required_keys(c, ["id", "status", "expected", "observed", "platforms_tested", "browsers_tested", "evidence_paths"], path.name)
        if c["status"] not in ("PASS", "FAIL", "UNTESTED", "BLOCKED"):
            raise Invalid(f"Unknown check status in {path.name}")
        if c["id"] in check_map:
            raise Invalid(f"Duplicate check ID in {path.name}: {c['id']}")
        if not c["expected"] or not c["observed"]:
            raise Invalid(f"No expected/observed for {c['id']}")
        if not isinstance(c["platforms_tested"], list) or not c["platforms_tested"]:
            raise Invalid(f"No tested platforms for check {c['id']}")
        if not set(c["platforms_tested"]).issubset(VALID_HOSTS):
            raise Invalid(f"Unknown platform for check {c['id']}")
        if not isinstance(c["browsers_tested"], list) or not set(c["browsers_tested"]).issubset(BROWSER_ENGINES):
            raise Invalid(f"Invalid browser engines for check {c['id']}")
        if not isinstance(c["evidence_paths"], list) or not c["evidence_paths"]:
            raise Invalid(f"No evidence files for check {c['id']}")
        for p in c["evidence_paths"]:
            path_ok(root, p)
        check_map[c["id"]] = c
    if not isinstance(doc["evidence_paths"], list) or not doc["evidence_paths"]:
        raise Invalid(f"No top-level evidence paths in {path.name}")
    for p in doc["evidence_paths"]:
        path_ok(root, p)
    if not isinstance(doc["network_isolation_proof"], str):
        raise Invalid(f"No network proof field in {path.name}")
    path_ok(root, doc["network_isolation_proof"])
    if is_verdict:
        required_keys(doc, ["tester_identity", "tester_origin", "independent_run_proof_path", "report_path"], path.name)
        if doc["status"] != "VERIFIED":
            raise RuntimeError(f"{gate}: Muse status {doc['status']}, cannot unlock")
        if doc["tester_origin"] != "independent_muse" or "muse" not in str(doc["tester_identity"]).lower():
            raise Invalid(f"Invalid claimed Muse identity in {path.name}")
        path_ok(root, doc["independent_run_proof_path"])
        path_ok(root, doc["report_path"])
        if doc["failed_gates"]:
            raise RuntimeError(f"{gate}: verdict has failed_gates")
    elif doc["status"] != "SUBMITTED":
        raise Invalid(f"Handoff status is not SUBMITTED in {path.name}")
    return doc, check_map


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=Path("."))
    args = ap.parse_args()
    root = args.root.resolve()
    matrix = root / "04_ACCEPTANCE_MATRIX.csv"
    if not matrix.exists():
        print("SCHEMA ERROR: missing 04_ACCEPTANCE_MATRIX.csv", file=sys.stderr)
        return 3
    with matrix.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    if not rows or len({r["id"] for r in rows}) != len(rows):
        print("SCHEMA ERROR: empty or duplicate matrix ID", file=sys.stderr)
        return 3
    all_sha = set()
    try:
        for gate in GATES:
            hp = root / f"qa/handoff-{gate}.json"
            vp = root / f"qa/muse-verdict-{gate}.json"
            if not hp.exists() or not vp.exists():
                print(f"BLOCKED: {gate} missing handoff/Muse verdict; no gate pass has been claimed.", file=sys.stderr)
                return 2
            h, hc = validate_record(root, hp, gate, False)
            v, vc = validate_record(root, vp, gate, True)
            if h["commit_sha"] != v["commit_sha"] or h["run_id"] != v["run_id"]:
                raise Invalid(f"{gate}: handoff/verdict SHA or run ID mismatch")
            all_sha.add(h["commit_sha"])
            expected = [r for r in rows if r["gate"] == gate]
            for row in expected:
                cid = row["id"]
                mandatory = row.get("critical", "true").lower() == "true"
                if cid not in hc or cid not in vc:
                    raise RuntimeError(f"{gate}: check {cid} missing; optional tests must declare UNTESTED explicitly")
                hs, vs = hc[cid]["status"], vc[cid]["status"]
                if mandatory and (hs != "PASS" or vs != "PASS"):
                    raise RuntimeError(f"{gate}: required check {cid} not PASS on both sides")
                if not mandatory and (hs in ("FAIL", "BLOCKED") or vs in ("FAIL", "BLOCKED")):
                    raise RuntimeError(f"{gate}: optional check {cid} recorded FAIL/BLOCKED; cannot silently waive")
                if hs == "UNTESTED" or vs == "UNTESTED":
                    if mandatory:
                        raise RuntimeError(f"{gate}: required check {cid} untested")
                    continue
                platforms = set(filter(None, row["required_platforms"].split(";"))) - {"any"}
                if not (platforms.issubset(set(h["tested_platforms"]))
                        and platforms.issubset(set(v["tested_platforms"]))
                        and platforms.issubset(set(hc[cid]["platforms_tested"]))
                        and platforms.issubset(set(vc[cid]["platforms_tested"]))):
                    raise RuntimeError(f"{gate}: required host platform(s) for {cid} missing: {sorted(platforms)}")
                browsers = set(filter(None, row.get("required_browsers", "any").split(";"))) - {"any"}
                if not (browsers.issubset(set(h["browsers_tested"]))
                        and browsers.issubset(set(v["browsers_tested"]))
                        and browsers.issubset(set(hc[cid]["browsers_tested"]))
                        and browsers.issubset(set(vc[cid]["browsers_tested"]))):
                    raise RuntimeError(f"{gate}: required browser engine(s) for {cid} missing: {sorted(browsers)}")
            print(f"{gate}: declaration and referenced files complete at {h['commit_sha'][:12]}")
        if len(all_sha) != 1:
            raise RuntimeError("G1-G5 must be re-run on the same final commit; different SHAs detected")
        approval_file = root / "qa/user-acceptance.json"
        if not approval_file.is_file():
            print("USER APPROVAL REQUIRED: qa/user-acceptance.json missing", file=sys.stderr)
            return 4
        approval = read_json(approval_file)
        required_keys(approval, ["schema_version","commit_sha","decision","approved_at","blind_test_evidence_path","user_confirmation","public_release_authorized"], approval_file.name)
        if approval["schema_version"] != "1.2" or approval["commit_sha"] not in all_sha:
            raise Invalid("User acceptance has wrong schema/commit")
        if approval["decision"] != "APPROVED" or len(approval["user_confirmation"]) < 20:
            print("USER APPROVAL REQUIRED: explicit user acceptance is absent", file=sys.stderr)
            return 4
        if approval["public_release_authorized"] is not False:
            raise Invalid("User approval for private push must not masquerade as public-release authorization")
        path_ok(root, approval["blind_test_evidence_path"])
        print("CONTRACT COMPLETE (not a substitute for physical QA identity verification or explicit push authorization)")
        return 0
    except Invalid as e:
        print(f"SCHEMA/EVIDENCE ERROR: {e}", file=sys.stderr)
        return 3
    except RuntimeError as e:
        print(f"GATE BLOCKED: {e}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    sys.exit(main())
