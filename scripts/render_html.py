#!/usr/bin/env python3
"""Génère le site statique CyberPodcast depuis podcasts.yaml.

Produit :
  - docs/index.html               annuaire filtrable
  - docs/podcast/<id>.html        fiches détaillées
  - docs/sujets.html              exploration par sujet
  - docs/statistiques.html        chiffres clés
  - docs/a-propos.html            présentation du projet
  - docs/rapport.html             rapport de santé des liens
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
from urllib.parse import quote
from xml.sax.saxutils import escape as xml_escape, quoteattr

import yaml

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "podcasts.yaml"
REPORTS_DIR = ROOT / "reports"
OUTPUT_DIR = ROOT / "docs"
ASSETS_DIR = OUTPUT_DIR / "assets"
SITE_URL = "https://zebux.github.io/CyberPodcast"
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
    "biweekly": "Bimensuel",
    "monthly": "Mensuel",
    "quarterly": "Trimestriel",
    "irregular": "Irrégulier",
}

DEFAULT_CATEGORY = "Cybersécurité"
DEFAULT_LANGUAGE = "fr"
DEFAULT_STATUS = "active"

THEME_INIT = """<script>
(function () {
  try {
    var stored = localStorage.getItem('cyberpodcast-theme');
    var theme = stored === 'light' || stored === 'dark'
      ? stored
      : (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
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
    if value is None:
        return "—"
    try:
        rating = f"{float(value):.1f}/5"
        if count is not None:
            rating += f" ({int(count)})"
        return rating
    except (TypeError, ValueError):
        return html_lib.escape(str(value))


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
    return f"{SITE_URL}/{path.lstrip('/')}"


def url_for(path: str, root: str = "") -> str:
    return f"{root}{path.lstrip('/')}"


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


def topic_chips(podcast: dict[str, Any], root: str = "", limit: int = 6) -> str:
    topics = [str(topic) for topic in (podcast.get("topics") or []) if topic]
    if not topics:
        topics = [str(category) for category in (podcast.get("category") or []) if category]
    if not topics:
        return ""
    shown = topics[:limit]
    chips = "".join(
        f'<a class="chip" href="{root}index.html?topic={quote(topic, safe="")}&amp;category=&amp;status=&amp;language=">'
        f"{html_lib.escape(topic)}</a>"
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

    categories = [str(category) for category in (podcast.get("category") or []) if category]
    category_chips = "".join(
        f'<span class="chip chip-category">{html_lib.escape(category)}</span>'
        for category in categories[:3]
    )
    if not category_chips:
        category_chips = '<span class="chip">—</span>'

    hosts = [str(host) for host in (podcast.get("hosts") or []) if host]
    hosts_text = ", ".join(hosts) or podcast.get("author") or "—"
    last_episode = podcast.get("last_episode")
    last_episode_title = podcast.get("last_episode_title")
    rating = podcast.get("community_rating")
    rating_count = podcast.get("community_rating_count")
    platform = podcast.get("platform") or "autre"
    platform_text = "Autre" if platform == "autre" else str(platform)

    meta_items = [
        ("Animateurs", hosts_text),
        ("Langue", language_text(podcast)),
        ("Dernier épisode", fmt_date(last_episode)),
        ("Rythme", frequency_text(podcast)),
        ("Épisodes", fmt_number(podcast.get("episode_count"))),
        ("Durée moyenne", fmt_duration(podcast.get("average_duration"))),
        ("Note Apple", fmt_rating(rating, rating_count)),
        ("Plateforme", platform_text),
    ]
    meta_html = "".join(
        f'<div><dt>{html_lib.escape(label)}</dt>'
        f'<dd title="{esc(value)}">{html_lib.escape(str(value))}</dd></div>'
        for label, value in meta_items
    )

    description = podcast.get("description") or ""
    description_html = (
        f'<p class="description">{html_lib.escape(description)}</p>'
        if description
        else '<p class="description muted">Pas de description.</p>'
    )

    topics = podcast.get("topics") or []
    tags = podcast.get("tags") or []
    topics_text = "|".join(str(topic) for topic in topics)
    categories_text = "|".join(categories)
    audio = podcast.get("last_episode_audio") or ""

    return f'''
<article class="card" data-id="{esc(entry_id)}" data-name="{esc(name)}" data-search="{esc(search_text(podcast))}" data-category="{esc(categories_text)}" data-topics="{esc(topics_text)}" data-status="{esc(podcast.get("status") or "archived")}" data-language="{esc(podcast.get("language") or "")}" data-platform="{esc(platform)}" data-last="{esc(last_episode or "")}" data-episodes="{esc(podcast.get("episode_count") or 0)}" data-rating="{esc(rating if rating is not None else 0)}" data-duration="{esc(podcast.get("average_duration") or 0)}" data-first-seen="{esc(podcast.get("first_seen") or "")}" data-audio="{esc(audio)}" data-title="{esc(name + (" — " + last_episode_title if last_episode_title else ""))}">
  <div class="card-cover">{cover_html(podcast, "cover")}</div>
  <div class="card-body">
    <div class="card-head">
      <div class="card-heading">
        <h2 class="card-title">{title}</h2>
        <div class="chips">{category_chips}</div>
      </div>
      {status_badge(podcast)}
    </div>
    {description_html}
    <dl class="meta">{meta_html}</dl>
    {topic_chips(podcast, root, 5)}
    <div class="card-actions">
      {play_button(podcast)}
      {favorite_button(podcast)}
      <a class="button button-small" href="{detail_url}">Détails</a>
      {link_pill("Site", website, "site")}
      {link_pill("Apple", podcast.get("apple_podcast"), "apple")}
      {link_pill("Spotify", podcast.get("spotify"), "spotify")}
      {link_pill("YouTube", podcast.get("youtube"), "youtube")}
    </div>
    {tag_html(podcast, 8)}
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
    page_url = canonical(canonical_path) if canonical_path else SITE_URL + "/"
    image_url = image or f"{SITE_URL}/assets/icon.svg"
    structured = ""
    if json_ld:
        structured = f'<script type="application/ld+json">{json_safe(json_ld)}</script>'
    return f'''<!doctype html>
<html lang="fr">
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
  <link rel="icon" href="{root}assets/icon.svg" type="image/svg+xml">
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
      <a class="brand" href="{root}index.html" aria-label="CyberPodcast, accueil">
        <span class="brand-mark">CP</span>
        <span class="brand-text">Cyber<span>Podcast</span></span>
      </a>
      <nav class="nav-links" aria-label="Navigation principale">
        <a class="nav-link" href="{root}index.html">Podcasts</a>
        <a class="nav-link" href="{root}sujets.html">Sujets</a>
        <a class="nav-link" href="{root}statistiques.html">Statistiques</a>
        <a class="nav-link" href="{root}a-propos.html">À propos</a>
        <a class="nav-link" href="{root}rapport.html">Rapport</a>
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
</body>
</html>'''


def build_stats(podcasts: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(podcast.get("status") or "archived" for podcast in podcasts)
    language_counts = Counter(podcast.get("language") or "??" for podcast in podcasts)
    platform_counts = Counter(podcast.get("platform") or "autre" for podcast in podcasts)
    topic_counts = Counter(
        str(topic)
        for podcast in podcasts
        for topic in (podcast.get("topics") or [])
        if topic
    )
    category_counts = Counter(
        str(category)
        for podcast in podcasts
        for category in (podcast.get("category") or [])
        if category
    )
    ratings = [
        float(podcast["community_rating"])
        for podcast in podcasts
        if podcast.get("community_rating") is not None
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
        "by_platform": dict(platform_counts),
        "by_topic": dict(topic_counts),
        "by_category": dict(category_counts),
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


def topic_buttons(podcasts: list[dict[str, Any]]) -> str:
    counts = Counter(
        str(topic)
        for podcast in podcasts
        for topic in (podcast.get("topics") or [])
        if topic
    )
    return "".join(
        f'<button class="topic-chip" type="button" data-topic-filter="{esc(topic)}" '
        f'aria-pressed="false">{html_lib.escape(topic)} <span>{count}</span></button>'
        for topic, count in sorted(counts.items(), key=lambda item: (-item[1], item[0].casefold()))
    )


def index_page(podcasts: list[dict[str, Any]], stats: dict[str, Any]) -> str:
    categories = sorted(
        {
            str(category)
            for podcast in podcasts
            for category in (podcast.get("category") or [])
            if category
        },
        key=str.casefold,
    )
    category_counts = Counter(
        str(category)
        for podcast in podcasts
        for category in (podcast.get("category") or [])
        if category
    )
    platforms = sorted(
        {podcast.get("platform") or "autre" for podcast in podcasts},
        key=str.casefold,
    )
    platform_counts = Counter(podcast.get("platform") or "autre" for podcast in podcasts)
    languages = sorted(
        {podcast.get("language") for podcast in podcasts if podcast.get("language")},
        key=str.casefold,
    )
    language_counts = Counter(
        podcast.get("language") for podcast in podcasts if podcast.get("language")
    )

    cards = "\n".join(podcast_card(podcast) for podcast in podcasts)
    category_options = build_options(
        categories,
        counts=category_counts,
        empty_label="Toutes les catégories",
        selected=DEFAULT_CATEGORY,
    )
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
    platform_options = build_options(
        platforms,
        labels={"autre": "Autre"},
        counts=platform_counts,
        empty_label="Toutes les plateformes",
    )
    config = {
        "defaults": {
            "category": DEFAULT_CATEGORY,
            "language": DEFAULT_LANGUAGE,
            "status": DEFAULT_STATUS,
            "platform": "",
            "sort": "name",
        },
        "total": len(podcasts),
    }
    updated = latest_episode_date(podcasts)

    body = f'''
  <main id="contenu">
    <section class="hero">
      <p class="eyebrow">Annuaire automatisé · {esc(fmt_date(updated))}</p>
      <h1>Les podcasts <span class="gradient">cyber, cloud &amp; dev</span></h1>
      <p class="lead">Découvrez, filtrez et écoutez les meilleurs podcasts francophones et internationaux sur la cybersécurité, le cloud et le développement. Données enrichies depuis les flux RSS, Apple Podcasts et les sites officiels.</p>
      <div class="stats-strip">
        <div class="stat"><strong>{stats["total"]}</strong><span>podcasts</span></div>
        <div class="stat"><strong>{stats["by_status"].get("active", 0)}</strong><span>actifs</span></div>
        <div class="stat"><strong>{fmt_number(stats["total_episodes"])}</strong><span>épisodes référencés</span></div>
        <div class="stat"><strong>{len(languages)}</strong><span>langues</span></div>
        <div class="stat"><strong>{stats["with_audio"]}</strong><span>écoute directe</span></div>
      </div>
    </section>

    <section class="toolbar" aria-label="Filtres">
      <div class="toolbar-inner">
        <label class="search">
          <span class="sr-only">Rechercher</span>
          <input id="search" type="search" placeholder="Rechercher un podcast, un sujet, un animateur…" autocomplete="off">
        </label>
        <select id="filter-category" aria-label="Filtrer par catégorie">{category_options}</select>
        <select id="filter-status" aria-label="Filtrer par statut">{status_options}</select>
        <select id="filter-language" aria-label="Filtrer par langue">{language_options}</select>
        <select id="filter-platform" aria-label="Filtrer par plateforme">{platform_options}</select>
        <select id="sort" aria-label="Trier">
          <option value="name">Nom (A–Z)</option>
          <option value="last">Dernier épisode</option>
          <option value="episodes">Nombre d’épisodes</option>
          <option value="rating">Note Apple</option>
          <option value="duration">Durée moyenne</option>
          <option value="recent">Ajout récent</option>
          <option value="status">Statut</option>
        </select>
        <button id="favorites-toggle" type="button" aria-pressed="false">Favoris</button>
        <button id="reset" type="button">Réinitialiser</button>
      </div>
      <div class="topic-bar" aria-label="Filtrer par sujet">
        <span class="topic-label">Sujets</span>
        {topic_buttons(podcasts)}
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
            "url": SITE_URL + "/",
            "description": "Annuaire de podcasts cybersécurité, cloud et développement.",
            "potentialAction": {
                "@type": "SearchAction",
                "target": f"{SITE_URL}/index.html?q={{search_term_string}}",
                "query-input": "required name=search_term_string",
            },
        },
    )


def meta_items(podcast: dict[str, Any]) -> list[tuple[str, str]]:
    hosts = ", ".join(str(host) for host in (podcast.get("hosts") or []) if host)
    return [
        ("Animateurs", hosts or podcast.get("author") or "—"),
        ("Auteur", podcast.get("author") or "—"),
        ("Langue", language_text(podcast)),
        ("Dernier épisode", fmt_date(podcast.get("last_episode"))),
        ("Rythme", frequency_text(podcast)),
        ("Épisodes", fmt_number(podcast.get("episode_count"))),
        ("Durée moyenne", fmt_duration(podcast.get("average_duration"))),
        ("Note Apple", fmt_rating(podcast.get("community_rating"), podcast.get("community_rating_count"))),
        ("Plateforme", "Autre" if (podcast.get("platform") or "autre") == "autre" else str(podcast.get("platform"))),
        ("Pays", podcast.get("country") or "—"),
        ("Ajouté le", fmt_date(podcast.get("first_seen"))),
        ("Mis à jour le", fmt_date(podcast.get("updated_at"))),
    ]


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
    description = podcast.get("description") or f"Fiche du podcast {name} sur CyberPodcast."
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

    meta_html = "".join(
        f'<div><dt>{html_lib.escape(label)}</dt><dd>{html_lib.escape(value)}</dd></div>'
        for label, value in meta_items(podcast)
    )
    related = related_podcasts(podcast, podcasts)
    related_html = "".join(mini_card(other, root) for other in related) or '<p class="muted">Aucun podcast proche pour le moment.</p>'
    tags = tag_html(podcast, 20)
    topics = topic_chips(podcast, root, 20)

    body = f'''
  <main class="detail" id="contenu">
    <nav class="breadcrumb" aria-label="Fil d’Ariane">
      <a href="{root}index.html">Podcasts</a><span>/</span><span>{esc(name)}</span>
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
        </div>
      </div>
    </section>

    <div class="detail-grid">
      <section class="panel">
        <div class="panel-head"><h2>Dernier épisode</h2>{f'<span class="muted">{esc(fmt_date(podcast.get("last_episode")))}</span>' if podcast.get("last_episode") else ''}</div>
        {player}
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
        "image": podcast.get("image") or f"{SITE_URL}/assets/icon.svg",
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
        for topic in podcast.get("topics") or []:
            topic_map.setdefault(str(topic), []).append(podcast)
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
      <a class="topic-card" href="index.html?topic={quote(topic, safe="")}&amp;category=&amp;status=&amp;language=">
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
    platform_counts = Counter(stats["by_platform"])
    topic_counts = Counter(stats["by_topic"])
    category_counts = Counter(stats["by_category"])
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
      <section class="panel"><h2>Plateformes</h2>{bar_list(platform_counts, total, lambda value: "Autre" if value == "autre" else value)}</section>
      <section class="panel"><h2>Catégories</h2>{bar_list(category_counts, total, limit=14)}</section>
      <section class="panel panel-wide"><h2>Sujets les plus représentés</h2>{bar_list(topic_counts, total, limit=24)}</section>
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
        <li>Les sources sont maintenues dans <code>data/podcasts-*.yaml</code>.</li>
        <li>Les corrections manuelles vérifiées sont dans <code>data/curated.yaml</code>.</li>
        <li>Le pipeline Python fusionne, déduplique, enrichit et écrit <code>podcasts.yaml</code>.</li>
        <li>Un workflow GitHub Actions contrôle la santé des liens, régénère le site et publie GitHub Pages.</li>
      </ol>
      <h2>Automatisation</h2>
      <p>Le workflow tourne chaque jour. Il récupère les nouveautés, met à jour les notes et les derniers épisodes, produit un rapport de santé et redéploie le site. Les erreurs réseau ne bloquent pas la publication : les données précédentes servent de repli.</p>
      <h2>Contribuer</h2>
      <p>Une erreur, un podcast manquant, un flux cassé ? Ouvrez une <a href="{REPO_URL}/issues" target="_blank" rel="noopener noreferrer">issue</a> ou proposez une correction dans <code>data/curated.yaml</code>. Les liens officiels et les flux vérifiés sont prioritaires.</p>
      <h2>Transparence</h2>
      <p>Les notes affichées proviennent d’Apple Podcasts et sont indicatives. Les liens d’écoute renvoient vers les plateformes officielles. Le code et les données sont publics sur <a href="{REPO_URL}" target="_blank" rel="noopener noreferrer">GitHub</a>.</p>
    </section>
    <section class="panel">
      <h2>Stack technique</h2>
      <p>Python, PyYAML, requests, feedparser, HTML/CSS/JavaScript vanilla, GitHub Actions et GitHub Pages. Aucun framework front, aucun tracker, aucune dépendance runtime.</p>
    </section>
  </main>'''
    return layout(
        title="À propos · CyberPodcast",
        description="Découvrez la méthode, les sources et l’automatisation du projet CyberPodcast.",
        body=body,
        canonical_path="a-propos.html",
    )


def health_badge(result: dict[str, Any]) -> str:
    status = result.get("status") or "unknown"
    labels = {
        "ok": "OK",
        "warning": "Vigilance",
        "error": "Erreur",
        "missing": "Absent",
        "unchecked": "Non vérifié",
    }
    label = labels.get(status, status)
    title = result.get("error") or result.get("http") or result.get("url") or ""
    return f'<span class="health-badge health-{esc(status)}" title="{esc(title)}">{esc(label)}</span>'


def basic_health(podcasts: list[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for podcast in podcasts:
        checks = {}
        for key, field in (
            ("site", "website"),
            ("rss", "rss"),
            ("image", "image"),
            ("audio", "last_episode_audio"),
        ):
            checks[key] = {
                "status": "unchecked" if podcast.get(field) else "missing",
                "url": podcast.get(field),
            }
        rows.append(
            {
                "id": podcast.get("id"),
                "name": podcast.get("name"),
                "status": "ok",
                "checks": checks,
            }
        )
    return {
        "generated_at": GENERATED_AT.isoformat(),
        "summary": {
            "total": len(podcasts),
            "ok": len(podcasts),
            "warning": 0,
            "error": 0,
            "missing": 0,
        },
        "podcasts": rows,
        "mode": "basic",
    }


def report_page(report: dict[str, Any] | None, podcasts: list[dict[str, Any]]) -> str:
    report = report or basic_health(podcasts)
    summary = report.get("summary") or {}
    rows = []
    check_labels = {"site": "Site", "rss": "RSS", "image": "Image", "audio": "Audio"}
    for item in report.get("podcasts") or []:
        checks = item.get("checks") or {}
        check_cells = "".join(
            f"<td>{health_badge(checks.get(key) or {'status': 'unchecked'})}</td>"
            for key in ("site", "rss", "image", "audio")
        )
        overall = item.get("status") or "unknown"
        rows.append(
            f'<tr><td><a href="podcast/{esc(item.get("id"))}.html">{esc(item.get("name") or item.get("id"))}</a></td>'
            f'<td><span class="health-badge health-{esc(overall)}">{esc(overall)}</span></td>'
            f"{check_cells}</tr>"
        )
    mode_note = (
        '<p class="notice">Rapport complet généré par <code>scripts/check_health.py</code>.</p>'
        if report.get("mode") != "basic"
        else '<p class="notice">Rapport de secours : lancez <code>python scripts/check_health.py</code> pour vérifier les liens en direct.</p>'
    )
    body = f'''
  <main class="page" id="contenu">
    <header class="page-header">
      <p class="eyebrow">Qualité des données</p>
      <h1>Rapport de <span class="gradient">santé</span></h1>
      <p class="lead">Vérification des sites, flux RSS, pochettes et fichiers audio. Dernier contrôle : {esc(report.get("generated_at", "—"))}.</p>
    </header>
    <section class="stats-grid">
      <div class="stat-card"><strong>{summary.get("total", len(podcasts))}</strong><span>podcasts</span></div>
      <div class="stat-card"><strong>{summary.get("ok", 0)}</strong><span>sans erreur</span></div>
      <div class="stat-card"><strong>{summary.get("warning", 0)}</strong><span>vigilances</span></div>
      <div class="stat-card"><strong>{summary.get("error", 0)}</strong><span>erreurs</span></div>
      <div class="stat-card"><strong>{summary.get("missing", 0)}</strong><span>liens absents</span></div>
    </section>
    {mode_note}
    <section class="panel table-panel">
      <h2>Détail par podcast</h2>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Podcast</th><th>Global</th><th>Site</th><th>RSS</th><th>Image</th><th>Audio</th></tr></thead>
          <tbody>{"".join(rows)}</tbody>
        </table>
      </div>
    </section>
  </main>'''
    return layout(
        title="Rapport de santé · CyberPodcast",
        description="Rapport de vérification des liens, flux RSS, images et fichiers audio du catalogue CyberPodcast.",
        body=body,
        canonical_path="rapport.html",
    )


def not_found_page() -> str:
    body = '''
  <main class="page not-found" id="contenu">
    <p class="eyebrow">Erreur 404</p>
    <h1>Cette page n’existe <span class="gradient">pas encore</span></h1>
    <p class="lead">Le podcast ou la page demandée est introuvable. Revenez à l’annuaire pour continuer l’exploration.</p>
    <a class="button" href="index.html">Retour aux podcasts</a>
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
            f"<description>{xml_escape(podcast.get('description') or '')}</description>"
            f"{enclosure}</item>"
        )
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<title>CyberPodcast · Derniers épisodes</title>
<link>{SITE_URL}/</link>
<description>Les derniers épisodes des podcasts cybersécurité, cloud et développement référencés par CyberPodcast.</description>
<language>fr</language>
<lastBuildDate>{format_datetime(GENERATED_AT)}</lastBuildDate>
{"".join(rendered)}
</channel></rss>'''


def sitemap_xml(podcasts: list[dict[str, Any]]) -> str:
    paths = [
        "",
        "index.html",
        "sujets.html",
        "statistiques.html",
        "a-propos.html",
        "rapport.html",
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

    stats = build_stats(podcasts)
    health = None
    health_path = REPORTS_DIR / "health.json"
    if health_path.exists():
        try:
            health = json.loads(health_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            health = None

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / ".nojekyll").write_text("", encoding="utf-8")

    write(OUTPUT_DIR / "index.html", index_page(podcasts, stats))
    for podcast in podcasts:
        entry_id = str(podcast.get("id") or "")
        if not entry_id:
            continue
        write(OUTPUT_DIR / "podcast" / f"{entry_id}.html", detail_page(podcast, podcasts))
    write(OUTPUT_DIR / "sujets.html", topics_page(podcasts))
    write(OUTPUT_DIR / "statistiques.html", stats_page(podcasts, stats))
    write(OUTPUT_DIR / "a-propos.html", about_page(podcasts, stats))
    write(OUTPUT_DIR / "rapport.html", report_page(health, podcasts))
    write(OUTPUT_DIR / "404.html", not_found_page())

    api_dir = OUTPUT_DIR / "api"
    write(
        api_dir / "podcasts.json",
        json.dumps(
            {
                "generated_at": GENERATED_AT.isoformat(),
                "site": SITE_URL + "/",
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

    write(OUTPUT_DIR / "feed.xml", feed_xml(podcasts))
    write(OUTPUT_DIR / "sitemap.xml", sitemap_xml(podcasts))
    write(
        OUTPUT_DIR / "robots.txt",
        f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}/sitemap.xml\n",
    )
    write(
        OUTPUT_DIR / "manifest.webmanifest",
        json.dumps(
            {
                "name": "CyberPodcast",
                "short_name": "CyberPodcast",
                "description": "Annuaire de podcasts cybersécurité, cloud et développement.",
                "start_url": "/CyberPodcast/",
                "scope": "/CyberPodcast/",
                "display": "standalone",
                "background_color": "#080d1c",
                "theme_color": "#080d1c",
                "icons": [
                    {
                        "src": "assets/icon.svg",
                        "sizes": "any",
                        "type": "image/svg+xml",
                        "purpose": "any",
                    }
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
