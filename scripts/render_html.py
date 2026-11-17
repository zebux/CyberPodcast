#!/usr/bin/env python3
"""Génère le site statique CyberPodcast depuis podcasts.yaml.

Produit :
  - docs/index.html               annuaire filtrable
  - docs/podcast/<id>.html        fiches détaillées
  - docs/episodes.html            derniers épisodes publiés
  - docs/sujets.html              exploration par sujet
  - docs/statistiques.html        chiffres clés
  - docs/a-propos.html            présentation du projet
  - docs/contribuer.html          guide de contribution
  - docs/api/*.json               données publiques
  - docs/sitemap.xml, robots.txt, feed.xml, 404.html
"""

from __future__ import annotations

import html as html_lib
import json
import re
import statistics
from collections import Counter
from datetime import date, datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse
from xml.sax.saxutils import escape as xml_escape, quoteattr

import yaml

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "podcasts.yaml"
REPORTS_DIR = ROOT / "reports"
OUTPUT_DIR = ROOT / "docs"
ASSETS_DIR = OUTPUT_DIR / "assets"
BASE_URL = "https://cyberpodcast.fr"
REPO_URL = "https://github.com/zebux/CyberPodcast"
GENERATED_AT = datetime.now(timezone.utc)
TODAY = GENERATED_AT.date()

STATUS_LABELS = {
    "active": "Actif",
    "slow": "Peu actif",
    "archived": "Inactif",
}
STATUS_ORDER = {"active": 0, "slow": 1, "archived": 2}

LANGUAGE_LABELS = {
    "fr": "Français",
    "en": "Anglais",
}

FREQUENCY_LABELS = {
    "daily": "Quotidien",
    "weekly": "Hebdomadaire",
    "biweekly": "Toutes les 2 semaines",
    "monthly": "Mensuel",
    "bimonthly": "Tous les 2 mois",
    "quarterly": "Trimestriel",
    "irregular": "Irrégulier",
}

FREQUENCY_THRESHOLDS = "≤ 2 j : Quotidien · 3–10 j : Hebdomadaire · 11–17 j : Toutes les 2 semaines · 18–45 j : Mensuel · 46–90 j : Tous les 2 mois · 91–120 j : Trimestriel · > 120 j : Irrégulier"

LISTENING_LABELS = {
    "apple_podcast": "Apple Podcasts",
    "spotify": "Spotify",
    "youtube": "YouTube",
    "deezer": "Deezer",
    "pocket_casts": "Pocket Casts",
    "podcast_addict": "Podcast Addict",
    "amazon_music": "Amazon Music",
    "castbox": "Castbox",
}

PROMO_PATTERNS = (
    r"\bHébergé par\b[^.!?]*[.!?]?",
    r"\bHosted by\b[^.!?]*[.!?]?",
    r"\bVisitez\b[^.!?]*[.!?]?",
    r"\bVisit\b[^.!?]*[.!?]?",
    r"\bLearn more\b[^.!?]*[.!?]?",
    r"\bEn savoir plus\b[^.!?]*[.!?]?",
    r"\bDécouvrez notre site\b[^.!?]*[.!?]?",
)

DEFAULT_TOPIC = "Cybersécurité"
DEFAULT_LANGUAGE = "fr"
DEFAULT_STATUS = "active"
DEFAULT_SORT = "last"
EPISODE_LIMIT = 100

THEME_INIT = """<script>
(function () {
  try {
    var stored = localStorage.getItem('cyberpodcast-theme');
    var theme = stored === 'light' || stored === 'dark' ? stored : 'dark';
    document.documentElement.dataset.theme = theme;
  } catch (error) {}
})();
</script>"""


def esc(value: Any) -> str:
    return html_lib.escape("" if value is None else str(value), quote=True)


def text(value: Any, default: str = "—") -> str:
    if value is None or value == "" or value == []:
        return default
    return html_lib.escape(str(value))


def fmt_date(value: str | None) -> str:
    if not value:
        return "—"
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return html_lib.escape(str(value))


def fmt_number(value: int | float | None) -> str:
    if value is None:
        return "—"
    try:
        return f"{int(value):,}".replace(",", "\u202f")
    except (TypeError, ValueError):
        return html_lib.escape(str(value))


def fmt_duration(value: int | float | None) -> str:
    if value is None:
        return "—"
    try:
        return f"{int(round(float(value)))} min"
    except (TypeError, ValueError):
        return html_lib.escape(str(value))


def fmt_rating(value: int | float | None, count: int | None = None) -> str:
    if value is None or (count is not None and int(count or 0) < 5):
        return "—"
    try:
        rating = f"{float(value):.1f}/5"
        if count is not None:
            rating += f" ({int(count)})"
        return rating
    except (TypeError, ValueError):
        return html_lib.escape(str(value))


def has_rating(podcast: dict[str, Any]) -> bool:
    return (
        podcast.get("community_rating") is not None
        and int(podcast.get("community_rating_count") or 0) >= 5
    )


def clean_description(value: Any, limit: int = 240) -> str:
    text_value = re.sub(r"<[^>]+>", " ", "" if value is None else str(value))
    text_value = html_lib.unescape(text_value)
    text_value = re.sub(r"\s+", " ", text_value).strip()
    if not text_value:
        return ""
    for pattern in PROMO_PATTERNS:
        text_value = re.sub(pattern, " ", text_value, flags=re.IGNORECASE)
    text_value = re.sub(r"\s+", " ", text_value).strip(" ,;:-")
    if not text_value:
        return ""
    if len(text_value) <= limit:
        return text_value

    sentences = re.split(r"(?<=[.!?])\s+", text_value[: limit + 80])
    kept: list[str] = []
    for sentence in sentences:
        candidate = " ".join(kept + [sentence])
        if len(candidate) > limit and kept:
            break
        kept.append(sentence)
        if len(candidate) >= limit * 0.6 and sentence.endswith((".", "!", "?")):
            break
    cut = " ".join(kept)
    if len(cut) <= limit and len(cut) < len(text_value):
        return cut
    prefix = text_value[:limit]
    if " " in prefix:
        prefix = prefix.rsplit(" ", 1)[0]
    return prefix.rstrip(" ,;:-") + "…"


def podcast_taxonomy(podcast: dict[str, Any]) -> list[str]:
    values = [str(value) for value in (podcast.get("topics") or []) if value]
    values.extend(str(value) for value in (podcast.get("category") or []) if value)
    return dedupe_preserve(values)


def dedupe_preserve(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.casefold()
        if key not in seen:
            seen.add(key)
            result.append(value)
    return result


def hosting_platform(podcast: dict[str, Any]) -> str | None:
    value = podcast.get("hosting_platform") or podcast.get("platform")
    if not value or str(value).casefold() in {"autre", "other"}:
        return None
    if str(value) in set(LISTENING_LABELS.values()):
        return None
    return str(value)


def listening_platforms(podcast: dict[str, Any]) -> list[str]:
    configured = podcast.get("listening_platforms")
    if isinstance(configured, list) and configured:
        return [str(value) for value in configured if value]
    return [
        label
        for field, label in LISTENING_LABELS.items()
        if podcast.get(field)
    ]


def language_text(podcast: dict[str, Any]) -> str:
    language = podcast.get("language") or ""
    country = podcast.get("country") or ""
    label = LANGUAGE_LABELS.get(language, language.upper() if language else "—")
    if country:
        label = f"{label} · {country}"
    return label


def status_label(status: str | None) -> str:
    return STATUS_LABELS.get(status or "archived", status or "Inactif")


def frequency_text(podcast: dict[str, Any]) -> str:
    frequency = podcast.get("frequency")
    days = podcast.get("frequency_days")
    if frequency:
        label = FREQUENCY_LABELS.get(frequency, frequency)
        return f"{label} (~{days} j)" if days is not None else label
    return "—"


def initials(name: str) -> str:
    words = re.findall(r"[A-Za-zÀ-ÿ0-9]+", name or "")
    value = "".join(word[0] for word in words[:2]).upper()
    return value or "CP"


def canonical(path: str = "") -> str:
    return f"{BASE_URL}/{path.lstrip('/')}"


def url_for(path: str, root: str = "") -> str:
    return f"{root}{path.lstrip('/')}"


BLOCKED_SITE_HOSTS = {
    "anchor.fm",
    "facebook.com",
    "feed.ausha.co",
    "feeds.acast.com",
    "instagram.com",
    "linkedin.com",
    "music.youtube.com",
    "open.spotify.com",
    "podcast.ausha.co",
    "podcasters.spotify.com",
    "shows.acast.com",
    "smartlink.ausha.co",
    "smartlinks.audiomeans.fr",
    "tiktok.com",
    "twitter.com",
    "x.com",
    "youtube.com",
    "youtu.be",
}
BLOCKED_YOUTUBE_MARKERS = ("iframe_api", "spotifyforcreators")


def valid_http_url(url: Any) -> str | None:
    if not url:
        return None
    value = str(url).strip()
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return value


def official_website(url: Any) -> str | None:
    value = valid_http_url(url)
    if not value:
        return None
    parsed = urlparse(value)
    host = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.lower()
    if host in BLOCKED_SITE_HOSTS or host.startswith(("feed.", "feeds.")):
        return None
    if path.endswith((".atom", ".rss", ".xml")) or re.search(r"/(?:feed|rss)(?:/|$)", path):
        return None
    return value


def youtube_link(url: Any) -> str | None:
    value = valid_http_url(url)
    if not value:
        return None
    host = urlparse(value).netloc.lower().removeprefix("www.")
    if host not in {"youtube.com", "youtu.be"}:
        return None
    if any(marker in value.lower() for marker in BLOCKED_YOUTUBE_MARKERS):
        return None
    return value


def sanitize_podcast_links(podcasts: list[dict[str, Any]]) -> None:
    for podcast in podcasts:
        podcast["website"] = official_website(podcast.get("website"))
        podcast["youtube"] = youtube_link(podcast.get("youtube"))


def json_safe(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def youtube_embed(url: str | None) -> str | None:
    if not url:
        return None
    patterns = (
        r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/shorts/)([A-Za-z0-9_-]{6,})",
    )
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return f"https://www.youtube-nocookie.com/embed/{match.group(1)}"
    return None


def link_pill(label: str, url: str | None, css: str = "") -> str:
    if not url:
        return ""
    css_class = f" link-{css}" if css else ""
    return (
        f'<a class="link{css_class}" href="{esc(url)}" target="_blank" '
        f'rel="noopener noreferrer"><span class="dot"></span>{html_lib.escape(label)}</a>'
    )


def podcast_links(podcast: dict[str, Any]) -> str:
    links = [
        ("Site", podcast.get("website"), "site"),
        ("RSS", podcast.get("rss"), "rss"),
        ("Apple", podcast.get("apple_podcast"), "apple"),
        ("Spotify", podcast.get("spotify"), "spotify"),
        ("YouTube", podcast.get("youtube"), "youtube"),
        ("Deezer", podcast.get("deezer"), "deezer"),
        ("Pocket Casts", podcast.get("pocket_casts"), "pocketcasts"),
        ("Podcast Addict", podcast.get("podcast_addict"), "podcastaddict"),
        ("Amazon Music", podcast.get("amazon_music"), "amazon"),
        ("Castbox", podcast.get("castbox"), "castbox"),
        ("LinkedIn", podcast.get("linkedin"), "linkedin"),
    ]
    rendered = "".join(link_pill(label, url, css) for label, url, css in links if url)
    return rendered or '<span class="muted">Aucun lien vérifié.</span>'


def detail_platform_links(podcast: dict[str, Any]) -> str:
    links = [
        ("Apple Podcasts", podcast.get("apple_podcast"), "apple"),
        ("Spotify", podcast.get("spotify"), "spotify"),
        ("YouTube", podcast.get("youtube"), "youtube"),
        ("Deezer", podcast.get("deezer"), "deezer"),
        ("Pocket Casts", podcast.get("pocket_casts"), "pocketcasts"),
        ("Podcast Addict", podcast.get("podcast_addict"), "podcastaddict"),
        ("Amazon Music", podcast.get("amazon_music"), "amazon"),
        ("Castbox", podcast.get("castbox"), "castbox"),
        ("LinkedIn", podcast.get("linkedin"), "linkedin"),
    ]
    return "".join(
        f'<a class="button button-secondary link-{css}" href="{esc(url)}" target="_blank" '
        f'rel="noopener noreferrer"><span class="dot"></span>{html_lib.escape(label)}</a>'
        for label, url, css in links
        if url
    )


def cover_html(podcast: dict[str, Any], css: str = "cover", lazy: bool = True) -> str:
    name = podcast.get("name") or podcast.get("id") or "Podcast"
    image = podcast.get("image")
    if image:
        loading = ' loading="lazy"' if lazy else ""
        return (
            f'<div class="{css}"><img src="{esc(image)}" alt="Pochette de {esc(name)}"'
            f'{loading} decoding="async" referrerpolicy="no-referrer"></div>'
        )
    return (
        f'<div class="{css} cover-placeholder" aria-hidden="true">'
        f"<span>{esc(initials(name))}</span></div>"
    )


def topic_url(topic: str) -> str:
    return f"/?topic={quote(topic, safe='')}"


def topic_chips(podcast: dict[str, Any], limit: int = 6) -> str:
    topics = podcast_taxonomy(podcast)
    if not topics:
        return ""
    shown = topics[:limit]
    chips = "".join(
        f'<a class="chip" href="{esc(topic_url(topic))}">{html_lib.escape(topic)}</a>'
        for topic in shown
    )
    if len(topics) > len(shown):
        chips += f'<span class="chip chip-more" title="{esc(", ".join(topics))}">+{len(topics) - len(shown)}</span>'
    return f'<div class="chips">{chips}</div>'


def tag_html(podcast: dict[str, Any], limit: int = 10) -> str:
    tags = [str(tag) for tag in (podcast.get("tags") or []) if tag]
    if not tags:
        return ""
    shown = tags[:limit]
    rendered = "".join(f'<span class="tag">{html_lib.escape(tag)}</span>' for tag in shown)
    if len(tags) > len(shown):
        rendered += (
            f'<span class="tag more" title="{esc(", ".join(tags))}">'
            f"+{len(tags) - len(shown)}</span>"
        )
    return f'<div class="tags">{rendered}</div>'


def status_badge(podcast: dict[str, Any]) -> str:
    status = podcast.get("status") or "archived"
    return f'<span class="badge status-{esc(status)}">{esc(status_label(status))}</span>'


def favorite_button(podcast: dict[str, Any], label: str = "", css: str = "icon-btn favorite-btn") -> str:
    name = podcast.get("name") or podcast.get("id") or "ce podcast"
    content = f'<span class="heart">♡</span><span class="favorite-label">{esc(label)}</span>' if label else '<span class="heart">♡</span>'
    return (
        f'<button class="{css}" type="button" data-id="{esc(podcast.get("id"))}" '
        f'aria-pressed="false" aria-label="Ajouter {esc(name)} aux favoris" '
        f'title="Ajouter aux favoris">{content}</button>'
    )


def play_button(podcast: dict[str, Any]) -> str:
    audio = podcast.get("last_episode_audio")
    if not audio:
        return ""
    title = podcast.get("last_episode_title") or podcast.get("name") or "Épisode"
    name = podcast.get("name") or podcast.get("id") or "Podcast"
    return (
        f'<button class="icon-btn play-btn" type="button" data-audio="{esc(audio)}" '
        f'data-title="{esc(name)} — {esc(title)}" aria-label="Écouter le dernier épisode" '
        f'title="Écouter le dernier épisode">▶</button>'
    )


def search_text(podcast: dict[str, Any]) -> str:
    parts = [
        podcast.get("name"),
        podcast.get("author"),
        podcast.get("description"),
        " ".join(str(host) for host in (podcast.get("hosts") or [])),
        " ".join(str(category) for category in (podcast.get("category") or [])),
        " ".join(str(topic) for topic in (podcast.get("topics") or [])),
        " ".join(str(tag) for tag in (podcast.get("tags") or [])),
        podcast.get("platform"),
        podcast.get("language"),
        podcast.get("country"),
        podcast.get("last_episode_title"),
    ]
    return " ".join(str(part) for part in parts if part)


def podcast_card(podcast: dict[str, Any], root: str = "") -> str:
    entry_id = str(podcast.get("id") or "")
    name = podcast.get("name") or entry_id or "Sans nom"
    detail_url = f"{root}podcast/{esc(entry_id)}.html"
    website = podcast.get("website")
    title = (
        f'<a href="{detail_url}">{html_lib.escape(name)}</a>'
    )
    if website:
        title += (
            f' <a class="external-mark" href="{esc(website)}" target="_blank" '
            f'rel="noopener noreferrer" title="Ouvrir le site officiel" aria-label="Site officiel">↗</a>'
        )

    hosts = [str(value) for value in (podcast.get("hosts") or []) if value]
    hosts_text = ", ".join(hosts) or podcast.get("author") or "—"
    last_episode = podcast.get("last_episode")
    last_episode_title = podcast.get("last_episode_title")
    rating = podcast.get("community_rating")
    rating_count = podcast.get("community_rating_count")
    host = hosting_platform(podcast) or "autre"
    listens = listening_platforms(podcast)

    meta_items = [
        ("Animateurs", hosts_text, False),
        ("Langue", language_text(podcast), False),
        ("Hébergeur", host if host != "autre" else "Autre", False),
        ("Écoute", ", ".join(listens) if listens else "—", False),
        ("Dernier épisode", fmt_date(last_episode), True),
        ("Rythme", frequency_text(podcast), False),
        ("Épisodes", fmt_number(podcast.get("episode_count")), False),
        ("Durée moyenne", fmt_duration(podcast.get("average_duration")), False),
    ]
    if has_rating(podcast):
        meta_items.append(("Note Apple", fmt_rating(rating, rating_count), False))

    def card_meta_item(label: str, value: Any, strong: bool) -> str:
        rendered = html_lib.escape(str(value))
        if strong:
            rendered = f"<strong>{rendered}</strong>"
        return f'<div><dt>{html_lib.escape(label)}</dt><dd title="{esc(value)}">{rendered}</dd></div>'

    meta_html = "".join(card_meta_item(*item) for item in meta_items)

    description = clean_description(podcast.get("description"), 220)
    description_html = (
        f'<p class="description">{html_lib.escape(description)}</p>'
        if description
        else '<p class="description muted">Pas de description.</p>'
    )

    taxonomy = podcast_taxonomy(podcast)
    topics_text = "|".join(taxonomy)
    listens_text = "|".join(listens)
    audio = podcast.get("last_episode_audio") or ""

    return f'''
<article class="card" data-id="{esc(entry_id)}" data-name="{esc(name)}" data-search="{esc(search_text(podcast))}" data-topics="{esc(topics_text)}" data-status="{esc(podcast.get("status") or "archived")}" data-language="{esc(podcast.get("language") or "")}" data-host="{esc(host)}" data-listen="{esc(listens_text)}" data-last="{esc(last_episode or "")}" data-episodes="{esc(podcast.get("episode_count") or 0)}" data-rating="{esc(rating if has_rating(podcast) else 0)}" data-duration="{esc(podcast.get("average_duration") or 0)}" data-first-seen="{esc(podcast.get("first_seen") or "")}" data-audio="{esc(audio)}" data-title="{esc(name + (" — " + last_episode_title if last_episode_title else ""))}">
  <div class="card-cover">{cover_html(podcast, "cover")}</div>
  <div class="card-body">
    <div class="card-head">
      <div class="card-heading">
        <h2 class="card-title">{title}</h2>
      </div>
      {status_badge(podcast)}
    </div>
    {description_html}
    <dl class="meta">{meta_html}</dl>
    {topic_chips(podcast, 5)}
    <div class="card-actions">
      {play_button(podcast)}
      {favorite_button(podcast)}
      <a class="button button-small" href="{detail_url}">Détails</a>
      {link_pill("Site", website, "site")}
      {link_pill("Apple", podcast.get("apple_podcast"), "apple")}
      {link_pill("Podcast Addict", podcast.get("podcast_addict"), "podcastaddict")}
      {link_pill("Spotify", podcast.get("spotify"), "spotify")}
      {link_pill("YouTube", podcast.get("youtube"), "youtube")}
    </div>
  </div>
</article>'''


def build_options(
    values: list[str],
    labels: dict[str, str] | None = None,
    counts: Counter[str] | None = None,
    empty_label: str = "Tous",
    selected: str | None = None,
) -> str:
    labels = labels or {}
    counts = counts or Counter()

    def selected_attr(value: str) -> str:
        return " selected" if selected is not None and value == selected else ""

    options = [
        f'<option value=""{selected_attr("")}>{html_lib.escape(empty_label)}</option>'
    ]
    for value in values:
        label = labels.get(value, value)
        count = counts.get(value)
        suffix = f" ({count})" if count is not None else ""
        options.append(
            f'<option value="{esc(value)}"{selected_attr(value)}>'
            f"{html_lib.escape(label)}{suffix}</option>"
        )
    return "".join(options)


def layout(
    *,
    title: str,
    description: str,
    body: str,
    root: str = "",
    canonical_path: str = "",
    image: str | None = None,
    page_type: str = "website",
    extra_head: str = "",
    body_class: str = "",
    json_ld: dict[str, Any] | None = None,
) -> str:
    page_url = canonical(canonical_path) if canonical_path else BASE_URL + "/"
    image_url = image or f"{BASE_URL}/assets/logo.png"
    structured = ""
    if json_ld:
        structured = f'<script type="application/ld+json">{json_safe(json_ld)}</script>'
    return f'''<!doctype html>
<html lang="fr" data-theme="dark">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(title)}</title>
  <meta name="description" content="{esc(description)}">
  <link rel="canonical" href="{esc(page_url)}">
  <meta name="theme-color" content="#080d1c">
  <meta property="og:site_name" content="CyberPodcast">
  <meta property="og:type" content="{esc(page_type)}">
  <meta property="og:title" content="{esc(title)}">
  <meta property="og:description" content="{esc(description)}">
  <meta property="og:url" content="{esc(page_url)}">
  <meta property="og:image" content="{esc(image_url)}">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{esc(title)}">
  <meta name="twitter:description" content="{esc(description)}">
  <meta name="twitter:image" content="{esc(image_url)}">
  <link rel="icon" href="{root}favicon.ico" sizes="any">
  <link rel="icon" type="image/png" sizes="32x32" href="{root}assets/favicon-32x32.png">
  <link rel="apple-touch-icon" href="{root}assets/apple-touch-icon.png">
  <link rel="manifest" href="{root}manifest.webmanifest">
  <link rel="alternate" type="application/rss+xml" title="CyberPodcast · Derniers épisodes" href="{root}feed.xml">
  <link rel="stylesheet" href="{root}assets/style.css">
  {THEME_INIT}
  <script src="{root}assets/app.js" defer></script>
  {extra_head}
  {structured}
</head>
<body class="{esc(body_class)}">
  <a class="skip-link" href="#contenu">Aller au contenu</a>
  <header class="site-header">
    <div class="site-header-inner">
      <a class="brand" href="/" aria-label="CyberPodcast, accueil">
        <img class="brand-logo" src="{root}assets/logo.png" alt="CyberPodcast" width="512" height="436">
      </a>
      <nav class="nav-links" aria-label="Navigation principale">
        <a class="nav-link" href="/">Podcasts</a>
        <a class="nav-link" href="{root}episodes.html">Épisodes</a>
        <a class="nav-link" href="{root}sujets.html">Sujets</a>
        <a class="nav-link" href="{root}statistiques.html">Statistiques</a>
        <a class="nav-link" href="{root}a-propos.html">À propos</a>
        <a class="nav-link nav-cta" href="{root}contribuer.html">Proposer un podcast</a>
        <a class="nav-link nav-external" href="{REPO_URL}" target="_blank" rel="noopener noreferrer">GitHub ↗</a>
        <button class="theme-toggle" id="theme-toggle" type="button" aria-pressed="false" aria-label="Activer le thème clair" title="Activer le thème clair">Clair</button>
      </nav>
    </div>
  </header>
  {body}
  <footer class="footer">
    <span>Données enrichies automatiquement · dernière mise à jour {GENERATED_AT.strftime("%d/%m/%Y")} · <a href="{root}a-propos.html">méthode</a></span>
    <span><a href="{REPO_URL}" target="_blank" rel="noopener noreferrer">Code source</a> · <a href="{root}feed.xml">RSS</a> · <a href="{root}api/podcasts.json">API JSON</a></span>
  </footer>
  <script data-goatcounter="https://zebux.goatcounter.com/count"
          async src="//gc.zgo.at/count.js"></script>
</body>
</html>'''


def build_stats(podcasts: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(podcast.get("status") or "archived" for podcast in podcasts)
    language_counts = Counter(podcast.get("language") or "??" for podcast in podcasts)
    host_counts = Counter(
        host for host in (hosting_platform(podcast) for podcast in podcasts) if host
    )
    listen_counts = Counter(
        value for podcast in podcasts for value in listening_platforms(podcast)
    )
    topic_counts = Counter(
        topic
        for podcast in podcasts
        for topic in podcast_taxonomy(podcast)
    )
    ratings = [
        float(podcast["community_rating"])
        for podcast in podcasts
        if has_rating(podcast)
    ]
    return {
        "generated_at": GENERATED_AT.isoformat(),
        "total": len(podcasts),
        "total_episodes": sum(int(podcast.get("episode_count") or 0) for podcast in podcasts),
        "with_rss": sum(1 for podcast in podcasts if podcast.get("rss")),
        "with_image": sum(1 for podcast in podcasts if podcast.get("image")),
        "with_audio": sum(1 for podcast in podcasts if podcast.get("last_episode_audio")),
        "rated": len(ratings),
        "average_rating": round(statistics.mean(ratings), 2) if ratings else None,
        "by_status": dict(status_counts),
        "by_language": dict(language_counts),
        "by_host": dict(host_counts),
        "by_listening_platform": dict(listen_counts),
        "by_taxonomy": dict(topic_counts),
        "by_topic": dict(topic_counts),
        "latest_episode": max(
            (podcast.get("last_episode") for podcast in podcasts if podcast.get("last_episode")),
            default=None,
        ),
    }


def latest_episode_date(podcasts: list[dict[str, Any]]) -> str:
    return max(
        (podcast.get("last_episode") for podcast in podcasts if podcast.get("last_episode")),
        default="",
    )


def taxonomy_options(podcasts: list[dict[str, Any]], selected: str | None = None) -> str:
    counts = Counter(
        topic
        for podcast in podcasts
        for topic in podcast_taxonomy(podcast)
    )
    values = sorted(counts, key=str.casefold)
    return build_options(
        values,
        counts=counts,
        empty_label="Sujets / catégories",
        selected=selected,
    )


def index_page(podcasts: list[dict[str, Any]], stats: dict[str, Any]) -> str:
    languages = sorted(
        {podcast.get("language") for podcast in podcasts if podcast.get("language")},
        key=str.casefold,
    )
    language_counts = Counter(
        podcast.get("language") for podcast in podcasts if podcast.get("language")
    )

    cards = "\n".join(podcast_card(podcast) for podcast in podcasts)
    taxonomy_select = taxonomy_options(podcasts, selected=DEFAULT_TOPIC)
    status_options = build_options(
        ["active", "slow", "archived"],
        labels=STATUS_LABELS,
        counts=Counter(podcast.get("status") or "archived" for podcast in podcasts),
        empty_label="Tous les statuts",
        selected=DEFAULT_STATUS,
    )
    language_options = build_options(
        languages,
        labels=LANGUAGE_LABELS,
        counts=language_counts,
        empty_label="Toutes les langues",
        selected=DEFAULT_LANGUAGE,
    )
    config = {
        "defaults": {
            "language": DEFAULT_LANGUAGE,
            "status": DEFAULT_STATUS,
            "topic": DEFAULT_TOPIC,
            "sort": DEFAULT_SORT,
        },
        "total": len(podcasts),
    }
    updated = latest_episode_date(podcasts)

    body = f'''
  <main id="contenu">
    <section class="hero">
      <p class="eyebrow">{esc(fmt_date(updated))}</p>
      <h1>Les podcasts <span class="gradient">cyber, cloud &amp; dev</span></h1>
      <p class="lead">Découvrez et écoutez les meilleurs francophones (et parfois internationaux) sur la cybersécurité, le cloud et le développement.</p>
    </section>

    <section class="toolbar" aria-label="Filtres">
      <div class="toolbar-inner">
        <label class="search">
          <span class="sr-only">Rechercher</span>
          <input id="search" type="search" placeholder="Rechercher un podcast, un sujet, un animateur…" autocomplete="off">
        </label>
        <button class="filters-toggle" id="filters-toggle" type="button" aria-expanded="false" aria-controls="filters-panel">Filtres</button>
        <div class="filters-panel" id="filters-panel">
          <select id="filter-topic" aria-label="Filtrer par sujets ou catégories">{taxonomy_select}</select>
          <select id="filter-status" aria-label="Filtrer par statut">{status_options}</select>
          <select id="filter-language" aria-label="Filtrer par langue">{language_options}</select>
          <select id="sort" aria-label="Trier">
            <option value="name">Nom (A–Z)</option>
            <option value="last" selected>Dernier épisode</option>
            <option value="episodes">Nombre d’épisodes</option>
            <option value="rating">Note Apple</option>
            <option value="duration">Durée moyenne</option>
            <option value="recent">Ajout récent</option>
            <option value="status">Statut</option>
          </select>
          <button id="reset" type="button">Réinitialiser</button>
        </div>
      </div>
    </section>

    <div class="results" aria-live="polite"><span id="count">{len(podcasts)} podcasts</span> · <span id="active-filters">filtres par défaut</span></div>
    <section class="grid" id="podcast-grid">
{cards}
    </section>
    <div class="empty" id="empty" hidden>Aucun podcast ne correspond à ces filtres. <button class="button button-small" id="empty-reset" type="button">Réinitialiser</button></div>

    <div class="player-bar" id="player-bar" hidden>
      <div class="player-info">
        <span class="player-label">Lecture en cours</span>
        <strong id="player-title"></strong>
      </div>
      <audio id="player-audio" controls preload="none"></audio>
      <button class="icon-btn" id="player-close" type="button" aria-label="Fermer le lecteur" title="Fermer">✕</button>
    </div>
  </main>
  <script>window.CYBERPODCAST_CONFIG = {json_safe(config)};</script>'''

    return layout(
        title="CyberPodcast · Podcasts cyber, cloud & dev",
        description="Annuaire de podcasts cybersécurité, cloud et développement : recherche, filtres par sujet, favoris et lecteur intégré.",
        body=body,
        canonical_path="",
        json_ld={
            "@context": "https://schema.org",
            "@type": "WebSite",
            "name": "CyberPodcast",
            "url": BASE_URL + "/",
            "description": "Annuaire de podcasts cybersécurité, cloud et développement.",
            "potentialAction": {
                "@type": "SearchAction",
                "target": f"{BASE_URL}/?q={{search_term_string}}",
                "query-input": "required name=search_term_string",
            },
        },
    )


def meta_items(podcast: dict[str, Any]) -> list[tuple[str, str]]:
    hosts = ", ".join(str(host) for host in (podcast.get("hosts") or []) if host)
    host = hosting_platform(podcast)
    listens = listening_platforms(podcast)
    items = [
        ("Animateurs", hosts or podcast.get("author") or "—"),
        ("Auteur", podcast.get("author") or "—"),
        ("Langue", language_text(podcast)),
        ("Dernier épisode", fmt_date(podcast.get("last_episode"))),
        ("Rythme", frequency_text(podcast)),
        ("Épisodes", fmt_number(podcast.get("episode_count"))),
        ("Durée moyenne", fmt_duration(podcast.get("average_duration"))),
        ("Hébergeur", host or "Autre"),
        ("Plateformes d’écoute", ", ".join(listens) if listens else "—"),
        ("Pays", podcast.get("country") or "—"),
        ("Ajouté le", fmt_date(podcast.get("first_seen"))),
        ("Mis à jour le", fmt_date(podcast.get("updated_at"))),
    ]
    if has_rating(podcast):
        items.insert(7, ("Note Apple", fmt_rating(podcast.get("community_rating"), podcast.get("community_rating_count"))))
    return items


def episode_html(episode: dict[str, Any], index: int) -> str:
    title = episode.get("title") or "Épisode sans titre"
    published = episode.get("published")
    url = episode.get("url")
    audio = episode.get("audio")
    duration = episode.get("duration")
    title_html = (
        f'<a href="{esc(url)}" target="_blank" rel="noopener noreferrer">{html_lib.escape(title)}</a>'
        if url
        else html_lib.escape(title)
    )
    audio_html = (
        f'<audio class="episode-audio" controls preload="none" src="{esc(audio)}"></audio>'
        if audio
        else ""
    )
    return f'''
      <li class="episode">
        <div class="episode-head">
          <div>
            <span class="episode-date">{esc(fmt_date(published))}</span>
            <h3>{title_html}</h3>
          </div>
          <span class="episode-duration">{esc(fmt_duration(duration))}</span>
        </div>
        {audio_html}
      </li>'''


def recent_episodes(podcasts: list[dict[str, Any]], limit: int = 20) -> list[tuple[str, dict[str, Any], dict[str, Any]]]:
    rows: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    for podcast in podcasts:
        for episode in podcast.get("episodes") or []:
            if not isinstance(episode, dict):
                continue
            published = str(episode.get("published") or "")
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", published):
                continue
            rows.append((published, podcast, episode))
    rows.sort(
        key=lambda item: (
            item[0],
            str(item[1].get("name") or "").casefold(),
            str(item[2].get("title") or "").casefold(),
        ),
        reverse=True,
    )
    return rows[:limit]


def latest_episodes_page(podcasts: list[dict[str, Any]]) -> str:
    rows = recent_episodes(podcasts, EPISODE_LIMIT)
    topic_counts: Counter[str] = Counter()
    language_counts: Counter[str] = Counter()
    for _, podcast, _ in rows:
        topic_counts.update(podcast_taxonomy(podcast))
        language_counts.update([podcast.get("language") or "??"])
    topic_options = build_options(
        sorted(topic_counts, key=str.casefold),
        counts=topic_counts,
        empty_label="Tous les sujets",
        selected=DEFAULT_TOPIC,
    )
    language_options = build_options(
        sorted(language_counts, key=str.casefold),
        labels=LANGUAGE_LABELS,
        counts=language_counts,
        empty_label="Toutes les langues",
        selected=DEFAULT_LANGUAGE,
    )
    items = []
    default_count = 0
    for index, (published, podcast, episode) in enumerate(rows, 1):
        entry_id = str(podcast.get("id") or "")
        podcast_url = f"podcast/{esc(entry_id)}.html"
        title = str(episode.get("title") or "Épisode sans titre")
        episode_url = episode.get("url")
        title_html = (
            f'<a href="{esc(episode_url)}" target="_blank" rel="noopener noreferrer">{html_lib.escape(title)}</a>'
            if episode_url
            else html_lib.escape(title)
        )
        audio = episode.get("audio")
        audio_html = (
            f'<audio class="episode-audio" controls preload="none" src="{esc(audio)}"></audio>'
            if audio
            else ""
        )
        taxonomy = podcast_taxonomy(podcast)
        language = podcast.get("language") or ""
        default_visible = DEFAULT_TOPIC in taxonomy and language == DEFAULT_LANGUAGE
        if default_visible:
            default_count += 1
        hidden_attr = "" if default_visible else " hidden"
        topics = topic_chips(podcast, 3)
        items.append(f'''
      <li class="episode episode-feed-item"{hidden_attr} data-topics="{esc("|".join(taxonomy))}" data-language="{esc(language)}">
        <span class="episode-rank">{index:02d}</span>
        <a class="episode-cover" href="{podcast_url}">{cover_html(podcast, "mini-cover")}</a>
        <div class="episode-feed-body">
          <span class="episode-date">{esc(fmt_date(published))}</span>
          <h3>{title_html}</h3>
          <a class="episode-podcast" href="{podcast_url}">{html_lib.escape(podcast.get("name") or entry_id)}</a>
          {topics}
          {audio_html}
        </div>
        <span class="episode-duration">{esc(fmt_duration(episode.get("duration")))}</span>
      </li>''')
    episodes_html = "".join(items) or '<li class="muted">Aucun épisode publié pour le moment.</li>'
    newest = rows[0][0] if rows else ""
    body = f'''
  <main class="page" id="contenu">
    <header class="page-header">
      <p class="eyebrow">{esc(fmt_date(newest))}</p>
      <h1>Les {EPISODE_LIMIT} derniers <span class="gradient">épisodes publiés</span></h1>
      <p class="lead">Une sélection chronologique des épisodes les plus récents publiés dans les flux RSS référencés, tous podcasts confondus.</p>
    </header>
    <div class="episode-filters" aria-label="Filtres des épisodes">
      <select id="episode-topic" aria-label="Filtrer les épisodes par sujet ou catégorie">{topic_options}</select>
      <select id="episode-language" aria-label="Filtrer les épisodes par langue">{language_options}</select>
    </div>
    <section class="panel">
      <div class="panel-head"><h2>À écouter maintenant</h2><span class="muted" id="episode-count">{default_count} épisode{'s' if default_count != 1 else ''}</span></div>
      <ol class="episode-list episode-feed" id="episode-list">{episodes_html}</ol>
    </section>
  </main>
  <script>window.CYBERPODCAST_EPISODES_CONFIG = {json_safe({"defaults": {"topic": DEFAULT_TOPIC, "language": DEFAULT_LANGUAGE}})};</script>'''
    return layout(
        title="Derniers épisodes · CyberPodcast",
        description=f"Les {EPISODE_LIMIT} derniers épisodes publiés par les podcasts cyber, cloud et développement référencés sur CyberPodcast.",
        body=body,
        canonical_path="episodes.html",
        json_ld={
            "@context": "https://schema.org",
            "@type": "CollectionPage",
            "name": "Derniers épisodes · CyberPodcast",
            "url": canonical("episodes.html"),
        },
    )


def related_podcasts(podcast: dict[str, Any], podcasts: list[dict[str, Any]], limit: int = 4) -> list[dict[str, Any]]:
    topics = {str(topic) for topic in (podcast.get("topics") or []) if topic}
    categories = {str(category) for category in (podcast.get("category") or []) if category}
    scored: list[tuple[int, int, str, dict[str, Any]]] = []
    for other in podcasts:
        if other.get("id") == podcast.get("id"):
            continue
        other_topics = {str(topic) for topic in (other.get("topics") or []) if topic}
        other_categories = {str(category) for category in (other.get("category") or []) if category}
        score = len(topics & other_topics) * 2 + len(categories & other_categories)
        if score <= 0:
            continue
        scored.append(
            (
                score,
                STATUS_ORDER.get(other.get("status") or "archived", 9),
                str(other.get("name") or "").casefold(),
                other,
            )
        )
    scored.sort(key=lambda item: (-item[0], item[1], item[2]))
    return [item[3] for item in scored[:limit]]


def mini_card(podcast: dict[str, Any], root: str = "../") -> str:
    return f'''
    <a class="mini-card" href="{root}podcast/{esc(podcast.get("id"))}.html">
      {cover_html(podcast, "mini-cover")}
      <span class="mini-body">
        <strong>{esc(podcast.get("name") or "Podcast")}</strong>
        <small>{esc(status_label(podcast.get("status")))} · {esc(language_text(podcast))}</small>
      </span>
    </a>'''


def detail_page(podcast: dict[str, Any], podcasts: list[dict[str, Any]]) -> str:
    entry_id = str(podcast.get("id"))
    name = podcast.get("name") or entry_id
    root = "../"
    description = clean_description(podcast.get("description"), 800) or f"Fiche du podcast {name} sur CyberPodcast."
    episodes = [episode for episode in (podcast.get("episodes") or []) if isinstance(episode, dict)]
    last_audio = podcast.get("last_episode_audio") or (episodes[0].get("audio") if episodes else None)
    last_title = podcast.get("last_episode_title") or (episodes[0].get("title") if episodes else None)
    last_url = podcast.get("last_episode_url") or (episodes[0].get("url") if episodes else None)
    embed = youtube_embed(podcast.get("youtube")) or youtube_embed(last_url)

    if last_audio:
        player = f'''
        <div class="player-card">
          <p class="player-title">{esc(last_title or "Dernier épisode")}</p>
          <audio id="main-player" controls preload="metadata" src="{esc(last_audio)}"></audio>
          {f'<a class="link" href="{esc(last_url)}" target="_blank" rel="noopener noreferrer"><span class="dot"></span>Voir l’épisode</a>' if last_url else ''}
        </div>'''
    elif embed:
        player = f'''
        <div class="video-card">
          <iframe src="{esc(embed)}" title="Vidéo de {esc(name)}" loading="lazy" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>
        </div>'''
    else:
        player = '<p class="muted">Aucun audio directement disponible. Utilisez les liens d’écoute ci-contre.</p>'

    episodes_html = "".join(episode_html(episode, index) for index, episode in enumerate(episodes))
    if not episodes_html:
        episodes_html = '<li class="muted">Aucun épisode récent détecté dans le flux.</li>'

    latest_html = ""
    if not episodes:
        latest_html = f'''
        <div class="panel-head"><h2>Dernier épisode</h2>{f'<span class="muted">{esc(fmt_date(podcast.get("last_episode")))}</span>' if podcast.get("last_episode") else ''}</div>
        {player}'''

    meta_html = "".join(
        f'<div><dt>{html_lib.escape(label)}</dt><dd>{html_lib.escape(value)}</dd></div>'
        for label, value in meta_items(podcast)
    )
    related = related_podcasts(podcast, podcasts)
    related_html = "".join(mini_card(other, root) for other in related) or '<p class="muted">Aucun podcast proche pour le moment.</p>'
    tags = tag_html(podcast, 20)
    topics = topic_chips(podcast, 20)

    body = f'''
  <main class="detail" id="contenu">
    <nav class="breadcrumb" aria-label="Fil d’Ariane">
      <a href="/">Podcasts</a><span>/</span><span>{esc(name)}</span>
    </nav>
    <section class="detail-hero">
      {cover_html(podcast, "cover cover-lg", lazy=False)}
      <div class="detail-intro">
        <div class="detail-badges">{status_badge(podcast)}<span class="badge badge-soft">{esc(frequency_text(podcast))}</span></div>
        <h1>{esc(name)}</h1>
        <p class="detail-hosts">{esc(", ".join(str(host) for host in (podcast.get("hosts") or []) if host) or podcast.get("author") or "Animateur non renseigné")}</p>
        <p class="lead">{esc(description)}</p>
        {topics}
        <div class="detail-actions">
          {favorite_button(podcast, "Ajouter aux favoris", "button favorite-btn")}
          {f'<a class="button button-secondary" href="{esc(podcast.get("rss"))}" target="_blank" rel="noopener noreferrer">Flux RSS</a>' if podcast.get("rss") else ''}
          {f'<a class="button button-secondary" href="{esc(podcast.get("website"))}" target="_blank" rel="noopener noreferrer">Site officiel ↗</a>' if podcast.get("website") else ''}
          {detail_platform_links(podcast)}
        </div>
      </div>
    </section>

    <div class="detail-grid">
      <section class="panel">
        {latest_html}
        <h2>Épisodes récents</h2>
        <ol class="episode-list">{episodes_html}</ol>
      </section>
      <aside class="panel">
        <h2>Informations</h2>
        <dl class="meta meta-large">{meta_html}</dl>
        <h2>Liens d’écoute</h2>
        <div class="links">{podcast_links(podcast)}</div>
        {f'<h2>Sujets</h2>{topics}' if topics else ''}
        {f'<h2>Tags</h2>{tags}' if tags else ''}
      </aside>
    </div>

    <section class="related">
      <h2>À découvrir aussi</h2>
      <div class="related-grid">{related_html}</div>
    </section>
  </main>'''

    json_ld = {
        "@context": "https://schema.org",
        "@type": "PodcastSeries",
        "name": name,
        "url": canonical(f"podcast/{entry_id}.html"),
        "description": description,
        "image": podcast.get("image") or f"{BASE_URL}/assets/icon-512.png",
        "webFeed": podcast.get("rss"),
        "inLanguage": podcast.get("language") or "fr",
        "author": [
            {"@type": "Person", "name": str(host)}
            for host in (podcast.get("hosts") or [])
            if host
        ],
        "sameAs": [
            url
            for url in (
                podcast.get("website"),
                podcast.get("apple_podcast"),
                podcast.get("spotify"),
                podcast.get("youtube"),
                podcast.get("deezer"),
            )
            if url
        ],
    }
    json_ld = {key: value for key, value in json_ld.items() if value not in (None, "", [])}
    return layout(
        title=f"{name} · CyberPodcast",
        description=description,
        body=body,
        root=root,
        canonical_path=f"podcast/{entry_id}.html",
        image=podcast.get("image"),
        page_type="article",
        json_ld=json_ld,
    )


def bar_list(counter: Counter[str], total: int, label_func: Any = None, limit: int | None = None) -> str:
    if not counter or total <= 0:
        return '<p class="muted">Aucune donnée.</p>'
    label_func = label_func or (lambda value: value)
    items = sorted(counter.items(), key=lambda item: (-item[1], str(item[0]).casefold()))
    if limit:
        items = items[:limit]
    rows = []
    for value, count in items:
        percent = max(1.0, min(100.0, count * 100 / total))
        rows.append(
            f'<div class="bar-row"><span class="bar-label">{html_lib.escape(str(label_func(value)))}</span>'
            f'<span class="bar-track"><span class="bar-fill" style="width:{percent:.1f}%"></span></span>'
            f'<span class="bar-count">{count}</span></div>'
        )
    return "".join(rows)


def topics_page(podcasts: list[dict[str, Any]]) -> str:
    topic_map: dict[str, list[dict[str, Any]]] = {}
    for podcast in podcasts:
        for topic in podcast_taxonomy(podcast):
            topic_map.setdefault(topic, []).append(podcast)
    cards = []
    for topic, items in sorted(topic_map.items(), key=lambda item: (-len(item[1]), item[0].casefold())):
        top = sorted(
            items,
            key=lambda podcast: (
                STATUS_ORDER.get(podcast.get("status") or "archived", 9),
                str(podcast.get("name") or "").casefold(),
            ),
        )[:4]
        names = " · ".join(html_lib.escape(str(podcast.get("name"))) for podcast in top)
        cards.append(
            f'''
      <a class="topic-card" href="{esc(topic_url(topic))}">
        <span class="topic-count">{len(items)} podcast{"s" if len(items) > 1 else ""}</span>
        <h2>{html_lib.escape(topic)}</h2>
        <p>{names}</p>
        <span class="topic-arrow">Explorer →</span>
      </a>'''
        )
    body = f'''
  <main class="page" id="contenu">
    <header class="page-header">
      <p class="eyebrow">Explorer</p>
      <h1>Tous les <span class="gradient">sujets</span></h1>
      <p class="lead">Parcourez les podcasts par thématique : cyber, cloud, développement, gouvernance, incidents, IA et plus encore.</p>
    </header>
    <div class="topic-grid">{"".join(cards)}</div>
  </main>'''
    return layout(
        title="Sujets · CyberPodcast",
        description="Explorer les podcasts cybersécurité, cloud et développement par sujet.",
        body=body,
        canonical_path="sujets.html",
    )


def stats_page(podcasts: list[dict[str, Any]], stats: dict[str, Any]) -> str:
    status_counts = Counter(stats["by_status"])
    language_counts = Counter(stats["by_language"])
    host_counts = Counter(stats["by_host"])
    listen_counts = Counter(stats["by_listening_platform"])
    topic_counts = Counter(stats["by_taxonomy"])
    total = stats["total"]
    rating = stats["average_rating"]
    rating_text = f"{rating:.2f}/5" if rating is not None else "—"
    body = f'''
  <main class="page" id="contenu">
    <header class="page-header">
      <p class="eyebrow">Chiffres clés</p>
      <h1>Le catalogue en <span class="gradient">un coup d’œil</span></h1>
      <p class="lead">Des statistiques générées automatiquement à partir de la base enrichie, sans suivi ni cookie.</p>
    </header>
    <section class="stats-grid">
      <div class="stat-card"><strong>{stats["total"]}</strong><span>podcasts</span></div>
      <div class="stat-card"><strong>{fmt_number(stats["total_episodes"])}</strong><span>épisodes référencés</span></div>
      <div class="stat-card"><strong>{stats["by_status"].get("active", 0)}</strong><span>podcasts actifs</span></div>
      <div class="stat-card"><strong>{stats["with_audio"]}</strong><span>écoutes directes</span></div>
      <div class="stat-card"><strong>{rating_text}</strong><span>note Apple moyenne</span></div>
      <div class="stat-card"><strong>{stats["with_image"]}</strong><span>pochettes disponibles</span></div>
    </section>
    <div class="charts-grid">
      <section class="panel"><h2>Statuts</h2>{bar_list(status_counts, total, lambda value: status_label(value))}</section>
      <section class="panel"><h2>Langues</h2>{bar_list(language_counts, total, lambda value: LANGUAGE_LABELS.get(value, str(value).upper()))}</section>
      <section class="panel"><h2>Hébergeurs</h2>{bar_list(host_counts, total, limit=14)}</section>
      <section class="panel"><h2>Plateformes d’écoute</h2>{bar_list(listen_counts, total, limit=14)}</section>
      <section class="panel panel-wide"><h2>Taxonomie la plus représentée</h2>{bar_list(topic_counts, total, limit=24)}</section>
    </div>
  </main>'''
    return layout(
        title="Statistiques · CyberPodcast",
        description="Statistiques du catalogue CyberPodcast : podcasts, épisodes, langues, plateformes et sujets.",
        body=body,
        canonical_path="statistiques.html",
    )


def about_page(podcasts: list[dict[str, Any]], stats: dict[str, Any]) -> str:
    body = f'''
  <main class="page prose" id="contenu">
    <header class="page-header">
      <p class="eyebrow">Le projet</p>
      <h1>Un annuaire <span class="gradient">vivant</span> des podcasts cyber</h1>
      <p class="lead">CyberPodcast référence {stats["total"]} podcasts francophones et internationaux autour de la cybersécurité, du cloud et du développement.</p>
    </header>
    <section class="panel">
      <h2>Ce que fait le projet</h2>
      <p>Le site agrège des podcasts, vérifie leurs liens, récupère leurs derniers épisodes et enrichit les fiches depuis les flux RSS, Apple Podcasts et les sites officiels. Tout est généré statiquement : aucun serveur, aucun compte, aucun cookie.</p>
      <h2>Comment les données sont produites</h2>
      <ol>
        <li>Les sources et les corrections manuelles vérifiées sont dans <code>data/podcasts-*.yaml</code>.</li>
        <li>Le pipeline Python fusionne, déduplique, enrichit et écrit <code>podcasts.yaml</code>.</li>
        <li>Un workflow GitHub Actions contrôle la santé des liens, régénère le site et publie GitHub Pages.</li>
      </ol>
      <h2>Rythmes de publication</h2>
      <p>Le rythme est calculé à partir de l’intervalle médian entre les dates de publication des épisodes récents, puis arrondi au nombre de jours entier le plus proche. Seuils utilisés : {FREQUENCY_THRESHOLDS}. Le nombre affiché entre parenthèses est cet intervalle médian, pas une périodicité contractuelle.</p>
      <h2>Automatisation</h2>
      <p>Le workflow tourne chaque jour. Il récupère les nouveautés, met à jour les notes et les derniers épisodes, contrôle la santé des liens et redéploie le site. Les erreurs réseau ne bloquent pas la publication : les données précédentes servent de repli.</p>
      <h2>Contribuer</h2>
      <p>Une erreur, un podcast manquant, un flux cassé ? Ouvrez une <a href="{REPO_URL}/issues" target="_blank" rel="noopener noreferrer">issue</a> ou proposez une correction dans <code>data/podcasts-*.yaml</code>. Les liens officiels et les flux vérifiés sont prioritaires.</p>
      <h2>Transparence</h2>
      <p>Les notes affichées proviennent d’Apple Podcasts et sont indicatives. Les liens d’écoute renvoient vers les plateformes officielles. Le code et les données sont publics sur <a href="{REPO_URL}" target="_blank" rel="noopener noreferrer">GitHub</a>.</p>
    </section>
    <section class="panel">
      <h2>Stack technique</h2>
      <p>Python, PyYAML, requests, feedparser, HTML/CSS/JavaScript vanilla, GitHub Actions et GitHub Pages. Aucun framework front, aucun tracker, aucune dépendance runtime. Le site a été vibecodé avec cette stack.</p>
    </section>
  </main>'''
    return layout(
        title="À propos · CyberPodcast",
        description="Découvrez la méthode, les sources et l’automatisation du projet CyberPodcast.",
        body=body,
        canonical_path="a-propos.html",
    )


def contribute_page() -> str:
    issue_url = f"{REPO_URL}/issues/new?template=nouvelle-ressource.yml"
    pr_url = f"{REPO_URL}/compare"
    guide_url = f"{REPO_URL}/blob/main/CONTRIBUTING.md"
    security_url = f"{REPO_URL}/blob/main/SECURITY.md"
    body = f'''
  <main class="page prose" id="contenu">
    <header class="page-header">
      <p class="eyebrow">Contribuer</p>
      <h1>Proposer un podcast ou <span class="gradient">une ressource</span></h1>
      <p class="lead">Un podcast manque, un lien est mort, une fiche mérite une correction ? La contribution passe par GitHub : ouvrez une issue guidée ou envoyez une pull request. Les liens officiels et les flux vérifiés sont toujours prioritaires.</p>
      <div class="prose-actions">
        <a class="button" href="{issue_url}" target="_blank" rel="noopener noreferrer">Proposer une ressource sur GitHub</a>
        <a class="button button-secondary" href="{pr_url}" target="_blank" rel="noopener noreferrer">Ouvrir une pull request</a>
      </div>
    </header>
    <section class="panel">
      <h2>Critères de sélection</h2>
      <ul>
        <li>Le sujet principal est la cybersécurité, le cloud, le développement ou un sujet adjacent clairement utile à la communauté.</li>
        <li>La ressource est publique, consultable sans accès privé et dispose d’un site officiel ou d’un flux RSS stable.</li>
        <li>Le podcast est actif ou récemment actif ; un arrêt de publication peut être accepté si l’intérêt historique est expliqué.</li>
        <li>Il n’existe pas déjà de fiche ou d’issue ouverte pour la même ressource.</li>
        <li>Le contenu n’est ni illégal, ni haineux, ni trompeur, et les liens d’écoute renvoient vers les plateformes officielles.</li>
      </ul>
      <h2>Format attendu</h2>
      <p>Ajoutez une entrée dans le fichier source adapté : <code>data/podcasts-cyber.yaml</code>, <code>data/podcasts-cloud.yaml</code> ou <code>data/podcasts-dev.yaml</code>. Ne modifiez pas <code>podcasts.yaml</code> ni <code>docs/</code> à la main : ils sont générés par le pipeline.</p>
      <pre><code>  - id: mon-podcast
    name: "Mon Podcast"
    category: ["Cybersécurité", "Blue Team"]
    language: fr
    host: "Prénom Nom"
    status: active
    website: https://exemple.fr
    rss: https://exemple.fr/feed.xml
    apple_podcast: https://podcasts.apple.com/...
    description: "Description courte et factuelle du podcast."
    platform: Ausha</code></pre>
      <h2>Champs obligatoires</h2>
      <ul>
        <li><code>id</code> : identifiant unique en kebab-case, en minuscules et sans accent.</li>
        <li><code>name</code> : nom public exact de la ressource.</li>
        <li><code>category</code> : au moins une catégorie, par exemple <code>Cybersécurité</code>, <code>Cloud</code> ou <code>Développement</code>.</li>
        <li><code>language</code> : <code>fr</code> ou <code>en</code>.</li>
        <li><code>website</code> ou <code>rss</code> : au moins une source vérifiable ; le flux RSS est fortement recommandé.</li>
      </ul>
      <p>Les champs <code>host</code>, <code>status</code>, <code>spotify</code>, <code>youtube</code>, <code>description</code> et <code>platform</code> sont facultatifs mais améliorent la fiche générée.</p>
    </section>
    <section class="panel">
      <h2>Ouvrir une issue</h2>
      <p>Utilisez le modèle <strong>Nouvelle ressource</strong> et joignez les liens officiels, la catégorie, la langue et l’éventuel flux RSS. Pour un lien mort ou une erreur, choisissez le modèle <strong>Lien cassé</strong> ou <strong>Bug</strong> afin que le problème soit routé correctement.</p>
      <p><a class="button" href="{issue_url}" target="_blank" rel="noopener noreferrer">Proposer une ressource sur GitHub</a></p>
      <h2>Proposer une pull request</h2>
      <p>Forkuez le dépôt, créez une branche courte, modifiez uniquement le fichier <code>data/podcasts-*.yaml</code> concerné, puis lancez les vérifications locales :</p>
      <pre><code>python scripts/enrich_podcasts.py
python scripts/check_health.py
python scripts/render_html.py</code></pre>
      <p>Ouvrez ensuite la pull request avec le modèle fourni. Les fichiers générés doivent être inclus s’ils changent après le rendu.</p>
      <h2>Règles et sécurité</h2>
      <p>Le guide complet est dans <a href="{guide_url}" target="_blank" rel="noopener noreferrer">CONTRIBUTING.md</a>. Pour signaler une vulnérabilité, suivez <a href="{security_url}" target="_blank" rel="noopener noreferrer">SECURITY.md</a> et n’exposez jamais de détails exploitables dans une issue publique.</p>
    </section>
    <section class="panel">
      <h2>Prêt à contribuer ?</h2>
      <p>Une proposition claire, même minimale, est toujours utile. Merci de garder les liens officiels à jour et de respecter le code de conduite du projet.</p>
      <div class="prose-actions">
        <a class="button" href="{issue_url}" target="_blank" rel="noopener noreferrer">Proposer une ressource sur GitHub</a>
        <a class="button button-secondary" href="{guide_url}" target="_blank" rel="noopener noreferrer">Lire le guide de contribution</a>
      </div>
    </section>
  </main>'''
    return layout(
        title="Contribuer · CyberPodcast",
        description="Proposez un podcast ou une ressource à CyberPodcast : critères de sélection, format YAML, issues et pull requests.",
        body=body,
        canonical_path="contribuer.html",
    )


def not_found_page() -> str:
    body = '''
  <main class="page not-found" id="contenu">
    <p class="eyebrow">Erreur 404</p>
    <h1>Cette page n’existe <span class="gradient">pas encore</span></h1>
    <p class="lead">Le podcast ou la page demandée est introuvable. Revenez à l’annuaire pour continuer l’exploration.</p>
    <a class="button" href="/">Retour aux podcasts</a>
  </main>'''
    return layout(
        title="Page introuvable · CyberPodcast",
        description="La page demandée est introuvable sur CyberPodcast.",
        body=body,
        canonical_path="404.html",
    )


def feed_xml(podcasts: list[dict[str, Any]]) -> str:
    items: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    for podcast in podcasts:
        for episode in podcast.get("episodes") or []:
            if not isinstance(episode, dict) or not episode.get("published"):
                continue
            items.append((episode["published"], podcast, episode))
    items.sort(key=lambda item: item[0], reverse=True)
    rendered = []
    for published, podcast, episode in items[:120]:
        try:
            dt = datetime.strptime(published, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            pub_date = format_datetime(dt)
        except ValueError:
            pub_date = ""
        title = f'{podcast.get("name")} — {episode.get("title")}'
        link = episode.get("url") or canonical(f'podcast/{podcast.get("id")}.html')
        guid = episode.get("url") or f'{podcast.get("id")}-{published}-{episode.get("title")}'
        enclosure = ""
        if episode.get("audio"):
            enclosure = f'<enclosure url={quoteattr(episode["audio"])} type="audio/mpeg" />'
        rendered.append(
            f"<item><title>{xml_escape(title)}</title>"
            f"<link>{xml_escape(link)}</link>"
            f"<guid isPermaLink=\"false\">{xml_escape(guid)}</guid>"
            f"<pubDate>{xml_escape(pub_date)}</pubDate>"
            f"<description>{xml_escape(clean_description(podcast.get('description'), 400))}</description>"
            f"{enclosure}</item>"
        )
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<title>CyberPodcast · Derniers épisodes</title>
<link>{BASE_URL}/</link>
<description>Les derniers épisodes des podcasts cybersécurité, cloud et développement référencés par CyberPodcast.</description>
<language>fr</language>
<lastBuildDate>{format_datetime(GENERATED_AT)}</lastBuildDate>
{"".join(rendered)}
</channel></rss>'''


def sitemap_xml(podcasts: list[dict[str, Any]]) -> str:
    paths = [
        "",
        "episodes.html",
        "sujets.html",
        "statistiques.html",
        "a-propos.html",
        "contribuer.html",
    ] + [f'podcast/{podcast.get("id")}.html' for podcast in podcasts]
    lastmod = TODAY.isoformat()
    urls = "".join(
        f"<url><loc>{xml_escape(canonical(path))}</loc><lastmod>{lastmod}</lastmod></url>"
        for path in paths
    )
    return f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>'


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cleaned = "\n".join(line.rstrip() for line in content.splitlines())
    if content.endswith("\n"):
        cleaned += "\n"
    path.write_text(cleaned, encoding="utf-8")


def render() -> None:
    with SOURCE.open(encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    podcasts = payload.get("podcasts") or []
    if not podcasts:
        raise SystemExit(f"Aucun podcast dans {SOURCE}")
    sanitize_podcast_links(podcasts)

    known_ids = {str(podcast.get("id")) for podcast in podcasts if podcast.get("id")}
    stats = build_stats(podcasts)
    health = None
    health_path = REPORTS_DIR / "health.json"
    if health_path.exists():
        try:
            health = json.loads(health_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            health = None
    if health is not None and isinstance(health.get("podcasts"), list):
        rows = [
            row
            for row in health["podcasts"]
            if str(row.get("id")) in known_ids
        ]
        health["podcasts"] = rows
        checked_urls = {
            str(check.get("url"))
            for row in rows
            for check in (row.get("checks") or {}).values()
            if check.get("status") != "missing" and check.get("url")
        }
        health["summary"] = {
            "total": len(rows),
            "ok": sum(1 for row in rows if row.get("status") == "ok"),
            "warning": sum(1 for row in rows if row.get("status") == "warning"),
            "error": sum(1 for row in rows if row.get("status") == "error"),
            "missing": sum(
                1
                for row in rows
                for check in (row.get("checks") or {}).values()
                if check.get("status") == "missing"
            ),
            "checked_urls": len(checked_urls),
        }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / ".nojekyll").write_text("", encoding="utf-8")

    write(OUTPUT_DIR / "index.html", index_page(podcasts, stats))
    for podcast in podcasts:
        entry_id = str(podcast.get("id") or "")
        if not entry_id:
            continue
        write(OUTPUT_DIR / "podcast" / f"{entry_id}.html", detail_page(podcast, podcasts))
    write(OUTPUT_DIR / "episodes.html", latest_episodes_page(podcasts))
    write(OUTPUT_DIR / "sujets.html", topics_page(podcasts))
    write(OUTPUT_DIR / "statistiques.html", stats_page(podcasts, stats))
    write(OUTPUT_DIR / "a-propos.html", about_page(podcasts, stats))
    write(OUTPUT_DIR / "contribuer.html", contribute_page())
    write(OUTPUT_DIR / "404.html", not_found_page())

    api_dir = OUTPUT_DIR / "api"
    write(
        api_dir / "podcasts.json",
        json.dumps(
            {
                "generated_at": GENERATED_AT.isoformat(),
                "site": BASE_URL + "/",
                "count": len(podcasts),
                "podcasts": podcasts,
            },
            ensure_ascii=False,
            indent=2,
        ),
    )
    write(api_dir / "stats.json", json.dumps(stats, ensure_ascii=False, indent=2))
    if health is not None:
        write(api_dir / "health.json", json.dumps(health, ensure_ascii=False, indent=2))

    podcast_dir = OUTPUT_DIR / "podcast"
    if podcast_dir.exists():
        for path in podcast_dir.glob("*.html"):
            if path.stem not in known_ids:
                path.unlink()

    write(OUTPUT_DIR / "feed.xml", feed_xml(podcasts))
    write(OUTPUT_DIR / "sitemap.xml", sitemap_xml(podcasts))
    write(
        OUTPUT_DIR / "robots.txt",
        f"User-agent: *\nAllow: /\nSitemap: {BASE_URL}/sitemap.xml\n",
    )
    write(
        OUTPUT_DIR / "manifest.webmanifest",
        json.dumps(
            {
                "name": "CyberPodcast",
                "short_name": "CyberPodcast",
                "description": "Annuaire de podcasts cybersécurité, cloud et développement.",
                "start_url": "/",
                "scope": "/",
                "display": "standalone",
                "background_color": "#080d1c",
                "theme_color": "#080d1c",
                "icons": [
                    {
                        "src": "assets/icon-192.png",
                        "sizes": "192x192",
                        "type": "image/png",
                        "purpose": "any",
                    },
                    {
                        "src": "assets/icon-512.png",
                        "sizes": "512x512",
                        "type": "image/png",
                        "purpose": "any",
                    },
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
    )
    print(
        f"✓ {len(podcasts)} podcasts, {len(podcasts)} fiches, "
        f"index, pages secondaires, API et SEO générés dans {OUTPUT_DIR.relative_to(ROOT)}"
    )


if __name__ == "__main__":
    render()
