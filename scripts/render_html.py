#!/usr/bin/env python3
"""Génère une page statique docs/index.html depuis podcasts.yaml."""

from __future__ import annotations

import html as html_lib
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "podcasts.yaml"
OUTPUT_DIR = ROOT / "docs"
OUTPUT = OUTPUT_DIR / "index.html"
REPO_URL = "https://github.com/zebux/CyberPodcast"

STATUS_LABELS = {
    "active": "Actif",
    "slow": "Ralenti",
    "archived": "Archivé",
}

LANGUAGE_LABELS = {
    "fr": "Français",
    "en": "Anglais",
}

DEFAULT_CATEGORY = "Cybersécurité"
DEFAULT_LANGUAGE = "fr"


def escape(value: Any) -> str:
    return html_lib.escape("" if value is None else str(value), quote=True)


def text(value: Any, default: str = "—") -> str:
    if value is None or value == "" or value == []:
        return default
    return html_lib.escape(str(value))


def format_date(value: str | None) -> str:
    if not value:
        return "—"
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return html_lib.escape(str(value))


def format_number(value: int | float | None) -> str:
    if value is None:
        return "—"
    try:
        return f"{int(value):,}".replace(",", "\u202f")
    except (TypeError, ValueError):
        return html_lib.escape(str(value))


def format_duration(value: int | float | None) -> str:
    if value is None:
        return "—"
    try:
        return f"{int(round(float(value)))} min"
    except (TypeError, ValueError):
        return html_lib.escape(str(value))


def format_rating(value: int | float | None) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):.1f} / 5"
    except (TypeError, ValueError):
        return html_lib.escape(str(value))


def format_language(podcast: dict[str, Any]) -> str:
    language = podcast.get("language") or ""
    country = podcast.get("country") or ""
    label = LANGUAGE_LABELS.get(language, language.upper() if language else "—")
    if country:
        label = f"{label} · {country}"
    return label


def join_values(values: Any) -> str:
    if not values:
        return "—"
    return ", ".join(str(value) for value in values if value) or "—"


def card_html(podcast: dict[str, Any]) -> str:
    name = podcast.get("name") or podcast.get("id") or "Sans nom"
    website = podcast.get("website")
    if website:
        title = (
            f'<a href="{escape(website)}" target="_blank" rel="noopener noreferrer">'
            f"{html_lib.escape(name)}</a>"
        )
    else:
        title = html_lib.escape(name)

    categories = [str(category) for category in (podcast.get("category") or []) if category]
    category_chips = "".join(
        f'<span class="chip">{html_lib.escape(category)}</span>' for category in categories
    ) or '<span class="chip">—</span>'

    status = podcast.get("status") or "archived"
    status_label = STATUS_LABELS.get(status, status)

    hosts = [str(host) for host in (podcast.get("hosts") or []) if host]
    hosts_text = join_values(hosts)
    language_text = format_language(podcast)
    last_episode = podcast.get("last_episode")
    last_episode_text = format_date(last_episode)
    episode_count = podcast.get("episode_count")
    episode_count_text = format_number(episode_count)
    average_duration = podcast.get("average_duration")
    average_duration_text = format_duration(average_duration)
    rating = podcast.get("community_rating")
    rating_text = format_rating(rating)
    platform = podcast.get("platform") or "autre"
    platform_text = "Autre" if platform == "autre" else platform

    meta_items = [
        ("Animateurs", hosts_text),
        ("Langue", language_text),
        ("Dernier épisode", last_episode_text),
        ("Épisodes", episode_count_text),
        ("Durée moyenne", average_duration_text),
        ("Plateforme", platform_text),
        ("Note Apple", rating_text),
    ]
    meta_html = "".join(
        f'<div><dt>{html_lib.escape(label)}</dt>'
        f'<dd title="{escape(value)}">{html_lib.escape(value)}</dd></div>'
        for label, value in meta_items
    )

    description = podcast.get("description") or ""
    description_html = (
        f'<p class="description">{html_lib.escape(description)}</p>'
        if description
        else '<p class="description muted">Pas de description.</p>'
    )

    links = [
        ("Site", website, "site"),
        ("RSS", podcast.get("rss"), "rss"),
        ("Apple", podcast.get("apple_podcast"), "apple"),
        ("Spotify", podcast.get("spotify"), "spotify"),
        ("YouTube", podcast.get("youtube"), "youtube"),
        ("LinkedIn", podcast.get("linkedin"), "linkedin"),
    ]
    link_html = "".join(
        f'<a class="link link-{css}" href="{escape(url)}" target="_blank" '
        f'rel="noopener noreferrer"><span class="dot"></span>{label}</a>'
        for label, url, css in links
        if url
    )
    if not link_html:
        link_html = '<span class="muted">Aucun lien vérifié</span>'

    tags = [str(tag) for tag in (podcast.get("tags") or []) if tag]
    tags_html = ""
    if tags:
        shown = tags[:8]
        tags_html = "".join(
            f'<span class="tag">{html_lib.escape(tag)}</span>' for tag in shown
        )
        if len(tags) > len(shown):
            tags_html += (
                f'<span class="tag more" title="{escape(", ".join(tags))}">'
                f"+{len(tags) - len(shown)}</span>"
            )
    tags_section = f'<div class="tags">{tags_html}</div>' if tags_html else ""

    search_parts = [
        name,
        description,
        " ".join(hosts),
        " ".join(categories),
        " ".join(str(topic) for topic in (podcast.get("topics") or [])),
        " ".join(tags),
        platform_text,
        language_text,
    ]
    search_text = " ".join(part for part in search_parts if part)

    return f'''
<article class="card" data-name="{escape(name)}" data-search="{escape(search_text)}" data-category="{escape("|".join(categories))}" data-status="{escape(status)}" data-language="{escape(podcast.get("language") or "")}" data-platform="{escape(platform)}" data-last="{escape(last_episode or "")}" data-episodes="{escape(episode_count if episode_count is not None else 0)}" data-rating="{escape(rating if rating is not None else 0)}">
  <div class="card-head">
    <div class="card-heading">
      <h2 class="card-title">{title}</h2>
      <div class="chips">{category_chips}</div>
    </div>
    <span class="badge status-{escape(status)}">{html_lib.escape(status_label)}</span>
  </div>
  {description_html}
  <dl class="meta">{meta_html}</dl>
  <div class="links">{link_html}</div>
  {tags_section}
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
            f'<option value="{escape(value)}"{selected_attr(value)}>'
            f"{html_lib.escape(label)}{suffix}</option>"
        )
    return "".join(options)


def render() -> None:
    with SOURCE.open(encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    podcasts = payload.get("podcasts") or []
    if not podcasts:
        raise SystemExit(f"Aucun podcast dans {SOURCE}")

    total = len(podcasts)
    status_counts = Counter(podcast.get("status") or "archived" for podcast in podcasts)
    active = status_counts.get("active", 0)
    archived = status_counts.get("archived", 0)

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

    cards = "\n".join(card_html(podcast) for podcast in podcasts)
    category_options = build_options(
        categories,
        counts=category_counts,
        empty_label="Toutes les catégories",
        selected=DEFAULT_CATEGORY,
    )
    status_options = build_options(
        ["active", "slow", "archived"],
        labels=STATUS_LABELS,
        counts=status_counts,
        empty_label="Tous les statuts",
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

    latest_episode = max(
        (podcast.get("last_episode") for podcast in podcasts if podcast.get("last_episode")),
        default=None,
    )

    template = r"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>CyberPodcast · Podcasts cyber, cloud &amp; dev</title>
  <meta name="description" content="Annuaire de podcasts cybersécurité, cloud et développement, enrichi automatiquement depuis les flux RSS et Apple Podcasts.">
  <meta property="og:title" content="CyberPodcast · Podcasts cyber, cloud &amp; dev">
  <meta property="og:description" content="Annuaire de podcasts cybersécurité, cloud et développement, enrichi automatiquement.">
  <meta property="og:type" content="website">
  <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><rect width=%22100%22 height=%22100%22 rx=%2222%22 fill=%22%23080d1c%22/><circle cx=%2250%22 cy=%2242%22 r=%2217%22 fill=%22%236ee7ff%22/><rect x=%2243%22 y=%2258%22 width=%2214%22 height=%2224%22 rx=%227%22 fill=%22%23a78bfa%22/></svg>">
  <style>
    :root {
      --bg: #080d1c;
      --bg-soft: #0e1530;
      --card: rgba(255, 255, 255, 0.045);
      --card-strong: rgba(255, 255, 255, 0.075);
      --border: rgba(255, 255, 255, 0.10);
      --text: #e9eefb;
      --muted: #96a2c2;
      --accent: #6ee7ff;
      --accent-2: #a78bfa;
      --green: #34d399;
      --amber: #fbbf24;
      --red: #fb7185;
      --radius: 18px;
      --shadow: 0 18px 45px rgba(0, 0, 0, 0.28);
    }
    * { box-sizing: border-box; }
    html { scroll-behavior: smooth; }
    body {
      margin: 0;
      min-height: 100vh;
      color: var(--text);
      background:
        radial-gradient(900px 520px at 8% -10%, rgba(110, 231, 255, 0.16), transparent 60%),
        radial-gradient(820px 520px at 92% 0%, rgba(167, 139, 250, 0.14), transparent 62%),
        radial-gradient(720px 420px at 50% 110%, rgba(52, 211, 153, 0.10), transparent 60%),
        var(--bg);
      background-attachment: fixed;
      font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      line-height: 1.5;
      -webkit-font-smoothing: antialiased;
    }
    a { color: inherit; }
    .sr-only {
      position: absolute;
      width: 1px;
      height: 1px;
      padding: 0;
      margin: -1px;
      overflow: hidden;
      clip: rect(0, 0, 0, 0);
      white-space: nowrap;
      border: 0;
    }
    .hero {
      max-width: 1400px;
      margin: 0 auto;
      padding: 64px 24px 28px;
    }
    .eyebrow {
      margin: 0;
      color: var(--accent);
      font-size: 0.72rem;
      font-weight: 800;
      letter-spacing: 0.2em;
      text-transform: uppercase;
    }
    h1 {
      margin: 0.45rem 0 0.9rem;
      max-width: 900px;
      font-size: clamp(2.1rem, 5.4vw, 4rem);
      line-height: 1.03;
      letter-spacing: -0.035em;
    }
    .gradient {
      background: linear-gradient(92deg, var(--accent), var(--accent-2) 55%, #f0abfc);
      -webkit-background-clip: text;
      background-clip: text;
      color: transparent;
    }
    .toolbar {
      position: sticky;
      top: 0;
      z-index: 20;
      border-top: 1px solid var(--border);
      border-bottom: 1px solid var(--border);
      background: rgba(8, 13, 28, 0.82);
      backdrop-filter: blur(16px);
    }
    .toolbar-inner {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 10px;
      max-width: 1400px;
      margin: 0 auto;
      padding: 14px 24px;
    }
    .search { flex: 1 1 300px; }
    input[type="search"],
    select,
    button {
      height: 42px;
      border: 1px solid var(--border);
      border-radius: 12px;
      background: var(--bg-soft);
      color: var(--text);
      font: inherit;
      font-size: 0.9rem;
      outline: none;
      transition: border-color 0.16s ease, box-shadow 0.16s ease, background 0.16s ease;
    }
    input[type="search"] {
      width: 100%;
      padding: 0 14px;
    }
    input[type="search"]::placeholder { color: #6f7da1; }
    select {
      max-width: 220px;
      padding: 0 34px 0 12px;
      cursor: pointer;
    }
    button {
      padding: 0 16px;
      cursor: pointer;
      font-weight: 700;
      white-space: nowrap;
    }
    input[type="search"]:focus,
    select:focus,
    button:focus-visible {
      border-color: rgba(110, 231, 255, 0.65);
      box-shadow: 0 0 0 4px rgba(110, 231, 255, 0.12);
    }
    button:hover { background: var(--card-strong); }
    .results {
      max-width: 1400px;
      margin: 0 auto;
      padding: 20px 24px 0;
      color: var(--muted);
      font-size: 0.85rem;
      font-weight: 600;
      letter-spacing: 0.03em;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(330px, 1fr));
      gap: 18px;
      max-width: 1400px;
      margin: 0 auto;
      padding: 18px 24px 36px;
    }
    .card {
      position: relative;
      display: flex;
      flex-direction: column;
      gap: 14px;
      overflow: hidden;
      padding: 20px;
      background: linear-gradient(180deg, rgba(255, 255, 255, 0.055), rgba(255, 255, 255, 0.022));
      border: 1px solid var(--border);
      border-radius: var(--radius);
      transition: transform 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease;
    }
    .card::before {
      content: "";
      position: absolute;
      inset: 0 0 auto;
      height: 3px;
      background: linear-gradient(90deg, var(--accent), var(--accent-2));
      opacity: 0.75;
    }
    .card[data-status="slow"]::before {
      background: linear-gradient(90deg, #f59e0b, var(--amber));
    }
    .card[data-status="archived"]::before {
      background: linear-gradient(90deg, #64748b, #94a3b8);
    }
    .card:hover {
      transform: translateY(-3px);
      border-color: rgba(110, 231, 255, 0.34);
      box-shadow: var(--shadow);
    }
    .card[hidden] { display: none !important; }
    .card-head {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 12px;
    }
    .card-heading { min-width: 0; }
    .card-title {
      margin: 0 0 8px;
      font-size: 1.16rem;
      line-height: 1.25;
      letter-spacing: -0.015em;
    }
    .card-title a { text-decoration: none; }
    .card-title a:hover { color: var(--accent); }
    .badge {
      flex: 0 0 auto;
      padding: 4px 9px;
      border: 1px solid transparent;
      border-radius: 999px;
      font-size: 0.68rem;
      font-weight: 800;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      white-space: nowrap;
    }
    .status-active {
      color: #bbf7d0;
      background: rgba(34, 197, 94, 0.14);
      border-color: rgba(34, 197, 94, 0.34);
    }
    .status-slow {
      color: #fde68a;
      background: rgba(245, 158, 11, 0.14);
      border-color: rgba(245, 158, 11, 0.34);
    }
    .status-archived {
      color: #cbd5e1;
      background: rgba(148, 163, 184, 0.14);
      border-color: rgba(148, 163, 184, 0.34);
    }
    .chips, .tags {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }
    .chip {
      padding: 3px 8px;
      color: var(--muted);
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid var(--border);
      border-radius: 999px;
      font-size: 0.7rem;
      font-weight: 600;
    }
    .description {
      display: -webkit-box;
      margin: 0;
      overflow: hidden;
      color: #c8d3eb;
      font-size: 0.9rem;
      line-height: 1.55;
      -webkit-box-orient: vertical;
      -webkit-line-clamp: 4;
    }
    .muted { color: var(--muted); }
    .meta {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 9px 14px;
      margin: 0;
    }
    .meta div { min-width: 0; }
    .meta dt {
      color: var(--muted);
      font-size: 0.65rem;
      font-weight: 700;
      letter-spacing: 0.09em;
      text-transform: uppercase;
    }
    .meta dd {
      margin: 2px 0 0;
      overflow: hidden;
      font-size: 0.84rem;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .links {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: auto;
    }
    .link {
      display: inline-flex;
      align-items: center;
      gap: 7px;
      padding: 6px 10px;
      color: var(--text);
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid var(--border);
      border-radius: 999px;
      font-size: 0.76rem;
      font-weight: 700;
      text-decoration: none;
      transition: color 0.16s ease, background 0.16s ease, border-color 0.16s ease;
    }
    .link:hover {
      color: #06101f;
      background: var(--accent);
      border-color: var(--accent);
    }
    .dot {
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: currentColor;
      opacity: 0.9;
    }
    .link-site .dot { background: var(--accent); }
    .link-rss .dot { background: #fb923c; }
    .link-apple .dot { background: #c084fc; }
    .link-spotify .dot { background: var(--green); }
    .link-youtube .dot { background: var(--red); }
    .link-linkedin .dot { background: #60a5fa; }
    .link:hover .dot { background: #06101f; }
    .tags {
      padding-top: 12px;
      border-top: 1px dashed var(--border);
    }
    .tag {
      color: var(--muted);
      font-size: 0.7rem;
    }
    .tag::before {
      content: "#";
      color: var(--accent);
      font-weight: 800;
    }
    .tag.more { cursor: help; }
    .empty {
      max-width: 1400px;
      margin: 0 auto;
      padding: 64px 24px;
      color: var(--muted);
      text-align: center;
    }
    .footer {
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      gap: 12px;
      max-width: 1400px;
      margin: 0 auto;
      padding: 22px 24px 32px;
      color: var(--muted);
      border-top: 1px solid var(--border);
      font-size: 0.8rem;
    }
    .footer a { color: var(--accent); text-decoration: none; }
    .footer a:hover { text-decoration: underline; }
    @media (max-width: 720px) {
      .hero { padding: 40px 16px 20px; }
      .toolbar-inner { padding: 12px 16px; }
      .results { padding: 16px 16px 0; }
      .grid { grid-template-columns: 1fr; padding: 14px 16px 28px; }
      select { flex: 1 1 150px; max-width: none; }
      .footer { padding: 20px 16px 28px; }
    }
    @media (prefers-reduced-motion: reduce) {
      * { scroll-behavior: auto !important; transition: none !important; }
    }
  </style>
</head>
<body>
  <header class="hero">
    <p class="eyebrow">CyberPodcast · Veille podcast</p>
    <h1>Les podcasts <span class="gradient">cyber, cloud &amp; dev</span></h1>
  </header>

  <section class="toolbar" aria-label="Filtres">
    <div class="toolbar-inner">
      <label class="search">
        <span class="sr-only">Rechercher</span>
        <input id="search" type="search" placeholder="Rechercher un podcast, un sujet, un animateur…" autocomplete="off">
      </label>
      <select id="filter-category" aria-label="Filtrer par catégorie">{{CATEGORY_OPTIONS}}</select>
      <select id="filter-status" aria-label="Filtrer par statut">{{STATUS_OPTIONS}}</select>
      <select id="filter-language" aria-label="Filtrer par langue">{{LANGUAGE_OPTIONS}}</select>
      <select id="filter-platform" aria-label="Filtrer par plateforme">{{PLATFORM_OPTIONS}}</select>
      <select id="sort" aria-label="Trier">
        <option value="name">Nom (A–Z)</option>
        <option value="last">Dernier épisode</option>
        <option value="episodes">Nombre d’épisodes</option>
        <option value="rating">Note Apple</option>
        <option value="status">Statut</option>
      </select>
      <button id="reset" type="button">Réinitialiser</button>
    </div>
  </section>

  <div class="results" aria-live="polite"><span id="count">{{TOTAL}} podcasts</span></div>
  <main class="grid" id="grid">
{{CARDS}}
  </main>
  <div class="empty" id="empty" hidden>Aucun podcast ne correspond à ces filtres.</div>

  <footer class="footer">
    <span>Dernière donnée : {{UPDATED}} · Page générée automatiquement depuis <a href="{{REPO_URL}}">GitHub</a>.</span>
    <span>{{TOTAL}} podcasts · {{ACTIVE}} actifs · {{ARCHIVED}} archivés</span>
  </footer>

  <script>
    (function () {
      const grid = document.getElementById('grid');
      const cards = Array.from(grid.querySelectorAll('.card'));
      const search = document.getElementById('search');
      const category = document.getElementById('filter-category');
      const status = document.getElementById('filter-status');
      const language = document.getElementById('filter-language');
      const platform = document.getElementById('filter-platform');
      const sort = document.getElementById('sort');
      const reset = document.getElementById('reset');
      const count = document.getElementById('count');
      const empty = document.getElementById('empty');
      const statusOrder = { active: 0, slow: 1, archived: 2 };
      const defaultCategory = 'Cybersécurité';
      const defaultLanguage = 'fr';

      function normalize(value) {
        return value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
      }

      function apply() {
        const query = normalize(search.value.trim());
        const selectedCategory = category.value;
        const selectedStatus = status.value;
        const selectedLanguage = language.value;
        const selectedPlatform = platform.value;
        const visible = new Set();

        cards.forEach(function (card) {
          const matches =
            (!query || normalize(card.dataset.search).includes(query)) &&
            (!selectedCategory || card.dataset.category.split('|').includes(selectedCategory)) &&
            (!selectedStatus || card.dataset.status === selectedStatus) &&
            (!selectedLanguage || card.dataset.language === selectedLanguage) &&
            (!selectedPlatform || card.dataset.platform === selectedPlatform);
          if (matches) visible.add(card);
        });

        const sorted = cards.slice().sort(function (a, b) {
          switch (sort.value) {
            case 'last':
              return (b.dataset.last || '').localeCompare(a.dataset.last || '');
            case 'episodes':
              return Number(b.dataset.episodes || 0) - Number(a.dataset.episodes || 0);
            case 'rating':
              return Number(b.dataset.rating || 0) - Number(a.dataset.rating || 0);
            case 'status':
              return (statusOrder[a.dataset.status] ?? 9) - (statusOrder[b.dataset.status] ?? 9) ||
                a.dataset.name.localeCompare(b.dataset.name, 'fr');
            default:
              return a.dataset.name.localeCompare(b.dataset.name, 'fr');
          }
        });

        sorted.forEach(function (card) { grid.appendChild(card); });
        cards.forEach(function (card) { card.hidden = !visible.has(card); });

        const n = visible.size;
        count.textContent = n + ' podcast' + (n > 1 ? 's' : '');
        empty.hidden = n !== 0;
      }

      [search, category, status, language, platform, sort].forEach(function (element) {
        element.addEventListener('input', apply);
        element.addEventListener('change', apply);
      });

      reset.addEventListener('click', function () {
        search.value = '';
        category.value = defaultCategory;
        status.value = '';
        language.value = defaultLanguage;
        platform.value = '';
        sort.value = 'name';
        apply();
        search.focus();
      });

      search.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') {
          search.value = '';
          apply();
        }
      });

      apply();
    })();
  </script>
</body>
</html>
"""

    replacements = {
        "{{TOTAL}}": str(total),
        "{{ACTIVE}}": str(active),
        "{{ARCHIVED}}": str(archived),
        "{{CATEGORY_OPTIONS}}": category_options,
        "{{STATUS_OPTIONS}}": status_options,
        "{{LANGUAGE_OPTIONS}}": language_options,
        "{{PLATFORM_OPTIONS}}": platform_options,
        "{{CARDS}}": cards,
        "{{UPDATED}}": format_date(latest_episode),
        "{{REPO_URL}}": REPO_URL,
    }
    for placeholder, value in replacements.items():
        template = template.replace(placeholder, value)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(template, encoding="utf-8")
    (OUTPUT_DIR / ".nojekyll").write_text("", encoding="utf-8")
    print(f"✓ {total} podcasts rendus dans {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    render()
