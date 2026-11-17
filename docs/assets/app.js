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
        theme = stored === 'light' || stored === 'dark' ? stored : 'dark';
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
      language: 'fr',
      status: 'active',
      host: '',
      listen: '',
      sort: 'last'
    }, config.defaults || {});

    var cards = Array.prototype.slice.call(grid.querySelectorAll('.card'));
    var search = document.getElementById('search');
    var host = document.getElementById('filter-host');
    var listen = document.getElementById('filter-listen');
    var status = document.getElementById('filter-status');
    var language = document.getElementById('filter-language');
    var sort = document.getElementById('sort');
    var reset = document.getElementById('reset');
    var emptyReset = document.getElementById('empty-reset');
    var filtersToggle = document.getElementById('filters-toggle');
    var toolbar = document.querySelector('.toolbar');
    var count = document.getElementById('count');
    var activeFilters = document.getElementById('active-filters');
    var empty = document.getElementById('empty');
    var topicButtons = Array.prototype.slice.call(document.querySelectorAll('[data-topic-filter]'));
    var statusOrder = { active: 0, slow: 1, archived: 2 };
    var selectedTopics = new Set();
    var params = new URLSearchParams(window.location.search);

    function paramOr(name, fallback) {
      return params.has(name) ? (params.get(name) || '') : fallback;
    }

    search.value = params.get('q') || '';
    host.value = paramOr('host', defaults.host);
    listen.value = paramOr('listen', defaults.listen);
    status.value = paramOr('status', defaults.status);
    language.value = paramOr('language', defaults.language);
    sort.value = params.get('sort') || defaults.sort;
    params.getAll('topic').forEach(function (topic) {
      if (topic) selectedTopics.add(topic);
    });
    var legacyCategory = params.get('category');
    if (legacyCategory) selectedTopics.add(legacyCategory);
    var topicList = params.get('topics');
    if (topicList) {
      topicList.split(',').forEach(function (topic) {
        if (topic) selectedTopics.add(topic);
      });
    }

    function baseMatch(card, query, selectedStatus, selectedLanguage, selectedHost, selectedListen) {
      return (!query || normalize(card.dataset.search).includes(query)) &&
        (!selectedStatus || card.dataset.status === selectedStatus) &&
        (!selectedLanguage || card.dataset.language === selectedLanguage) &&
        (!selectedHost || card.dataset.host === selectedHost) &&
        (!selectedListen || (card.dataset.listen || '').split('|').includes(selectedListen));
    }

    function syncTopicButtons() {
      var query = normalize(search.value.trim());
      var counts = {};
      cards.forEach(function (card) {
        if (!baseMatch(card, query, status.value, language.value, host.value, listen.value)) return;
        (card.dataset.topics || '').split('|').filter(Boolean).forEach(function (topic) {
          counts[topic] = (counts[topic] || 0) + 1;
        });
      });
      topicButtons.forEach(function (button) {
        var topic = button.dataset.topicFilter || '';
        var active = selectedTopics.has(topic);
        var span = button.querySelector('span');
        if (span) span.textContent = String(counts[topic] || 0);
        button.classList.toggle('is-active', active);
        button.setAttribute('aria-pressed', String(active));
      });
    }

    function syncUrl() {
      var next = new URLSearchParams();
      if (search.value.trim()) next.set('q', search.value.trim());
      if (status.value !== defaults.status) next.set('status', status.value);
      if (language.value !== defaults.language) next.set('language', language.value);
      if (host.value) next.set('host', host.value);
      if (listen.value) next.set('listen', listen.value);
      if (sort.value !== defaults.sort) next.set('sort', sort.value);
      selectedTopics.forEach(function (topic) { next.append('topic', topic); });
      var query = next.toString();
      var url = window.location.pathname + (query ? '?' + query : '') + window.location.hash;
      try {
        window.history.replaceState(null, '', url);
      } catch (error) {}
    }

    function apply() {
      var query = normalize(search.value.trim());
      var selectedStatus = status.value;
      var selectedLanguage = language.value;
      var selectedHost = host.value;
      var selectedListen = listen.value;
      var visible = new Set();

      cards.forEach(function (card) {
        var cardTopics = (card.dataset.topics || '').split('|').filter(Boolean);
        var matches = baseMatch(card, query, selectedStatus, selectedLanguage, selectedHost, selectedListen) &&
          (!selectedTopics.size || cardTopics.some(function (topic) { return selectedTopics.has(topic); }));
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
      if (selectedHost) filters.push('hébergeur : ' + selectedHost);
      if (selectedListen) filters.push('écoute : ' + selectedListen);
      if (selectedStatus) filters.push(statusLabel(selectedStatus));
      if (selectedLanguage) filters.push(languageLabel(selectedLanguage));
      if (selectedTopics.size) filters.push('taxonomie : ' + Array.from(selectedTopics).join(', '));
      activeFilters.textContent = filters.length ? filters.join(' · ') : 'tous les podcasts';
      empty.hidden = n !== 0;
      syncTopicButtons();
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
      host.value = '';
      listen.value = '';
      status.value = '';
      language.value = '';
      sort.value = defaults.sort;
      selectedTopics.clear();
      apply();
      search.focus();
    }

    [search, host, listen, status, language, sort].forEach(function (element) {
      element.addEventListener('input', apply);
      element.addEventListener('change', apply);
    });

    topicButtons.forEach(function (button) {
      button.addEventListener('click', function () {
        var topic = button.dataset.topicFilter || '';
        if (!selectedTopics.size && !search.value.trim() && !host.value && !listen.value &&
            status.value === defaults.status &&
            language.value === defaults.language) {
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

    if (filtersToggle && toolbar) {
      filtersToggle.addEventListener('click', function () {
        var open = toolbar.classList.toggle('is-filters-open');
        filtersToggle.setAttribute('aria-expanded', String(open));
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

    syncTopicButtons();
    apply();
  }

  initTheme();
  initFavorites();
  initPlayer();
  initIndex();
})();
