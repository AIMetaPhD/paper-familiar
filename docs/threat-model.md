# PaperFamiliar Threat Model (v0.1)

- Date: 2026-10-28
- Assets: unpublished manuscripts, author style profile, API keys, local files outside the workspace, the integrity of the evidence ledger.
- Trust boundary: everything parsed from `.tex`, `.bib` or `.zip` is untrusted. Model output is untrusted. The local browser is trusted only for same-origin requests to `127.0.0.1`.

## 1. Adversaries and abuse cases

| # | Adversary / scenario | Impact | Control | Test |
|---|---|---|---|---|
| T1 | Malicious archive (`../`, absolute, symlink, device file, nested bomb) | arbitrary file write/read outside workspace | extract into a fresh directory; reject absolute/parent/symlink/special entries; cap entries, total size, ratio and depth; canonical root check | SEC-ZIP, `fixtures/generated/*.zip` |
| T2 | Malicious TeX (`\write18`, `\input{/etc/passwd}`, `\input{../../secret}`, recursive macro) | command execution, secret read | never run a TeX engine; treat includes as text; resolve only inside root; recursion depth cap; report as security event | SEC-TEX, `fixtures/adversarial/malicious.tex` |
| T3 | Prompt injection inside manuscript comments or text | hijack agent policy, leak keys, skip checks | model output is data; fixed system policy; no tool execution from model output; redact secrets; quote gate independent of model | ADV-06, canary key in environment during test |
| T4 | Fabricated or shifted quote from a model (hallucination) | user trusts a false citation of their own text | exact byte-range quote gate before ledger; hash binding; rejection log | ADV-05, `fixtures/adversarial/fabricated_findings.json` |
| T5 | Real DOI attached to a wrong claim | user believes the literature supports the claim | metadata status is `source_corroborated`, never `claim_supported`; claim support requires licensed source text and is `insufficient_evidence` otherwise | ADV-04 |
| T6 | Unauthorized outbound traffic (metadata lookup, cloud model, telemetry) | manuscript exfiltration | strict offline default; per-request payload preview and consent; no CDN; egress test with firewall/network capture | SEC-01, SEC-02, `UNTESTED_CLOUD_REAL` when no key |
| T7 | Key leakage through logs/reports/DB/exports | credential compromise | keys only from env/OS store; redaction filter on every log and export; secret scan in CI and before push | SEC-SECRET |
| T8 | Cross-origin or DNS-rebinding request to the local API | reading or mutating local data from a web page | bind loopback; validate `Host`; require same-origin for state-changing methods; no CORS wildcard; CSRF token for mutations | SEC-01 |
| T9 | Style-profile poisoning by coauthor or unapproved sections | wrong "your style" advice | section-level contribution labels; default `unknown` excluded; only `author_approved && sole_or_primary` used; sample-size abstention | ADV-03, STYLE-02 |
| T10 | Repudiation of a QA gate | false claim of acceptance | handoff/verdict JSON bound to commit, run id, platform and logs; independent Muse identity; user signature | G1–G5 checker + human review |

## 2. Explicit non-goals

- No defense against a malicious local user with the same OS account; file permissions are the boundary.
- No compiled-PDF sandbox in v0.1, because v0.1 does not compile.
- No claim that metadata lookup proves a scientific claim.
- No anti-forensics or detection evasion; the product is defensive and author-facing.

## 3. Fail-closed rules

1. Unknown archive entry type → reject the archive.
2. Include outside workspace root → skip the include and record a security event.
3. Quote mismatch (even after normalization) → reject the finding.
4. Model provider configured but consent not granted → no request.
5. Gate evidence missing or inconsistent → `BLOCKED`, never `PASS`.
