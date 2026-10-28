#!/usr/bin/env python3
"""Run the implementer's acceptance evidence pass for one gate (v1.2 matrix).

This is SELF-TEST evidence: it can never unlock a gate and it is not a Muse
verdict. It reads the required check ids from 04_ACCEPTANCE_MATRIX.csv, runs the
mapped commands against the real local server, and writes

    qa/evidence/G<n>/host-local/selftest.json (+ per-check logs)

The JSON follows the handoff check shape so a Muse handoff can reference it.

    python scripts/selftest.py --gate G1
"""
from __future__ import annotations

import argparse
import csv
import json
import platform
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
PLATFORM_ID = "windows11_x64" if sys.platform == "win32" else (
    "macos_apple_silicon_arm64" if sys.platform == "darwin" else "other_local")


def fingerprint() -> str:
    return (f"{platform.system()}-{platform.release()}-{platform.machine()}-"
            f"py{platform.python_version()}")


def run_cmd(cmd: list[str], log: Path, timeout: int = 1800) -> int:
    log.parent.mkdir(parents=True, exist_ok=True)
    started = time.time()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, timeout=timeout,
                              env={**__import__("os").environ, "PYTHONUTF8": "1"},
                              encoding="utf-8", errors="replace")
        code = proc.returncode
        body = f"$ {' '.join(cmd)}\nexit={code}\nelapsed={time.time() - started:.1f}s\n"
        body += "--- stdout ---\n" + (proc.stdout or "") + "\n--- stderr ---\n" + (proc.stderr or "")
    except subprocess.TimeoutExpired:
        code = 124
        body = f"$ {' '.join(cmd)}\nTIMEOUT after {timeout}s\n"
    log.write_text(body, encoding="utf-8")
    return code


# check id -> (pytest selector or shell command, browsers, note)
MAPPED: dict[str, tuple[list[str], list[str], str]] = {}


def py(*tests: str, browsers: tuple[str, ...] = ()) -> tuple[list[str], list[str], str]:
    return ([PY, "-m", "pytest", "-q", *tests], list(browsers), "pytest")


def e2e(name: str | None = None) -> tuple[list[str], list[str], str]:
    path = "tests/e2e/test_browser.py" + (f"::{name}" if name else "")
    return py(path, browsers=("chromium", "firefox", "webkit"))


MAPPED.update({
    # G1
    "OFF-01": py("tests/test_strict_offline.py", "tests/test_api.py::test_demo_persists_survives_restart_and_export_is_immutable"),
    "WEB-SERVE": ([PY, "scripts/g1_check.py"], ["chromium"], "g1 runtime probe"),
    "WEB-PACK": ([PY, "-c", "import zipfile,sys;"
                   "w=zipfile.ZipFile('dist/paperfamiliar-0.1.0-py3-none-any.whl');"
                   "names=w.namelist();"
                   "sys.exit(0 if any('web/dist/index.html' in n for n in names) "
                   "and any('/demo/' in n for n in names) else 1)"], [], "wheel contents"),
    "WEB-UI-SMOKE": e2e(),
    "WEB-NOPLATFORM": ([PY, "-c", "import sys;"
                        "bad=[m for m in ('electron','tauri','pywebview','pystray') if m in sys.modules];"
                        "sys.exit(1 if bad else 0)"], [], "no native GUI deps"),
    "WEB-STATE-BOOT": ([PY, "scripts/g1_check.py"], ["chromium"], "restart persistence probe"),
    "UX-01": e2e("test_demo_loads_and_clicking_a_finding_jumps_to_source"),
    "OS-PATH-01": py("tests/test_scanner.py", "tests/test_api.py::test_upload_from_browser_multiples"),
    "WEB-PORT": ([PY, "scripts/g1_check.py"], [], "port conflict probe"),
    # G2
    "EVD-01": py("tests/test_rules.py"),
    "EVD-02": py("tests/test_providers.py", "tests/test_strict_offline.py"),
    "EVD-03": py("tests/test_quote_gate.py"),
    "ADV-04": py("tests/test_providers.py::test_metadata_corroborates_but_never_supports_a_claim",
                 "tests/test_providers.py::test_metadata_offline_never_reaches_network"),
    "ADV-05": py("tests/test_quote_gate.py::test_every_fabricated_finding_is_rejected"),
    "ADV-06": py("tests/test_security.py::test_prompt_injection_is_inert_text"),
    "SEC-ZIP": py("tests/test_security.py::test_dangerous_archives_fail_closed"),
    "SEC-TEX": py("tests/test_security.py::test_malicious_includes_are_reported_not_followed",
                  "tests/test_scanner.py::test_malicious_tex_is_scanned_never_executed",
                  "tests/test_security.py::test_scanner_never_writes_next_to_source"),
    "SEC-SOURCE": py("tests/test_scanner.py::test_multifile_order_and_crlf_positions",
                     "tests/test_quote_gate.py::test_exact_span_round_trips",
                     "tests/test_api.py::test_demo_persists_survives_restart_and_export_is_immutable"),
    "WEB-HOST": py("tests/test_api.py::test_host_and_csrf_guards"),
    "WEB-CSRF": py("tests/test_api.py::test_host_and_csrf_guards", browsers=("chromium", "firefox", "webkit")),
    "WEB-FILE": py("tests/test_api.py::test_path_escape_is_refused",
                   "tests/test_api.py::test_upload_rejects_traversal_and_bad_types"),
    # G3
    "ADV-01": py("tests/test_style.py::test_same_topic_different_author_does_not_look_identical"),
    "ADV-02": py("tests/test_style.py::test_baseline_uses_function_words_not_topic_terms"),
    "ADV-03": py("tests/test_style.py::test_coauthor_sections_are_excluded_from_the_profile"),
    "STYLE-01": py("tests/test_style.py::test_coauthor_sections_are_excluded_from_the_profile",
                   "tests/test_rules.py::test_draft_has_the_intended_defects"),
    "STYLE-02": py("tests/test_style.py::test_small_sample_abstains_instead_of_scoring",
                   "tests/test_api.py::test_path_workspace_and_reference_flow"),
    "FAM-01": py("tests/test_navigator.py",
                 "tests/e2e/test_browser.py::test_accept_dismiss_and_navigator",
                 browsers=("chromium", "firefox", "webkit")),
    "FAM-02": py("tests/test_navigator.py"),
    "STYLE-CARD": e2e("test_refresh_restores_workspace"),
    # G4
    "WEB-E2E": e2e(),
    "WEB-PERSIST": py("tests/e2e/test_browser.py::test_refresh_restores_workspace",
                      "tests/test_api.py::test_demo_persists_survives_restart_and_export_is_immutable",
                      browsers=("chromium", "firefox", "webkit")),
    "WEB-DELETE": py("tests/test_api.py::test_delete_workspace_removes_copy_but_not_the_original",
                     "tests/test_api.py::test_clear_all_empties_the_store"),
    "SEC-01": py("tests/test_strict_offline.py"),
    "SEC-02": py("tests/test_providers.py::test_no_request_before_consent",
                 "tests/test_providers.py::test_payload_change_after_preview_is_refused",
                 "tests/test_providers.py::test_consent_is_single_use"),
    "SEC-SECRET": py("tests/test_providers.py::test_secrets_are_redacted_before_the_preview",
                     "tests/test_providers.py::test_api_key_is_not_in_the_preview"),
    "AI-01": py("tests/test_providers.py::test_core_product_is_complete_without_any_model",
               "tests/test_providers.py::test_no_request_before_consent"),
    "AI-02": py("tests/test_providers.py::test_consent_sends_exactly_the_previewed_payload"),
    "STYLE-03": py("tests/test_api.py::test_demo_persists_survives_restart_and_export_is_immutable",
                   "tests/test_security.py::test_scanner_never_writes_next_to_source"),
    "UX-03": py("tests/test_api.py::test_demo_persists_survives_restart_and_export_is_immutable"),
    "UX-02": py("tests/e2e/test_browser.py::test_layout_has_no_page_overflow",
                browsers=("chromium", "firefox", "webkit")),
    "WEB-LAN": py("tests/test_api.py::test_host_and_csrf_guards",
                  "tests/test_strict_offline.py::test_provider_probe_is_loopback_only"),
    # G5
    "OPS-01": ([PY, "-m", "build", "--wheel"], [], "wheel build"),
    "SEC-PUBLISH": ([PY, "scripts/secret_scan.py"], [], "secret and privacy scan"),
    "OPS-COMPAT": py("tests/test_scanner.py", "tests/test_api.py",
                     "tests/test_providers.py", "tests/test_security.py",
                     "tests/test_style.py", "tests/test_navigator.py", "tests/test_quote_gate.py"),
})

# ids that only Muse or the user can decide
MANUAL = {"USER-01"}
MUSE_ONLY = {"QA-01", "QA-02"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gate", required=True, choices=[f"G{i}" for i in range(1, 6)])
    args = ap.parse_args()

    with (ROOT / "04_ACCEPTANCE_MATRIX.csv").open(encoding="utf-8-sig", newline="") as fh:
        rows = [r for r in csv.DictReader(fh) if r["gate"] == args.gate]

    ev_dir = ROOT / "qa" / "evidence" / args.gate / "host-local"
    ev_dir.mkdir(parents=True, exist_ok=True)
    run_id = uuid.uuid4().hex[:12]
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                         text=True).stdout.strip()

    # run the live-server probes once per invocation and reuse the results
    g1_results: dict[str, dict] | None = None

    def g1_probe() -> dict[str, dict]:
        nonlocal g1_results
        if g1_results is None:
            run_cmd([PY, "scripts/g1_check.py"], ev_dir / f"g1_check-{run_id}.log")
            probe_root = ROOT / "qa" / "evidence" / "G1" / "host-local"
            candidates = sorted(probe_root.glob("g1-check-*.json"),
                                key=lambda p: p.stat().st_mtime)
            latest = (json.loads(candidates[-1].read_text(encoding="utf-8"))
                      if candidates else {})
            rel = (ev_dir / f"g1_check-{run_id}.log").relative_to(ROOT).as_posix()
            g1_results = {
                check["id"]: {"status": check["status"], "observed": check["observed"],
                              "log": rel, "code": 0 if check["status"] == "PASS" else 1}
                for check in latest.get("checks", [])
            }
        return g1_results

    checks = []
    commands = []

    def note_log(cid: str, text: str) -> str:
        path = ev_dir / f"{cid.lower()}-{run_id}.note.log"
        path.write_text(text, encoding="utf-8")
        return path.relative_to(ROOT).as_posix()

    for row in rows:
        cid = row["id"]
        if cid in MUSE_ONLY:
            note = note_log(cid, f"{cid} is reserved for independent Muse execution.\n"
                                 "The implementer records BLOCKED and must never self-attest "
                                 "this check.\n")
            checks.append({
                "id": cid, "status": "BLOCKED", "expected": row["assertion"],
                "observed": "independent QA can only be recorded by Muse; the implementer "
                            "leaves this blocked and must not self-attest it",
                "platforms_tested": [PLATFORM_ID], "browsers_tested": [],
                "evidence_paths": [note],
            })
            print(f"BLOCKED {cid:14} (Muse only)")
            continue
        if cid in MANUAL:
            note = note_log(cid, f"{cid} is the product owner's own judgment.\n"
                                 "Neither the implementer nor Muse may sign for the author.\n")
            checks.append({
                "id": cid, "status": "UNTESTED", "expected": row["assertion"],
                "observed": "reserved for the product owner's own signature; "
                            "the implementer cannot test this",
                "platforms_tested": [PLATFORM_ID], "browsers_tested": [],
                "evidence_paths": [note],
            })
            print(f"UNTESTED {cid:12} (user only)")
            continue
        if cid in ("WEB-SERVE", "WEB-STATE-BOOT", "WEB-PORT", "WEB-NOPLATFORM"):
            probe = g1_probe().get(cid)
            if probe is None:
                checks.append({"id": cid, "status": "FAIL", "expected": row["assertion"],
                               "observed": "g1_check produced no record for this id",
                               "platforms_tested": [PLATFORM_ID], "browsers_tested": [],
                               "evidence_paths": [f"qa/evidence/{args.gate}/host-local/"
                                                  f"g1_check-{run_id}.log"]})
                continue
            checks.append({
                "id": cid, "status": probe["status"], "expected": row["assertion"],
                "observed": probe["observed"], "platforms_tested": [PLATFORM_ID],
                "browsers_tested": ["chromium"], "evidence_paths": [probe["log"]],
            })
            commands.append({"command": f"scripts/g1_check.py (shared probe for {cid})",
                             "exit_code": probe["code"], "platform": PLATFORM_ID,
                             "log_path": probe["log"]})
            print(f"{probe['status']:4}  {cid:14} g1_check")
            continue
        mapped = MAPPED.get(cid)
        if mapped is None:
            note = note_log(cid, f"{cid} has no implementer-side procedure yet.\n"
                                 "Muse must define and run it independently.\n")
            checks.append({
                "id": cid, "status": "UNTESTED", "expected": row["assertion"],
                "observed": "no mapping in selftest.py; Muse must define the procedure",
                "platforms_tested": [PLATFORM_ID], "browsers_tested": [],
                "evidence_paths": [note],
            })
            continue
        cmd, browsers, note = mapped
        log = ev_dir / f"{cid.lower()}-{run_id}.log"
        code = run_cmd(cmd, log)
        status = "PASS" if code == 0 else "FAIL"
        rel = log.relative_to(ROOT).as_posix()
        checks.append({
            "id": cid, "status": status, "expected": row["assertion"],
            "observed": f"{note}: exit {code} on {platform.system()} {platform.machine()}",
            "platforms_tested": [PLATFORM_ID], "browsers_tested": browsers,
            "evidence_paths": [rel],
        })
        commands.append({"command": " ".join(cmd), "exit_code": code,
                         "platform": PLATFORM_ID, "log_path": rel})
        print(f"{status:4}  {cid:14} exit={code}")

    doc = {
        "kind": "IMPLEMENTER_SELF_TEST",
        "warning": "Not a Muse verdict; cannot unlock any gate by itself.",
        "gate": args.gate,
        "run_id": run_id,
        "commit_sha": sha,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "environment_fingerprint": fingerprint(),
        "platform": PLATFORM_ID,
        "checks": checks,
        "executed_commands": commands,
        "passed": sum(1 for c in checks if c["status"] == "PASS"),
        "total": len(checks),
    }
    out = ev_dir / f"selftest.json"
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {out.relative_to(ROOT)}  {doc['passed']}/{doc['total']} pass")
    return 0 if doc["passed"] == doc["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
