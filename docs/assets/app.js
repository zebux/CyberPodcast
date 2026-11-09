(function () {
  'use strict';

  var FAVORITES_KEY = 'cyberpodcast-favorites';
  var THEME_KEY = 'cyberpodcast-theme';

  function normalize(value) {
    return String(value || '')
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .toLowerCase();
  }

  function readFavorites() {
    try {
      var parsed = JSON.parse(localStorage.getItem(FAVORITES_KEY) || '[]');
      return new Set(Array.isArray(parsed) ? parsed.filter(function (id) { return typeof id === 'string'; }) : []);
    } catch (error) {
      return new Set();
    }
  }

  function writeFavorites(favorites) {
    try {
      localStorage.setItem(FAVORITES_KEY, JSON.stringify(Array.from(favorites)));
    } catch (error) {}
  }

  function syncFavoriteButtons() {
    var favorites = readFavorites();
    document.querySelectorAll('.favorite-btn').forEach(function (button) {
      var isFavorite = favorites.has(button.dataset.id || '');
      button.classList.toggle('is-fav', isFavorite);
      button.setAttribute('aria-pressed', String(isFavorite));
      var label = isFavorite ? 'Retirer des favoris' : 'Ajouter aux favoris';
      var title = isFavorite ? 'Retirer des favoris' : 'Ajouter aux favoris';
      button.setAttribute('aria-label', label);
      button.title = title;
      var text = button.querySelector('.favorite-label');
      if (text) text.textContent = label;
    });
  }

  function toggleFavorite(id) {
    if (!id) return;
    var favorites = readFavorites();
    if (favorites.has(id)) {
      favorites.delete(id);
    } else {
      favorites.add(id);
    }
    writeFavorites(favorites);
    syncFavoriteButtons();
    document.dispatchEvent(new CustomEvent('cyberpodcast:favoriteschange'));
  }

  function applyTheme(theme, persist) {
    var light = theme === 'light';
    document.documentElement.dataset.theme = light ? 'light' : 'dark';
    document.querySelectorAll('.theme-toggle').forEach(function (button) {
      button.textContent = light ? 'Sombre' : 'Clair';
      button.setAttribute('aria-pressed', String(light));
      var label = light ? 'Activer le thème sombre' : 'Activer le thème clair';
      button.setAttribute('aria-label', label);
      button.title = label;
    });
    if (persist) {
      try {
        localStorage.setItem(THEME_KEY, light ? 'light' : 'dark');
      } catch (error) {}
    }
  }

  function initTheme() {
    var theme = document.documentElement.dataset.theme;
    if (theme !== 'light' && theme !== 'dark') {
      try {
        var stored = localStorage.getItem(THEME_KEY);
        theme = stored === 'light' || stored === 'dark'
          ? stored
          : (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
      } catch (error) {
        theme = 'dark';
      }
    }
    applyTheme(theme, false);
    document.querySelectorAll('.theme-toggle').forEach(function (button) {
      button.addEventListener('click', function () {
        applyTheme(document.documentElement.dataset.theme === 'light' ? 'dark' : 'light', true);
      });
    });
  }

  function initFavorites() {
    syncFavoriteButtons();
    document.addEventListener('click', function (event) {
      var button = event.target.closest('.favorite-btn');
      if (!button) return;
      event.preventDefault();
      toggleFavorite(button.dataset.id || '');
    });
  }

  function initPlayer() {
    var bar = document.getElementById('player-bar');
    var audio = document.getElementById('player-audio');
    var title = document.getElementById('player-title');
    var close = document.getElementById('player-close');
    if (!bar || !audio || !title || !close) return;

    document.addEventListener('click', function (event) {
      var button = event.target.closest('.play-btn');
      if (!button || !button.dataset.audio) return;
      event.preventDefault();
      audio.src = button.dataset.audio;
      title.textContent = button.dataset.title || 'Lecture en cours';
      bar.hidden = false;
      var promise = audio.play();
      if (promise && typeof promise.catch === 'function') {
        promise.catch(function () {});
      }
    });

    close.addEventListener('click', function () {
      audio.pause();
      audio.removeAttribute('src');
      audio.load();
      bar.hidden = true;
      title.textContent = '';
    });
  }

  function initIndex() {
    var grid = document.getElementById('podcast-grid');
    if (!grid) return;

    var config = window.CYBERPODCAST_CONFIG || {};
    var defaults = Object.assign({
      category: 'Cybersécurité',
      language: 'fr',
      status: 'active',
      platform: '',
      sort: 'name'
    }, config.defaults || {});

    var cards = Array.prototype.slice.call(grid.querySelectorAll('.card'));
    var search = document.getElementById('search');
    var category = document.getElementById('filter-category');
    var status = document.getElementById('filter-status');
    var language = document.getElementById('filter-language');
    var platform = document.getElementById('filter-platform');
    var sort = document.getElementById('sort');
    var reset = document.getElementById('reset');
    var emptyReset = document.getElementById('empty-reset');
    var favoritesToggle = document.getElementById('favorites-toggle');
    var count = document.getElementById('count');
    var activeFilters = document.getElementById('active-filters');
    var empty = document.getElementById('empty');
    var topicButtons = Array.prototype.slice.call(document.querySelectorAll('[data-topic-filter]'));
    var statusOrder = { active: 0, slow: 1, archived: 2 };
    var selectedTopics = new Set();
    var favoritesOnly = false;
    var params = new URLSearchParams(window.location.search);

    function paramOr(name, fallback) {
      return params.has(name) ? (params.get(name) || '') : fallback;
    }

    search.value = params.get('q') || '';
    category.value = paramOr('category', defaults.category);
    status.value = paramOr('status', defaults.status);
    language.value = paramOr('language', defaults.language);
    platform.value = paramOr('platform', defaults.platform);
    sort.value = params.get('sort') || defaults.sort;
    favoritesOnly = params.get('favorites') === '1' || params.get('favorites') === 'true';
    params.getAll('topic').forEach(function (topic) {
      if (topic) selectedTopics.add(topic);
    });
    var topicList = params.get('topics');
    if (topicList) {
      topicList.split(',').forEach(function (topic) {
        if (topic) selectedTopics.add(topic);
      });
    }

    function syncTopicButtons() {
      topicButtons.forEach(function (button) {
        var active = selectedTopics.has(button.dataset.topicFilter || '');
        button.classList.toggle('is-active', active);
        button.setAttribute('aria-pressed', String(active));
      });
    }

    function syncFavoritesToggle() {
      if (!favoritesToggle) return;
      var total = readFavorites().size;
      favoritesToggle.textContent = 'Favoris' + (total ? ' (' + total + ')' : '');
      favoritesToggle.setAttribute('aria-pressed', String(favoritesOnly));
      favoritesToggle.classList.toggle('is-active', favoritesOnly);
    }

    function syncUrl() {
      var next = new URLSearchParams();
      if (search.value.trim()) next.set('q', search.value.trim());
      if (category.value !== defaults.category) next.set('category', category.value);
      if (status.value !== defaults.status) next.set('status', status.value);
      if (language.value !== defaults.language) next.set('language', language.value);
      if (platform.value) next.set('platform', platform.value);
      if (sort.value !== defaults.sort) next.set('sort', sort.value);
      selectedTopics.forEach(function (topic) { next.append('topic', topic); });
      if (favoritesOnly) next.set('favorites', '1');
      var query = next.toString();
      var url = window.location.pathname + (query ? '?' + query : '') + window.location.hash;
      try {
        window.history.replaceState(null, '', url);
      } catch (error) {}
    }

    function apply() {
      var query = normalize(search.value.trim());
      var selectedCategory = category.value;
      var selectedStatus = status.value;
      var selectedLanguage = language.value;
      var selectedPlatform = platform.value;
      var favorites = readFavorites();
      var visible = new Set();

      cards.forEach(function (card) {
        var cardTopics = (card.dataset.topics || '').split('|').filter(Boolean);
        var matches =
          (!query || normalize(card.dataset.search).includes(query)) &&
          (!selectedCategory || (card.dataset.category || '').split('|').includes(selectedCategory)) &&
          (!selectedStatus || card.dataset.status === selectedStatus) &&
          (!selectedLanguage || card.dataset.language === selectedLanguage) &&
          (!selectedPlatform || card.dataset.platform === selectedPlatform) &&
          (!selectedTopics.size || cardTopics.some(function (topic) { return selectedTopics.has(topic); })) &&
          (!favoritesOnly || favorites.has(card.dataset.id || ''));
        if (matches) visible.add(card);
      });

      var sorted = cards.slice().sort(function (a, b) {
        switch (sort.value) {
          case 'last':
            return (b.dataset.last || '').localeCompare(a.dataset.last || '');
          case 'episodes':
            return Number(b.dataset.episodes || 0) - Number(a.dataset.episodes || 0);
          case 'rating':
            return Number(b.dataset.rating || 0) - Number(a.dataset.rating || 0);
          case 'duration':
            return Number(b.dataset.duration || 0) - Number(a.dataset.duration || 0);
          case 'recent':
            return (b.dataset.firstSeen || '').localeCompare(a.dataset.firstSeen || '');
          case 'status':
            return (statusOrder[a.dataset.status] || 9) - (statusOrder[b.dataset.status] || 9) ||
              a.dataset.name.localeCompare(b.dataset.name, 'fr');
          default:
            return a.dataset.name.localeCompare(b.dataset.name, 'fr');
        }
      });

      sorted.forEach(function (card) { grid.appendChild(card); });
      cards.forEach(function (card) { card.hidden = !visible.has(card); });

      var n = visible.size;
      count.textContent = n + ' podcast' + (n > 1 ? 's' : '');
      var filters = [];
      if (query) filters.push('recherche « ' + search.value.trim() + ' »');
      if (selectedCategory) filters.push(selectedCategory);
      if (selectedStatus) filters.push(statusLabel(selectedStatus));
      if (selectedLanguage) filters.push(languageLabel(selectedLanguage));
      if (selectedPlatform) filters.push(selectedPlatform === 'autre' ? 'Autre' : selectedPlatform);
      if (selectedTopics.size) filters.push('sujets : ' + Array.from(selectedTopics).join(', '));
      if (favoritesOnly) filters.push('favoris');
      activeFilters.textContent = filters.length ? filters.join(' · ') : 'tous les podcasts';
      empty.hidden = n !== 0;
      syncTopicButtons();
      syncFavoritesToggle();
      syncUrl();
    }

    function statusLabel(value) {
      return { active: 'Actif', slow: 'Peu actif', archived: 'Inactif' }[value] || value;
    }

    function languageLabel(value) {
      return { fr: 'Français', en: 'Anglais' }[value] || String(value).toUpperCase();
    }

    function resetFilters() {
      search.value = '';
      category.value = defaults.category;
      status.value = defaults.status;
      language.value = defaults.language;
      platform.value = defaults.platform;
      sort.value = defaults.sort;
      selectedTopics.clear();
      favoritesOnly = false;
      apply();
      search.focus();
    }

    [search, category, status, language, platform, sort].forEach(function (element) {
      element.addEventListener('input', apply);
      element.addEventListener('change', apply);
    });

    topicButtons.forEach(function (button) {
      button.addEventListener('click', function () {
        var topic = button.dataset.topicFilter || '';
        if (!selectedTopics.size && !search.value.trim() && !platform.value &&
            category.value === defaults.category &&
            status.value === defaults.status &&
            language.value === defaults.language) {
          category.value = '';
          status.value = '';
          language.value = '';
        }
        if (selectedTopics.has(topic)) {
          selectedTopics.delete(topic);
        } else {
          selectedTopics.add(topic);
        }
        apply();
      });
    });

    if (favoritesToggle) {
      favoritesToggle.addEventListener('click', function () {
        favoritesOnly = !favoritesOnly;
        apply();
      });
    }

    reset.addEventListener('click', resetFilters);
    if (emptyReset) emptyReset.addEventListener('click', resetFilters);

    search.addEventListener('keydown', function (event) {
      if (event.key === 'Escape') {
        search.value = '';
        apply();
      }
    });

    document.addEventListener('cyberpodcast:favoriteschange', function () {
      syncFavoritesToggle();
      if (favoritesOnly) apply();
    });

    syncTopicButtons();
    syncFavoritesToggle();
    apply();
  }

  initTheme();
  initFavorites();
  initPlayer();
  initIndex();
})();
