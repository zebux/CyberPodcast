#!/usr/bin/env python3
"""Vérifie la santé des liens du catalogue et écrit reports/health.json.

Le script ne bloque jamais la publication : les erreurs réseau sont consignées
dans le rapport. Il est appelé par GitHub Actions avant le rendu du site.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "podcasts.yaml"
OUTPUT = ROOT / "reports" / "health.json"
USER_AGENT = (
    "CyberPodcast-Health/1.0 "
    "(+https://github.com/zebux/CyberPodcast; contact via GitHub issues)"
)
HEADERS = {"User-Agent": USER_AGENT, "Accept": "*/*"}

CHECK_FIELDS = (
    ("site", "website"),
    ("rss", "rss"),
    ("image", "image"),
    ("audio", "last_episode_audio"),
)


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def check_url(url: str, kind: str, timeout: int) -> dict[str, Any]:
    if not url:
        return {"status": "missing", "url": None}
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=timeout,
            allow_redirects=True,
            stream=True,
        )
        content_type = str(response.headers.get("content-type") or "").lower()
        http_status = response.status_code
        final_url = response.url
        response.close()
        status = "ok" if http_status < 400 else "error"
        if status == "ok" and content_type:
            if kind == "image" and "image" not in content_type:
                status = "warning"
            elif kind == "rss" and "html" in content_type:
                status = "warning"
            elif kind == "audio" and "audio" not in content_type and "octet-stream" not in content_type:
                status = "warning"
            elif kind == "site" and "html" not in content_type and "text" not in content_type:
                status = "warning"
        result = {
            "status": status,
            "url": url,
            "http": http_status,
            "content_type": content_type or None,
        }
        if final_url and final_url != url:
            result["final_url"] = final_url
        return result
    except requests.RequestException as exc:
        return {"status": "error", "url": url, "error": str(exc)}
    except Exception as exc:  # pragma: no cover - garde-fou
        return {"status": "error", "url": url, "error": str(exc)}


def build_report(podcasts: list[dict[str, Any]], *, skip_network: bool, workers: int, timeout: int) -> dict[str, Any]:
    started = time.time()
    checks_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    pending: dict[tuple[str, str], str] = {}
    for podcast in podcasts:
        for kind, field in CHECK_FIELDS:
            url = podcast.get(field)
            if not url:
                continue
            key = (kind, str(url))
            pending[key] = str(url)

    if skip_network:
        for key, url in pending.items():
            checks_by_key[key] = {"status": "unchecked", "url": url}
    else:
        log(f"Vérification de {len(pending)} URL…")
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            futures = {
                pool.submit(check_url, url, kind, timeout): (kind, url)
                for (kind, url) in pending.items()
            }
            for future in as_completed(futures):
                kind, url = futures[future]
                try:
                    checks_by_key[(kind, url)] = future.result()
                except Exception as exc:  # pragma: no cover - garde-fou
                    checks_by_key[(kind, url)] = {
                        "status": "error",
                        "url": url,
                        "error": str(exc),
                    }

    rows: list[dict[str, Any]] = []
    for podcast in podcasts:
        checks: dict[str, dict[str, Any]] = {}
        for kind, field in CHECK_FIELDS:
            url = podcast.get(field)
            if not url:
                checks[kind] = {"status": "missing", "url": None}
            else:
                checks[kind] = checks_by_key.get(
                    (kind, str(url)), {"status": "unchecked", "url": url}
                )
        statuses = {check.get("status") for check in checks.values()}
        if "error" in statuses:
            overall = "error"
        elif "warning" in statuses:
            overall = "warning"
        else:
            overall = "ok"
        rows.append(
            {
                "id": podcast.get("id"),
                "name": podcast.get("name"),
                "status": overall,
                "checks": checks,
            }
        )

    summary = {
        "total": len(rows),
        "ok": sum(1 for row in rows if row["status"] == "ok"),
        "warning": sum(1 for row in rows if row["status"] == "warning"),
        "error": sum(1 for row in rows if row["status"] == "error"),
        "missing": sum(
            1
            for row in rows
            for check in row["checks"].values()
            if check.get("status") == "missing"
        ),
        "checked_urls": len(checks_by_key),
    }
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "unchecked" if skip_network else "network",
        "duration_seconds": round(time.time() - started, 2),
        "summary": summary,
        "podcasts": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-network", action="store_true", help="ne pas vérifier les URL")
    parser.add_argument("--workers", type=int, default=16, help="vérifications parallèles")
    parser.add_argument("--timeout", type=int, default=12, help="timeout HTTP en secondes")
    args = parser.parse_args()

    with SOURCE.open(encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    podcasts = payload.get("podcasts") or []
    if not podcasts:
        raise SystemExit(f"Aucun podcast dans {SOURCE}")

    report = build_report(
        podcasts,
        skip_network=args.skip_network,
        workers=max(1, args.workers),
        timeout=max(1, args.timeout),
    )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    summary = report["summary"]
    print(
        f"✓ Santé: {summary['total']} podcasts, {summary['ok']} OK, "
        f"{summary['warning']} vigilances, {summary['error']} erreurs, "
        f"{summary['missing']} liens absents → {OUTPUT.relative_to(ROOT)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
