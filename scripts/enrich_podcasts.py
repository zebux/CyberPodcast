#!/usr/bin/env python3
"""Enrichit la liste des podcasts depuis iTunes + les flux RSS.

Sources  : data/podcasts-*.yaml (un podcast = une entrée)
Curation : data/curated.yaml (liens officiels vérifiés manuellement)
Sortie   : podcasts.yaml (fichier unique, trié, dédupliqué)

Le script est idempotent : il peut être lancé à la main ou par GitHub Actions.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import statistics
import sys
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import feedparser
import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CACHE_DIR = ROOT / ".cache"
OUTPUT = ROOT / "podcasts.yaml"
USER_AGENT = (
    "CyberPodcast-Enricher/1.0 "
    "(+https://github.com/zebux/CyberPodcast; contact via GitHub issues)"
)
HEADERS = {"User-Agent": USER_AGENT, "Accept": "*/*"}
CACHE_TTL = 24 * 3600
HTTP_TIMEOUT = 20
EPISODE_LIMIT = 10

TODAY = datetime.now(timezone.utc).date()

# Liens de plateformes détectés dans les pages officielles et les flux.
PLATFORM_LINK_PATTERNS: dict[str, str] = {
    "deezer": r"https?://(?:www\.)?deezer\.com/[^\"'<>\s]*?/show/\d+",
    "pocket_casts": r"https?://(?:pca\.st|pocketcasts\.com)/[^\"'<>\s]+",
    "podcast_addict": r"https?://podcastaddict\.com/podcast/[^\"'<>\s]+",
    "amazon_music": r"https?://music\.amazon\.[^\"'<>\s]+/podcasts/[^\"'<>\s]+",
    "castbox": r"https?://castbox\.fm/[^\"'<>\s]+",
    "youtube": r"https?://(?:www\.)?(?:youtube\.com|youtu\.be)/[^\"'<>\s]+",
    "spotify": r"https?://open\.spotify\.com/show/[^\"'<>\s]+",
    "apple_podcast": r"https?://podcasts\.apple\.com/[^\"'<>\s]+/podcast/[^\"'<>\s]+",
}

PLATFORMS: list[tuple[str, tuple[str, ...]]] = [
    ("Ausha", ("ausha.co", "ausha")),
    ("Acast", ("acast.com", "acast")),
    ("Podbean", ("podbean.com",)),
    ("Buzzsprout", ("buzzsprout.com",)),
    ("Libsyn", ("libsyn.com",)),
    ("RSS.com", ("rss.com",)),
    ("Simplecast", ("simplecast.com",)),
    ("RedCircle", ("redcircle.com",)),
    ("Anchor", ("anchor.fm",)),
    ("Spotify", ("spotify.com", "spotifycdn.com", "pscdn.co")),
    ("Captivate", ("captivate.fm",)),
    ("Megaphone", ("megaphone.fm",)),
    ("Transistor", ("transistor.fm",)),
    ("Fireside", ("fireside.fm",)),
    ("Audiomeans", ("audiomeans.fr",)),
    ("Spreaker", ("spreaker.com", "pwop.com")),
    ("Zencastr", ("zencastr.com",)),
    ("Podhome", ("podhome.fm",)),
    ("Riverside", ("riverside.com",)),
    ("FeedBurner", ("feedburner.com",)),
    ("Podigee", ("podigee.io",)),
    ("Castos", ("castos.com",)),
    ("Blubrry", ("blubrry.com",)),
    ("Art19", ("art19.com",)),
    ("Omny", ("omny.fm",)),
    ("SoundCloud", ("soundcloud.com",)),
    ("Podcastics", ("podcastics.com",)),
    ("Deezer", ("deezer.com",)),
    ("Castbox", ("castbox.fm",)),
    ("Substack", ("substack.com", "substackcdn.com")),
]

# Sujets normalisés (vocabulaire contrôlé) : mot-clé -> sujet.
TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Cybersécurité": ("cyber", "cybersecurity", "cybersécurité", "sécurité", "security"),
    "SOC": ("soc", "security operations"),
    "SIEM": ("siem", "splunk", "sentinel", "qradar"),
    "EDR": ("edr", "endpoint detection", "crowdstrike", "sentinelone"),
    "XDR": ("xdr",),
    "DFIR": ("dfir", "forensics", "forensic", "incident response", "réponse à incident"),
    "Malware": ("malware", "ransomware", "rançongiciel", "virus"),
    "OSINT": ("osint", "open source intelligence"),
    "Reverse Engineering": ("reverse engineering", "reverse", "reversing"),
    "Pentest": ("pentest", "penetration test", "test d'intrusion", "offensive"),
    "Red Team": ("red team", "redteam", "offensive security"),
    "Blue Team": ("blue team", "blueteam", "defensive security"),
    "Threat Intelligence": ("threat intelligence", "threat intel", "cti", "mitre att&ck"),
    "Cloud Security": ("cloud security", "sécurité cloud", "cspm", "cwpp"),
    "IAM": ("iam", "identity", "identité", "entra id", "active directory"),
    "DevSecOps": ("devsecops", "devsecops", "security as code"),
    "GRC": ("grc", "compliance", "conformité", "rgpd", "gdpr", "audit"),
    "Cryptographie": ("crypto", "cryptographie", "cryptography", "chiffrement"),
    "Juridique": ("juridique", "droit", "legal", "law"),
    "Cloud": ("cloud", "aws", "azure", "gcp", "google cloud"),
    "AWS": ("aws", "amazon web services"),
    "Azure": ("azure", "microsoft cloud"),
    "GCP": ("gcp", "google cloud platform", "google cloud"),
    "Kubernetes": ("kubernetes", "k8s", "aks", "eks", "gke"),
    "Docker": ("docker", "containers", "conteneurs", "container"),
    "Terraform": ("terraform", "opentofu"),
    "Ansible": ("ansible",),
    "Linux": ("linux", "ubuntu", "debian", "red hat", "rhel", "fedora"),
    "Windows": ("windows", "windows server", "active directory"),
    "DevOps": ("devops", "sre", "site reliability", "platform engineering"),
    "GitOps": ("gitops", "argocd", "fluxcd", "argo cd"),
    "CI/CD": ("ci/cd", "cicd", "github actions", "gitlab ci", "jenkins", "pipeline"),
    "Observabilité": ("observability", "observabilité", "prometheus", "grafana", "opentelemetry"),
    "FinOps": ("finops", "cost optimization", "coût cloud"),
    "Réseau": ("network", "réseau", "networking", "cisco", "palo alto", "fortinet"),
    "Open Source": ("open source", "opensource", "oss"),
    "Administration système": ("sysadmin", "administration système", "system administration"),
    "Développement": ("developer", "développeur", "development", "développement", "software engineering"),
    "Architecture": ("architecture", "software architecture", "design"),
    "Python": ("python",),
    "Go": ("golang", "go language"),
    "Java": ("java", "jvm", "kotlin"),
    "Rust": ("rust",),
    "C++": ("c++", "cpp"),
    ".NET": (".net", "dotnet", "c#", "csharp"),
    "JavaScript": ("javascript", "js", "node.js", "nodejs"),
    "React": ("react", "reactjs", "next.js"),
    "Angular": ("angular",),
    "IA": ("ai", "artificial intelligence", "intelligence artificielle", "machine learning", "ml"),
    "LLM": ("llm", "large language model", "gpt", "openai", "claude", "gemini"),
    "MCP": ("mcp", "model context protocol"),
    "Data": ("data engineering", "data science", "data pipeline", "big data"),
    "Carrière": ("career", "carrière", "soft skills", "management"),
    "Histoire": ("history", "histoire"),
}

# Tags libres : mot-clé -> tag.
TAG_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Azure": ("azure",),
    "Sentinel": ("sentinel", "microsoft sentinel"),
    "AKS": ("aks", "azure kubernetes"),
    "Helm": ("helm",),
    "Traefik": ("traefik",),
    "ArgoCD": ("argocd", "argo cd"),
    "FluxCD": ("fluxcd", "flux cd"),
    "Docker Compose": ("docker compose",),
    "Hyper-V": ("hyper-v", "hyperv"),
    "VMware": ("vmware", "vsphere", "esxi"),
    "Active Directory": ("active directory", "ad ds"),
    "Entra ID": ("entra id", "azure ad"),
    "Microsoft Defender": ("defender", "microsoft defender"),
    "Azure Firewall": ("azure firewall",),
    "Palo Alto": ("palo alto", "pan-os"),
    "Fortinet": ("fortinet", "fortigate"),
    "Cisco": ("cisco",),
    "Windows Server": ("windows server",),
    "Splunk": ("splunk",),
    "Elastic": ("elastic", "elasticsearch", "elk"),
    "Wazuh": ("wazuh",),
    "CrowdStrike": ("crowdstrike",),
    "HarfangLab": ("harfanglab",),
    "Gatewatcher": ("gatewatcher",),
    "MITRE ATT&CK": ("mitre", "att&ck"),
    "SANS": ("sans institute", "sans conference", "sans.org"),
    "AWS": ("aws", "amazon web services"),
    "GCP": ("gcp", "google cloud"),
    "Kubernetes": ("kubernetes", "k8s"),
    "Docker": ("docker",),
    "Terraform": ("terraform", "opentofu"),
    "Ansible": ("ansible",),
    "GitHub": ("github",),
    "GitLab": ("gitlab",),
    "Prometheus": ("prometheus",),
    "Grafana": ("grafana",),
    "OpenTelemetry": ("opentelemetry",),
    "CNCF": ("cncf", "cloud native"),
    "OpenStack": ("openstack",),
    "Proxmox": ("proxmox",),
    "Homelab": ("homelab", "self-hosted", "auto-hébergement"),
    "Python": ("python",),
    "Go": ("golang",),
    "Rust": ("rust",),
    "Java": ("java",),
    "C++": ("c++", "cpp"),
    ".NET": (".net", "dotnet", "c#"),
    "JavaScript": ("javascript", "node.js", "nodejs"),
    "React": ("react",),
    "Angular": ("angular",),
    "LLM": ("llm", "gpt", "openai", "claude", "gemini"),
    "OpenAI": ("openai", "gpt"),
    "Anthropic": ("anthropic", "claude"),
}

STOPWORDS = {
    "the", "le", "la", "les", "de", "des", "du", "un", "une", "et", "and",
    "podcast", "podcasts", "show", "a", "of", "from", "with", "sur",
}


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(c for c in value if not unicodedata.combining(c))
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def normalize_name(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(c for c in value if not unicodedata.combining(c))
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(w for w in value.split() if w not in STOPWORDS)


def clean_text(value: Any, limit: int = 200) -> str | None:
    if not value:
        return None
    value = re.sub(r"<[^>]+>", " ", str(value))
    value = html.unescape(value)
    value = re.sub(r"\s+", " ", value).strip()
    if not value:
        return None
    if len(value) <= limit:
        return value
    cut = value[:limit]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(" ,;:-") + "…"


def as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return [str(v) for v in value if v is not None]
    return [str(value)]


def dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        value = value.strip()
        if not value:
            continue
        key = value.casefold()
        if key not in seen:
            seen.add(key)
            result.append(value)
    return result


def cache_path(kind: str, key: str, suffix: str) -> Path:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
    folder = CACHE_DIR / kind
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{digest}{suffix}"


def cache_get(path: Path) -> bytes | None:
    if not path.exists():
        return None
    if time.time() - path.stat().st_mtime > CACHE_TTL:
        return None
    return path.read_bytes()


def cache_put(path: Path, data: bytes) -> None:
    path.write_bytes(data)


def normalize_url(url: str | None) -> str | None:
    if not url:
        return None
    url = str(url).strip()
    if not url:
        return None
    if url.startswith("//"):
        return "https:" + url
    if not re.match(r"^https?://", url, re.IGNORECASE):
        return "https://" + url
    return url


def clean_url(url: str | None) -> str | None:
    if not url:
        return None
    value = html.unescape(str(url)).strip()
    value = value.rstrip(".,;:)\\\"'")
    return normalize_url(value)


def http_get(url: str, *, timeout: int = HTTP_TIMEOUT) -> requests.Response | None:
    url = normalize_url(url) or url
    try:
        response = requests.get(
            url, headers=HEADERS, timeout=timeout, allow_redirects=True
        )
        return response
    except requests.RequestException as exc:
        log(f"  ! HTTP {url}: {exc}")
        return None


def fetch_cached(url: str, kind: str, suffix: str) -> bytes | None:
    path = cache_path(kind, url, suffix)
    cached = cache_get(path)
    if cached is not None:
        return cached
    response = http_get(url)
    if response is None or not response.ok:
        if response is not None:
            log(f"  ! HTTP {response.status_code} {url}")
        return None
    cache_put(path, response.content)
    return response.content


def apple_community_rating(url: str | None) -> tuple[float | None, int | None]:
    if not url:
        return None, None
    content = fetch_cached(url, "apple", ".html")
    if not content:
        return None, None
    text = content.decode("utf-8", "ignore")
    patterns = (
        r'"aggregateRating"\s*:\s*\{[^{}]*?"ratingValue"\s*:\s*([0-9.]+)[^{}]*?"(?:reviewCount|ratingCount)"\s*:\s*(\d+)',
        r'"aggregateRating"\s*:\s*\{[^{}]*?"(?:reviewCount|ratingCount)"\s*:\s*(\d+)[^{}]*?"ratingValue"\s*:\s*([0-9.]+)',
    )
    for index, pattern in enumerate(patterns):
        match = re.search(pattern, text)
        if not match:
            continue
        if index == 0:
            value, count = match.group(1), int(match.group(2))
        else:
            count, value = int(match.group(1)), match.group(2)
        if count <= 0:
            continue
        try:
            return round(float(value), 1), count
        except ValueError:
            return None, None
    return None, None


def url_ok(url: str | None) -> bool:
    if not url:
        return False
    response = http_get(url, timeout=15)
    return bool(response and response.ok)


def parse_feed_url(url: str | None) -> tuple[Any, bool]:
    if not url:
        return None, False
    raw = fetch_cached(url, "rss", ".xml")
    if raw is None:
        return None, True
    parsed = feedparser.parse(raw)
    if getattr(parsed, "bozo", False) and not parsed.entries:
        return None, True
    return parsed, False


_itunes_lock = threading.Lock()
_itunes_failures = 0
_ITUNES_MAX_FAILURES = 5


def itunes_search(term: str, country: str) -> list[dict[str, Any]]:
    global _itunes_failures

    with _itunes_lock:
        if _itunes_failures >= _ITUNES_MAX_FAILURES:
            return []

    params = {
        "term": term,
        "entity": "podcast",
        "media": "podcast",
        "limit": 8,
        "country": country,
    }
    key = json.dumps(params, sort_keys=True)
    path = cache_path("itunes", key, ".json")
    raw = cache_get(path)
    if raw is None:
        last_error: str | None = None
        for attempt, delay in enumerate((0, 3, 8)):
            if delay:
                time.sleep(delay)
            try:
                response = requests.get(
                    "https://itunes.apple.com/search",
                    params=params,
                    headers=HEADERS,
                    timeout=HTTP_TIMEOUT,
                )
                if response.status_code in (403, 429):
                    last_error = f"HTTP {response.status_code}"
                    continue
                response.raise_for_status()
                raw = response.content
                cache_put(path, raw)
                with _itunes_lock:
                    _itunes_failures = 0
                break
            except requests.RequestException as exc:
                last_error = str(exc)
        if raw is None:
            with _itunes_lock:
                _itunes_failures += 1
                disabled = _itunes_failures >= _ITUNES_MAX_FAILURES
            log(f"  ! iTunes {term}: {last_error}" + (" (iTunes désactivé)" if disabled else ""))
            return []
    try:
        return json.loads(raw).get("results", [])
    except (ValueError, AttributeError):
        return []


FEED_HOST_PATTERN = re.compile(
    r"https?://(?:"
    r"feed\.ausha\.co|feeds\.acast\.com|feeds\.buzzsprout\.com|"
    r"feeds\.simplecast\.com|feeds\.redcircle\.com|feeds\.captivate\.fm|"
    r"feeds\.transistor\.fm|feeds\.megaphone\.fm|anchor\.fm/s/|"
    r"[a-z0-9-]+\.libsyn\.com|feed\.podbean\.com|"
    r"feeds\.podcastics\.com|rss\.com/podcasts|"
    r"feeds\.fireside\.fm|api\.spreaker\.de|feeds\.soundcloud\.com|"
    r"feeds\.audiomeans\.fr|pwop\.com/feed|spreaker\.com/show|"
    r"feeds\.zencastr\.com|serve\.podhome\.fm|"
    r"api\.riverside\.com/hosting|feeds\.feedburner\.com"
    r")[^\"'<>\s]+",
    re.IGNORECASE,
)


def is_valid_feed(url: str) -> bool:
    raw = fetch_cached(url, "rss", ".xml")
    if raw is None:
        return False
    parsed = feedparser.parse(raw)
    return bool(parsed.entries)


def discover_feed(website: str | None) -> str | None:
    """Cherche le flux RSS officiel depuis le site (autodiscovery + plateformes)."""
    if not website:
        return None
    content = fetch_cached(website, "site", ".html")
    if not content:
        return None
    text = content.decode("utf-8", "ignore")
    candidates: list[str] = []

    for tag in re.findall(r"<link[^>]+>", text, re.IGNORECASE):
        if re.search(r"application/(?:rss|atom)\+xml", tag, re.IGNORECASE):
            href = re.search(r"href=[\"']([^\"']+)", tag, re.IGNORECASE)
            if href:
                candidates.append(urljoin(website, html.unescape(href.group(1))))

    candidates.extend(html.unescape(m.group(0)) for m in FEED_HOST_PATTERN.finditer(text))

    for match in re.finditer(
        r"href=[\"']([^\"']*(?:rss|feed)[^\"']*)[\"']", text, re.IGNORECASE
    ):
        candidates.append(urljoin(website, html.unescape(match.group(1))))

    base = website.rstrip("/")
    candidates.extend(
        f"{base}{path}"
        for path in (
            "/feed",
            "/feed.xml",
            "/rss",
            "/rss.xml",
            "/podcast.xml",
            "/podcast.rss",
            "/episodes/feed",
            "/feed/podcast",
            "/rss/podcast",
        )
    )

    seen: set[str] = set()
    for candidate in candidates:
        candidate = candidate.strip().rstrip(".,;)\\\"'")
        if candidate in seen or not candidate.startswith("http"):
            continue
        seen.add(candidate)
        if is_valid_feed(candidate):
            return candidate
    return None


def name_similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    ratio = SequenceMatcher(None, left, right).ratio()
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    if left_tokens and right_tokens:
        jaccard = len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
        ratio = max(ratio, jaccard)
    return ratio


def collection_score(entry_name: str, candidate: dict[str, Any]) -> float:
    target = normalize_name(entry_name)
    names = [
        normalize_name(candidate.get("collectionName", "")),
        normalize_name(candidate.get("trackName", "")),
    ]
    return max((name_similarity(target, name) for name in names if name), default=0.0)


def best_itunes_match(name: str, country: str) -> dict[str, Any] | None:
    results = itunes_search(name, country)
    if not results:
        return None
    ranked = sorted(results, key=lambda r: collection_score(name, r), reverse=True)
    best = ranked[0]
    if collection_score(name, best) < 0.78:
        return None
    return best


def parse_duration(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) / 60 if value > 1000 else float(value)
    text = str(value).strip()
    if not text:
        return None
    if re.fullmatch(r"\d+(\.\d+)?", text):
        seconds = float(text)
        return seconds / 60 if seconds > 1000 else seconds
    parts = text.split(":")
    try:
        parts = [float(p) for p in parts]
    except ValueError:
        return None
    seconds = 0.0
    for part in parts:
        seconds = seconds * 60 + part
    return seconds / 60 if seconds > 0 else None


def episode_duration(entry: Any) -> float | None:
    duration = parse_duration(entry.get("itunes_duration"))
    if duration and 0 < duration < 600:
        return duration
    for link in entry.get("links", []):
        if link.get("rel") == "enclosure" and link.get("href", "").startswith("http"):
            length = link.get("length")
            try:
                length = float(length)
            except (TypeError, ValueError):
                continue
            if length > 0:
                minutes = length * 8 / 128_000 / 60
                if 1 < minutes < 600:
                    return minutes
    return None


FRENCH_MONTHS = {
    "janv": 1, "janvier": 1,
    "fevr": 2, "fevrier": 2,
    "mars": 3,
    "avr": 4, "avril": 4,
    "mai": 5,
    "juin": 6,
    "juil": 7, "juillet": 7,
    "aout": 8,
    "sept": 9, "septembre": 9,
    "oct": 10, "octobre": 10,
    "nov": 11, "novembre": 11,
    "dec": 12, "decembre": 12,
}


def parse_text_date(value: str) -> datetime | None:
    match = re.search(r"(\d{1,2})\s+([^\s,]+)\.?\s+(\d{4})", value)
    if not match:
        return None
    day = int(match.group(1))
    token = unicodedata.normalize("NFKD", match.group(2)).encode("ascii", "ignore").decode().lower().strip(".")
    month = FRENCH_MONTHS.get(token)
    if not month:
        return None
    try:
        return datetime(int(match.group(3)), month, day, tzinfo=timezone.utc)
    except ValueError:
        return None


def feed_date(entry: Any) -> datetime | None:
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        value = entry.get(key)
        if value:
            try:
                return datetime(*value[:6], tzinfo=timezone.utc)
            except (TypeError, ValueError):
                continue
    for key in ("published", "updated", "created"):
        value = entry.get(key)
        if value:
            parsed = parse_text_date(str(value))
            if parsed:
                return parsed
    return None


def entry_audio_url(entry: Any) -> str | None:
    for link in entry.get("links", []) or []:
        if link.get("rel") != "enclosure":
            continue
        href = link.get("href")
        if not href:
            continue
        content_type = str(link.get("type") or "").lower()
        if content_type.startswith("audio") or not content_type:
            return clean_url(href)
    return None


def extract_episodes(feed_entries: list[Any]) -> list[dict[str, Any]]:
    episodes: list[dict[str, Any]] = []
    ordered = sorted(
        feed_entries,
        key=lambda item: feed_date(item) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    for entry in ordered:
        title = clean_text(entry.get("title"), 200)
        if not title:
            continue
        date = feed_date(entry)
        url = clean_url(entry.get("link"))
        if not url:
            for link in entry.get("links", []) or []:
                if link.get("rel") == "alternate" and link.get("href"):
                    url = clean_url(link.get("href"))
                    break
        duration = episode_duration(entry)
        episodes.append(
            {
                "title": title,
                "published": date.date().isoformat() if date else None,
                "url": url,
                "audio": entry_audio_url(entry),
                "duration": round(duration) if duration else None,
            }
        )
        if len(episodes) >= EPISODE_LIMIT:
            break
    return episodes


def compute_frequency(episodes: list[dict[str, Any]]) -> tuple[str | None, int | None]:
    dates = sorted(
        {
            datetime.strptime(episode["published"], "%Y-%m-%d").date()
            for episode in episodes
            if episode.get("published")
        },
        reverse=True,
    )
    if len(dates) < 2:
        return None, None
    gaps = [
        (newer - older).days
        for newer, older in zip(dates, dates[1:])
        if (newer - older).days > 0
    ]
    if not gaps:
        return None, None
    days = round(statistics.median(gaps[:12]))
    if days <= 3:
        frequency = "daily"
    elif days <= 10:
        frequency = "weekly"
    elif days <= 21:
        frequency = "biweekly"
    elif days <= 45:
        frequency = "monthly"
    elif days <= 120:
        frequency = "quarterly"
    else:
        frequency = "irregular"
    return frequency, days


def feed_image(feed_meta: Any, feed_entries: list[Any]) -> str | None:
    image = feed_meta.get("image") if hasattr(feed_meta, "get") else None
    if isinstance(image, dict) and image.get("href"):
        return clean_url(image.get("href"))
    for entry in feed_entries:
        image = entry.get("image") if hasattr(entry, "get") else None
        if isinstance(image, dict) and image.get("href"):
            return clean_url(image.get("href"))
        for link in entry.get("links", []) or []:
            if str(link.get("rel") or "").lower() == "image" and link.get("href"):
                return clean_url(link.get("href"))
    return None


def discover_platform_links(
    website: str | None, feed_meta: Any, feed_entries: list[Any]
) -> dict[str, str | None]:
    parts: list[str] = []
    if website:
        content = fetch_cached(website, "site", ".html")
        if content:
            parts.append(content.decode("utf-8", "ignore"))
    if hasattr(feed_meta, "get"):
        parts.append(str(feed_meta.get("link") or ""))
        parts.append(str(feed_meta.get("generator") or ""))
    for entry in feed_entries[:5]:
        parts.append(str(entry.get("link") or ""))
        for link in entry.get("links", []) or []:
            parts.append(str(link.get("href") or ""))
    haystack = " ".join(part for part in parts if part)
    found: dict[str, str | None] = {}
    for field, pattern in PLATFORM_LINK_PATTERNS.items():
        match = re.search(pattern, haystack, re.IGNORECASE)
        found[field] = clean_url(match.group(0)) if match else None
    return found


def detect_platform(hints: list[str]) -> str | None:
    haystack = " ".join(h for h in hints if h).lower()
    for name, needles in PLATFORMS:
        if any(needle in haystack for needle in needles):
            return name
    return None


_KEYWORD_PATTERNS: dict[str, re.Pattern[str]] = {}


def keyword_present(haystack: str, needle: str) -> bool:
    if not needle:
        return False
    pattern = _KEYWORD_PATTERNS.get(needle)
    if pattern is None:
        pattern = re.compile(
            r"(?<![0-9a-z])" + re.escape(needle) + r"(?![0-9a-z])",
            re.IGNORECASE,
        )
        _KEYWORD_PATTERNS[needle] = pattern
    return bool(pattern.search(haystack))


def detect_topics(text: str, categories: list[str]) -> list[str]:
    haystack = f"{text} {' '.join(categories)}"
    topics = [topic for topic, needles in TOPIC_KEYWORDS.items()
              if any(keyword_present(haystack, needle) for needle in needles)]
    return dedupe(topics)


def detect_tags(text: str, categories: list[str]) -> list[str]:
    haystack = f"{text} {' '.join(categories)}"
    tags = [tag for tag, needles in TAG_KEYWORDS.items()
            if any(keyword_present(haystack, needle) for needle in needles)]
    return dedupe(tags)


def infer_country(language: str | None, seed: str | None) -> str:
    if seed:
        return seed.upper()
    if language == "fr":
        return "FR"
    if language == "en":
        return "US"
    return "??"


def compute_status(last_episode: str | None, fallback: str | None) -> str:
    if not last_episode:
        return fallback or "archived"
    try:
        date = datetime.strptime(last_episode, "%Y-%m-%d").date()
    except ValueError:
        return fallback or "archived"
    age = (TODAY - date).days
    if age < 183:
        return "active"
    if age < 730:
        return "slow"
    return "archived"


def load_sources() -> list[dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for path in sorted(DATA_DIR.glob("podcasts-*.yaml")):
        with path.open(encoding="utf-8") as handle:
            payload = yaml.safe_load(handle) or {}
        items = payload.get("podcasts", []) if isinstance(payload, dict) else payload
        for item in items or []:
            if not isinstance(item, dict) or not item.get("id"):
                continue
            entry = dict(item)
            entry_id = str(entry["id"])
            if entry_id not in entries:
                entries[entry_id] = entry
                order.append(entry_id)
                continue
            current = entries[entry_id]
            for key, value in entry.items():
                if key in ("category", "categories"):
                    continue
                if current.get(key) in (None, "", []) and value not in (None, "", []):
                    current[key] = value
            current["category"] = dedupe(
                as_list(current.get("category")) + as_list(entry.get("category"))
            )
    return [entries[entry_id] for entry_id in order]


def load_curated() -> dict[str, dict[str, Any]]:
    path = DATA_DIR / "curated.yaml"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    return payload.get("curated", {}) or {}


FALLBACK_FIELDS = (
    "website",
    "rss",
    "youtube",
    "spotify",
    "apple_podcast",
    "linkedin",
    "deezer",
    "pocket_casts",
    "podcast_addict",
    "amazon_music",
    "castbox",
    "image",
    "author",
    "description",
    "last_episode",
    "last_episode_title",
    "last_episode_url",
    "last_episode_audio",
    "last_episode_duration",
    "episodes",
    "frequency",
    "frequency_days",
    "first_seen",
    "episode_count",
    "average_duration",
    "community_rating",
    "community_rating_count",
    "platform",
    "hosts",
    "topics",
    "tags",
)


def load_previous() -> dict[str, dict[str, Any]]:
    if not OUTPUT.exists():
        return {}
    try:
        with OUTPUT.open(encoding="utf-8") as handle:
            payload = yaml.safe_load(handle) or {}
    except (OSError, yaml.YAMLError):
        return {}
    return {
        str(podcast["id"]): podcast
        for podcast in (payload.get("podcasts") or [])
        if podcast.get("id")
    }


def enrich_one(seed: dict[str, Any], curated: dict[str, Any], previous: dict[str, Any]) -> dict[str, Any]:
    entry_id = str(seed["id"])
    name = str(seed.get("name") or entry_id)
    overrides = dict(curated.get(entry_id, {}))
    language = overrides.get("language") or seed.get("language")
    country = overrides.get("country") or seed.get("country")
    log(f"→ {name}")

    website = overrides.get("website") or seed.get("website")
    rss_url = overrides.get("rss") or seed.get("rss")
    skip_discovery = bool(
        overrides.get("skip_rss_discovery") or seed.get("skip_rss_discovery")
    )

    # 1) autodiscovery du flux depuis le site officiel
    if not rss_url and website and not skip_discovery:
        rss_url = discover_feed(website)

    # 2) iTunes : lien Apple + flux de secours
    itunes_country = "fr" if language == "fr" else "us"
    skip_itunes = bool(overrides.get("skip_itunes") or seed.get("skip_itunes"))
    itunes = None if skip_itunes else best_itunes_match(name, itunes_country)
    apple_url = overrides.get("apple_podcast") or seed.get("apple_podcast")
    if not apple_url and itunes:
        apple_url = itunes.get("collectionViewUrl")
    if not rss_url and itunes:
        rss_url = itunes.get("feedUrl")

    feed, feed_error = parse_feed_url(rss_url) if rss_url else (None, False)
    feed_meta = feed.feed if feed else {}

    # 3) derniers recours : lien du flux -> site, puis page iTunes
    if not website:
        website = feed_meta.get("link")
    if not rss_url and feed_meta.get("link") and not skip_discovery:
        rss_url = discover_feed(feed_meta.get("link"))
        if rss_url:
            feed, feed_error = parse_feed_url(rss_url)
            feed_meta = feed.feed if feed else {}
    if not website:
        website = (itunes or {}).get("artistViewUrl")

    feed_entries = list(feed.entries) if feed and feed.entries else []

    episodes = overrides.get("episodes") or seed.get("episodes") or extract_episodes(feed_entries)
    if not isinstance(episodes, list):
        episodes = []
    latest_episode = episodes[0] if episodes else {}
    frequency, frequency_days = compute_frequency(episodes)
    if overrides.get("frequency"):
        frequency = overrides["frequency"]
    if overrides.get("frequency_days") is not None:
        frequency_days = int(overrides["frequency_days"])

    last_dt: datetime | None = None
    timed_entries: list[tuple[datetime, float | None]] = []
    for item in feed_entries:
        date = feed_date(item)
        if date and (last_dt is None or date > last_dt):
            last_dt = date
        timed_entries.append((date or datetime.min.replace(tzinfo=timezone.utc), episode_duration(item)))

    last_episode = overrides.get("last_episode") or seed.get("last_episode")
    if not last_episode:
        last_episode = latest_episode.get("published")
    if last_dt and not overrides.get("last_episode"):
        last_episode = last_dt.date().isoformat()

    last_episode_title = (
        overrides.get("last_episode_title")
        or seed.get("last_episode_title")
        or latest_episode.get("title")
    )
    last_episode_url = (
        overrides.get("last_episode_url")
        or seed.get("last_episode_url")
        or latest_episode.get("url")
    )
    last_episode_audio = (
        overrides.get("last_episode_audio")
        or seed.get("last_episode_audio")
        or latest_episode.get("audio")
    )
    last_episode_duration = (
        overrides.get("last_episode_duration")
        or seed.get("last_episode_duration")
        or latest_episode.get("duration")
    )

    itunes_count = itunes.get("trackCount") if itunes else None
    try:
        itunes_count = int(itunes_count) if itunes_count is not None else None
    except (TypeError, ValueError):
        itunes_count = None
    episode_count = overrides.get("episode_count") or seed.get("episode_count")
    if episode_count is None:
        candidates = [n for n in (len(feed_entries), itunes_count) if n]
        episode_count = max(candidates) if candidates else None

    average_duration = overrides.get("average_duration") or seed.get("average_duration")
    if average_duration is None and timed_entries:
        recent = sorted(timed_entries, key=lambda item: item[0], reverse=True)[:20]
        recent_durations = [duration for _, duration in recent if duration]
        if len(recent_durations) >= max(3, len(recent) // 2):
            average_duration = round(statistics.median(recent_durations))

    description = (
        overrides.get("description")
        or seed.get("description")
        or clean_text(feed_meta.get("subtitle"))
        or clean_text(feed_meta.get("summary"))
        or clean_text(feed_meta.get("description"))
    )
    description = clean_text(description)

    categories = dedupe(as_list(seed.get("category")) + as_list(overrides.get("category")))
    feed_categories = [c.get("term", "") for c in feed_meta.get("tags", []) if isinstance(c, dict)]
    context = " ".join(
        filter(None, [name, description or "", " ".join(categories), " ".join(feed_categories)])
    )

    topics = dedupe(
        as_list(overrides.get("topics"))
        or as_list(seed.get("topics"))
        or detect_topics(context, categories)
    )
    tags = dedupe(
        as_list(overrides.get("tags"))
        or as_list(seed.get("tags"))
        or detect_tags(context, categories)
        or [c for c in feed_categories if c]
        or categories
    )

    discovered_links = discover_platform_links(website, feed_meta, feed_entries)
    if not apple_url:
        apple_url = discovered_links.get("apple_podcast")

    hints = [rss_url or "", website or "", feed_meta.get("generator", "")]
    hints.extend(value for value in discovered_links.values() if value)
    if feed_entries:
        hints.append(str(feed_entries[0].get("id", "")))
        for link in feed_entries[0].get("links", []):
            hints.append(link.get("href", ""))
    platform = overrides.get("platform") or seed.get("platform") or detect_platform(hints) or "autre"

    feed_author = feed_meta.get("author")
    if not feed_author:
        feed_author = (feed_meta.get("author_detail") or {}).get("name")
    if overrides.get("hosts"):
        hosts = dedupe(as_list(overrides["hosts"]))
    else:
        hosts = dedupe(
            as_list(seed.get("hosts"))
            + as_list(seed.get("host"))
        ) or dedupe(as_list(feed_author))
    status = compute_status(last_episode, seed.get("status"))
    if overrides.get("status"):
        status = overrides["status"]

    rating = overrides.get("community_rating") or seed.get("community_rating")
    rating_count = overrides.get("community_rating_count") or seed.get(
        "community_rating_count"
    )
    if apple_url and (rating is None or rating_count is None):
        apple_rating, apple_count = apple_community_rating(apple_url)
        if rating is None:
            rating = apple_rating
        if rating_count is None:
            rating_count = apple_count

    youtube = (
        overrides.get("youtube")
        or seed.get("youtube")
        or discovered_links.get("youtube")
    )
    spotify = (
        overrides.get("spotify")
        or seed.get("spotify")
        or discovered_links.get("spotify")
    )
    linkedin = overrides.get("linkedin") or seed.get("linkedin")
    image = overrides.get("image") or seed.get("image") or feed_image(feed_meta, feed_entries)
    if not image and itunes:
        image = itunes.get("artworkUrl600") or itunes.get("artworkUrl100")
    author = (
        overrides.get("author")
        or seed.get("author")
        or feed_author
        or (itunes or {}).get("artistName")
    )

    result: dict[str, Any] = {
        "id": entry_id,
        "name": name,
        "category": categories,
        "language": language or "fr",
        "country": infer_country(language, country),
        "hosts": hosts,
        "website": normalize_url(website),
        "rss": normalize_url(
            rss_url if feed and not feed_error else (overrides.get("rss") or None)
        ),
        "youtube": normalize_url(youtube),
        "spotify": normalize_url(spotify),
        "apple_podcast": normalize_url(apple_url),
        "linkedin": normalize_url(linkedin),
        "deezer": normalize_url(
            overrides.get("deezer") or seed.get("deezer") or discovered_links.get("deezer")
        ),
        "pocket_casts": normalize_url(
            overrides.get("pocket_casts")
            or seed.get("pocket_casts")
            or discovered_links.get("pocket_casts")
        ),
        "podcast_addict": normalize_url(
            overrides.get("podcast_addict")
            or seed.get("podcast_addict")
            or discovered_links.get("podcast_addict")
        ),
        "amazon_music": normalize_url(
            overrides.get("amazon_music")
            or seed.get("amazon_music")
            or discovered_links.get("amazon_music")
        ),
        "castbox": normalize_url(
            overrides.get("castbox")
            or seed.get("castbox")
            or discovered_links.get("castbox")
        ),
        "image": normalize_url(image),
        "author": author,
        "description": description,
        "last_episode": last_episode,
        "last_episode_title": last_episode_title,
        "last_episode_url": normalize_url(last_episode_url),
        "last_episode_audio": normalize_url(last_episode_audio),
        "last_episode_duration": last_episode_duration,
        "episodes": episodes,
        "frequency": frequency,
        "frequency_days": frequency_days,
        "first_seen": (previous.get(entry_id) or {}).get("first_seen") or TODAY.isoformat(),
        "updated_at": TODAY.isoformat(),
        "episode_count": episode_count,
        "average_duration": average_duration,
        "status": status,
        "community_rating": float(rating) if rating is not None else None,
        "community_rating_count": (
            int(rating_count) if rating_count is not None else None
        ),
        "platform": platform,
        "topics": topics,
        "tags": tags,
    }

    previous_entry = previous.get(entry_id) or {}
    for field in FALLBACK_FIELDS:
        current = result.get(field)
        old = previous_entry.get(field)
        if (current in (None, "", []) or (field == "platform" and current == "autre")) and old not in (None, "", []):
            result[field] = old
    if not overrides.get("status"):
        result["status"] = compute_status(result.get("last_episode"), seed.get("status"))
    return result


def merge_duplicates(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    index_by_key: dict[str, int] = {}

    def keys(entry: dict[str, Any]) -> list[str]:
        result = [f"id:{entry['id']}"]
        name_key = re.sub(r"[^a-z0-9]", "", normalize_name(entry["name"]))
        if name_key:
            result.append(f"name:{name_key}")
        return result

    for entry in entries:
        found = None
        for key in keys(entry):
            if key in index_by_key:
                found = index_by_key[key]
                break
        if found is None:
            index_by_key.update({key: len(merged) for key in keys(entry)})
            merged.append(entry)
            continue

        target = merged[found]
        for field, value in entry.items():
            if field in ("id", "name"):
                continue
            if field in ("category", "topics", "tags", "hosts"):
                target[field] = dedupe(as_list(target.get(field)) + as_list(value))
            elif target.get(field) in (None, "", []):
                target[field] = value
        for key in keys(target):
            index_by_key[key] = found
        log(f"  = doublon fusionné: {entry['name']} → {target['name']}")
    return merged


def write_output(entries: list[dict[str, Any]]) -> None:
    payload = {
        "version": 3,
        "count": len(entries),
        "podcasts": entries,
    }
    with OUTPUT.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(
            payload,
            handle,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
            width=1000,
        )
    log(f"\n✓ {len(entries)} podcasts écrits dans {OUTPUT.relative_to(ROOT)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=6, help="requêtes parallèles")
    parser.add_argument("--clear-cache", action="store_true", help="vide le cache HTTP")
    args = parser.parse_args()

    if args.clear_cache and CACHE_DIR.exists():
        import shutil

        shutil.rmtree(CACHE_DIR)

    seeds = load_sources()
    curated = load_curated()
    previous = load_previous()
    log(f"{len(seeds)} podcasts en entrée, {len(curated)} entrées curatées\n")

    enriched: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {
            pool.submit(enrich_one, seed, curated, previous): seed for seed in seeds
        }
        for future in as_completed(futures):
            seed = futures[future]
            try:
                enriched.append(future.result())
            except Exception as exc:  # pragma: no cover - garde-fou
                log(f"  ! échec {seed.get('id')}: {exc}")
                enriched.append({
                    **seed,
                    "category": as_list(seed.get("category")),
                    "hosts": as_list(seed.get("hosts")) + as_list(seed.get("host")),
                })

    order = {str(seed["id"]): i for i, seed in enumerate(seeds)}
    enriched.sort(key=lambda e: order.get(str(e["id"]), 10_000))
    enriched = merge_duplicates(enriched)
    write_output(enriched)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
