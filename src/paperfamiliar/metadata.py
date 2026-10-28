"""Opt-in reference metadata lookup (V1).

This module proves only that a DOI resolves to metadata. It never produces or
supports `claim_supported`: a real paper can still be misrepresented by the
sentence that cites it. Offline is the default and returns `unavailable_offline`.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

DOI_RE = re.compile(r"^10\.\d{4,9}/[-._;()/:A-Za-z0-9]+$")
CROSSREF = "https://api.crossref.org/works/"
CACHE_TTL_SECONDS = 30 * 24 * 3600


@dataclass
class MetadataResult:
    status: str
    doi: str
    source: str = "crossref"
    title: str | None = None
    authors: list[str] | None = None
    year: int | None = None
    venue: str | None = None
    fetched_at: str | None = None
    detail: str = ""
    claim_support: str = "unknown"

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "doi": self.doi,
            "source": self.source,
            "title": self.title,
            "authors": self.authors or [],
            "year": self.year,
            "venue": self.venue,
            "fetched_at": self.fetched_at,
            "detail": self.detail,
            "claim_support": "unknown",
            "note": "Metadata corroboration never means the cited paper supports the claim.",
        }


def _cache_path(cache_dir: Path, doi: str) -> Path:
    digest = hashlib.sha256(doi.lower().encode()).hexdigest()[:24]
    return cache_dir / "metadata" / f"{digest}.json"


def _parse_crossref(doi: str, message: dict) -> MetadataResult:
    titles = message.get("title") or []
    authors = []
    for author in message.get("author") or []:
        name = " ".join(part for part in (author.get("given"), author.get("family")) if part)
        if name:
            authors.append(name)
    year = None
    for key in ("published-print", "published-online", "issued", "created"):
        parts = (message.get(key) or {}).get("date-parts") or []
        if parts and parts[0] and isinstance(parts[0][0], int):
            year = parts[0][0]
            break
    venues = message.get("container-title") or message.get("publisher") or []
    return MetadataResult(
        status="source_corroborated",
        doi=doi,
        title=titles[0] if titles else None,
        authors=authors,
        year=year,
        venue=venues[0] if venues else None,
        fetched_at=datetime.now(timezone.utc).isoformat(),
        detail="Crossref returned bibliographic metadata for this DOI.",
    )


def lookup_doi(doi: str, *, allow_network: bool = False, cache_dir: Path | None = None,
               timeout: float = 10.0, opener=None, endpoint: str = CROSSREF) -> MetadataResult:
    doi = doi.strip()
    if not DOI_RE.match(doi):
        return MetadataResult("invalid_identifier", doi, detail="Not a syntactically valid DOI.")
    if cache_dir is not None:
        path = _cache_path(cache_dir, doi)
        if path.is_file():
            try:
                cached = json.loads(path.read_text(encoding="utf-8"))
                if time.time() - cached.get("_cached_at", 0) < CACHE_TTL_SECONDS:
                    return MetadataResult(**{k: v for k, v in cached.items() if k != "_cached_at"})
            except (OSError, json.JSONDecodeError, TypeError):
                pass
    if not allow_network:
        return MetadataResult("unavailable_offline", doi,
                              detail="Network access is disabled for this run.")

    url = endpoint + urllib.parse.quote(doi, safe="/:;()")
    request = urllib.request.Request(url, headers={
        "User-Agent": "PaperFamiliar/0.1 (metadata lookup; local user initiated)",
        "Accept": "application/json",
    })
    try:
        open_fn = opener.open if opener is not None else urllib.request.urlopen
        with open_fn(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return MetadataResult("not_found", doi, detail="Crossref has no record for this DOI.")
        return MetadataResult("network_error", doi, detail=f"Crossref returned HTTP {exc.code}.")
    except Exception as exc:  # noqa: BLE001 - network failures are a product state
        return MetadataResult("network_error", doi, detail=f"{type(exc).__name__}: {exc}")
    result = _parse_crossref(doi, payload.get("message", {}))
    if cache_dir is not None:
        path = _cache_path(cache_dir, doi)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = result.as_dict()
        data["_cached_at"] = time.time()
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return result
