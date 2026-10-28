# ADR-0004: Offline by default, every outbound request individually authorized

- Status: accepted
- Date: 2026-10-28

## Context

Manuscripts are unpublished research. The product must work with no network, no API key and no account. Two features can reach the network: reference metadata lookup and optional model providers. Both must be visible and revocable.

## Decision

- The application starts in `strict_offline` mode when no provider is configured and no metadata lookup is enabled. In this mode no code path performs DNS or outbound TCP.
- The UI loads no CDN assets, web fonts, telemetry or update checks. Fonts are bundled or system fonts.
- Reference metadata lookup (V1) is opt-in per run. The preview lists every identifier that would be sent, the endpoint, and the fact that titles are leaving the machine.
- Model providers are opt-in. Before each cloud request the UI shows the actual payload bytes (truncated with an explicit notice), provider, endpoint, estimated tokens, redaction summary and a data-egress warning. The user confirms that request; consent is not remembered for later payloads unless the user explicitly enables a session consent.
- API keys are read from environment variables or the OS credential store, are never written to logs, reports, exports, SQLite or the repository, and are redacted in diagnostic output.
- Local providers (`Ollama`, any OpenAI-compatible base URL on loopback) are the default model path. A missing local model degrades to the deterministic offline feature set with an explicit `unavailable` status.
- Content from a manuscript, including comments, is untrusted data. A prompt-injection attempt in a `.tex` comment cannot change system policy, trigger tool use, or exfiltrate keys.

## Consequences

- Offline acceptance can be demonstrated by showing zero outbound connections during a full demo run, while loopback stays available.
- Tests must distinguish "no network" (CLI/headless) from "desktop UI with loopback only"; the two are separate evidence items.
- Cloud claims are limited to what was actually tested. Without a real key, the status is `UNTESTED_CLOUD_REAL`.
