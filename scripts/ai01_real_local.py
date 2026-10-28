#!/usr/bin/env python3
"""AI-01 evidence: exercise the local model path honestly, either way.

If a local Ollama (or OpenAI-compatible loopback) is reachable with at least
one model, this performs a real end-to-end request through the product's own
consent machinery (preview -> confirm -> send) using a synthetic excerpt, and
records the candidate output. If not reachable, it verifies the documented
fallback: the product remains fully functional and the provider surface says
`unavailable` explicitly. Both outcomes are honest evidence; the script never
fabricates the other one.

    python scripts/ai01_real_local.py            # auto-detect
    PAPERFAMILIAR_OLLAMA_MODEL=qwen3.5:9b python scripts/ai01_real_local.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from paperfamiliar import providers  # noqa: E402

EXCERPT = (ROOT / "src" / "paperfamiliar" / "demo" / "draft" / "sections" / "eval.tex")
OUT_DIR = ROOT / "qa" / "evidence" / "G4" / "host-local"


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    probe = providers.probe_local(timeout=2.0)
    config = providers.local_provider()
    record = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "endpoint": config.base_url,
        "requested_model": config.model,
        "probe": probe,
        "kind": "IMPLEMENTER_SELF_TEST (not a Muse verdict)",
    }
    text = EXCERPT.read_text(encoding="utf-8")

    if probe["status"] == "available" and probe["models"]:
        model = config.model if config.model in probe["models"] else probe["models"][0]
        config.model = model
        store = providers.ConsentStore()
        preview = store.preview(
            "List candidate clarity issues in this excerpt; quote exact text.",
            text, config)
        started = time.time()
        store.confirm(preview["consent_id"])
        result = providers.send(store, preview["consent_id"],
                                "List candidate clarity issues in this excerpt; quote exact text.",
                                text, config, timeout=600.0)  # first load can be slow
        record["mode"] = "real_local_model"
        record["model"] = model
        record["preview_bytes"] = preview["payload_bytes"]
        record["estimated_tokens"] = preview["estimated_tokens"]
        record["redactions"] = preview["redactions"]
        record["elapsed_seconds"] = round(time.time() - started, 1)
        record["result_status"] = result.get("status")
        record["candidate_output_excerpt"] = (result.get("content") or result.get("detail")
                                              or "")[:1500]
        ok = result.get("status") == "candidate"
    else:
        record["mode"] = "fallback_documented"
        ok = probe["status"] in ("unavailable", "no_models")
        record["fallback_proof"] = ("product core path is covered by "
                                    "tests/test_providers.py::"
                                    "test_core_product_is_complete_without_any_model")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = OUT_DIR / f"ai01-real-local-{stamp}.json"
    out.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in record.items()
                      if k != "candidate_output_excerpt"}, indent=2)[:800])
    print(f"wrote {out.relative_to(ROOT)}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
