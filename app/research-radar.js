(function (root) {
  'use strict';
  if (!root || !root.ResearchRadarAPI || !root.ResearchRadarState) return;
  var API = root.ResearchRadarAPI, State = root.ResearchRadarState;
  var Icons = root.ResearchRadarIcons || { icon: function () { return ''; } };
  var current = null;

  function esc(value) { return String(value == null ? '' : value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
  function icon(name, size) { return Icons.icon(name, size || 18); }
  function isRoute() { return /^#\/research-radar\/?(?:\?|$)/.test(root.location.hash); }
  function config() { return root.RESEARCH_RADAR_CONFIG ? Object.assign({ mode: 'fixture', baseUrl: 'fixtures/research_radar' }, root.RESEARCH_RADAR_CONFIG) : { mode: 'fixture', baseUrl: 'fixtures/research_radar' }; }
  function debounce(fn, wait) { var timer; return function () { var args = arguments; clearTimeout(timer); timer = setTimeout(function () { fn.apply(null, args); }, wait); }; }
  function splitLines(value) { return String(value || '').split(/\n|,/).map(function (item) { return item.trim(); }).filter(Boolean); }
  function readStorage(key, fallback) { try { var value = root.localStorage.getItem(key); return value == null ? fallback : value; } catch (error) { return fallback; } }
  function writeStorage(key, value) { try { root.localStorage.setItem(key, value); } catch (error) {} }

  function App(rootEl) {
    this.root = rootEl;
    this.source = API.createDataSource(config());
    this.fields = [];
    this.field = null;
    this.state = State.parseHash(root.location.hash);
    this.graph = null;
    this.drawerRequest = 0;
    this.syncPollTimer = null;
    this.syncPollRunId = null;
    this.syncPollButton = null;
    this.theme = readStorage('rr-theme', root.matchMedia && root.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    this.sidebarCollapsed = readStorage('rr-sidebar-collapsed', '0') === '1';
    this.keydownHandler = this.onGlobalKeydown.bind(this);
    root.document.addEventListener('keydown', this.keydownHandler);
  }

  App.prototype.start = function () {
    var self = this;
    this.root.innerHTML = appSkeleton();
    var fieldsRequest = this.source.listResearchFields();
    var request = this.source.getHome ? Promise.all([fieldsRequest, this.source.getHome()]) : fieldsRequest.then(function (fields) { return [fields, null]; });
    return request.then(function (result) {
      var fields = result[0] || [], home = result[1];
      if (home && home.fields) {
        var byId = Object.fromEntries(fields.map(function (field) { return [field.id, field]; }));
        self.fields = home.fields.map(function (field) { return Object.assign({}, byId[field.id] || {}, field); });
      } else self.fields = fields;
      self.field = self.fields.find(function (item) { return item.id === self.state.field; }) || null;
      if (self.state.view === 'field' && !self.field) self.state.view = 'home';
      if (!self.fields.length) return self.showHome(true);
      if (self.state.view === 'search') return self.showSearch();
      if (self.state.view === 'settings') return self.showSettings();
      if (self.field) return self.showField();
      return self.showHome(false);
    }).catch(function (error) { self.renderFatal(error); });
  };

  App.prototype.renderShell = function (options) {
    options = options || {};
    var view = options.view || 'home', title = options.title || 'Research Radar';
    var activeField = this.field && view === 'field' ? this.field.id : '';
    var sidebarFields = this.fields.map(function (field) {
      return '<button class="rr-sidebar-link rr-field-link' + (field.id === activeField ? ' is-active' : '') + '" data-open-field="' + esc(field.id) + '" title="' + esc(field.name) + '"><span class="rr-field-dot"></span><span>' + esc(field.name) + '</span>' + (field.sync_status === 'running' ? '<i class="rr-tiny-spinner" aria-label="Updating"></i>' : '') + '</button>';
    }).join('');
    this.root.innerHTML = '<main class="rr-app rr-theme-' + esc(this.theme) + (this.sidebarCollapsed ? ' rr-sidebar-collapsed' : '') + '" data-theme="' + esc(this.theme) + '" data-view="' + esc(view) + '">' +
      '<aside class="rr-sidebar" aria-label="Research Radar navigation"><div class="rr-brand"><span class="rr-brand-mark">R</span><span class="rr-brand-name">Research Radar</span><button class="rr-icon-button rr-collapse-sidebar" type="button" aria-label="Collapse sidebar" title="Collapse sidebar">' + icon('panel') + '</button></div>' +
      '<nav class="rr-sidebar-nav"><button class="rr-sidebar-link' + (view === 'home' ? ' is-active' : '') + '" data-nav="home">' + icon('home') + '<span>Home</span></button><button class="rr-sidebar-link' + (view === 'search' ? ' is-active' : '') + '" data-nav="search">' + icon('search') + '<span>Search</span></button></nav>' +
      '<div class="rr-sidebar-section"><div class="rr-sidebar-label"><span>Research Fields</span><button class="rr-icon-button" type="button" data-new-field aria-label="Create research field" title="New research field">' + icon('plus', 16) + '</button></div><div class="rr-sidebar-fields">' + sidebarFields + '</div><button class="rr-sidebar-link rr-new-field-link" type="button" data-new-field>' + icon('plus') + '<span>New Research Field</span></button></div>' +
      '<nav class="rr-sidebar-nav rr-sidebar-bottom"><button class="rr-sidebar-link" data-nav="home">' + icon('library') + '<span>Library</span></button><button class="rr-sidebar-link' + (view === 'settings' ? ' is-active' : '') + '" data-nav="settings">' + icon('settings') + '<span>Settings</span></button></nav></aside>' +
      '<button class="rr-sidebar-scrim" type="button" aria-label="Close navigation"></button><section class="rr-main"><header class="rr-topbar"><div class="rr-topbar-title"><button class="rr-icon-button rr-mobile-menu" type="button" aria-label="Open navigation">' + icon('menu') + '</button><span>Research Radar</span><i>/</i><strong>' + esc(title) + '</strong></div>' +
      '<div class="rr-topbar-actions"><button class="rr-command-trigger" type="button" data-open-command>' + icon('search') + '<span>Search papers, authors, fields...</span><kbd>Ctrl K</kbd></button>' + syncTopStatus(this.field, view) + '<button class="rr-icon-button" type="button" data-nav="settings" aria-label="Settings" title="Settings">' + icon('settings') + '</button><button class="rr-icon-button" type="button" data-theme-toggle aria-label="Toggle theme" title="Toggle theme">' + icon(this.theme === 'dark' ? 'sun' : 'moon') + '</button></div></header>' +
      '<div class="rr-workspace">' + (options.content || skeletonPage()) + '</div></section><aside class="rr-drawer" aria-hidden="true"></aside><button class="rr-drawer-scrim" aria-label="Close detail"></button><div class="rr-overlay-root"></div><div class="rr-toast-region" aria-live="polite" aria-atomic="true"></div></main>';
    this.bindShell();
  };

  App.prototype.bindShell = function () {
    var self = this, app = this.root.querySelector('.rr-app');
    this.root.querySelectorAll('[data-nav]').forEach(function (button) { button.addEventListener('click', function () { self.navigate(button.dataset.nav); }); });
    this.root.querySelectorAll('.rr-sidebar [data-open-field]').forEach(function (button) { button.addEventListener('click', function () { self.openField(button.dataset.openField); }); });
    this.root.querySelectorAll('.rr-sidebar [data-new-field]').forEach(function (button) { button.addEventListener('click', function () { self.openFieldDialog(); }); });
    var command = this.root.querySelector('[data-open-command]'); if (command) command.addEventListener('click', function () { self.openCommandPalette(); });
    var theme = this.root.querySelector('[data-theme-toggle]'); if (theme) theme.addEventListener('click', function () { self.toggleTheme(); });
    var collapse = this.root.querySelector('.rr-collapse-sidebar'); if (collapse) collapse.addEventListener('click', function () { self.sidebarCollapsed = !self.sidebarCollapsed; writeStorage('rr-sidebar-collapsed', self.sidebarCollapsed ? '1' : '0'); app.classList.toggle('rr-sidebar-collapsed', self.sidebarCollapsed); });
    var mobile = this.root.querySelector('.rr-mobile-menu'); if (mobile) mobile.addEventListener('click', function () { app.classList.add('rr-sidebar-open'); });
    var sidebarScrim = this.root.querySelector('.rr-sidebar-scrim'); if (sidebarScrim) sidebarScrim.addEventListener('click', function () { app.classList.remove('rr-sidebar-open'); });
    var drawerScrim = this.root.querySelector('.rr-drawer-scrim'); if (drawerScrim) drawerScrim.addEventListener('click', function () { self.closeDrawer(); });
  };

  App.prototype.navigate = function (view) { this.state.view = view; if (view !== 'field') this.state.field = ''; this.updateUrl(); this.start(); };
  App.prototype.openField = function (fieldId) { this.state.view = 'field'; this.state.field = fieldId; this.state.tab = 'overview'; this.updateUrl(); this.start(); };

  App.prototype.showHome = function (firstRun) {
    var content = '<div class="rr-home"><section class="rr-home-hero"><div><span class="rr-kicker">Academic discovery workspace</span><h1>Research Radar</h1><p>Track research fields, discover new papers, and understand scholar communities.</p></div><button class="rr-button rr-button-primary" type="button" data-new-field>' + icon('plus') + 'Create Research Field</button></section>' +
      '<button class="rr-home-search" type="button" data-open-command>' + icon('search', 20) + '<span>Search papers, authors, research fields...</span><kbd>Ctrl K</kbd></button>' +
      (firstRun ? '<section class="rr-onboarding"><div class="rr-onboarding-mark">' + icon('network', 28) + '</div><h2>Build your first research radar</h2><p>Define a topic once. Research Radar will organize papers, researchers, and collaboration networks as the field evolves.</p><button class="rr-button rr-button-primary" type="button" data-new-field>' + icon('plus') + 'Create your first field</button></section>' : '<section class="rr-home-fields"><div class="rr-section-heading"><div><span class="rr-kicker">Workspace</span><h2>Research Fields</h2></div><span>' + this.fields.length + ' fields</span></div><div class="rr-field-cards">' + this.fields.map(fieldCard).join('') + '</div></section>') + '</div>';
    this.renderShell({ view: 'home', title: 'Home', content: content });
    this.bindHome();
  };

  App.prototype.bindHome = function () {
    var self = this;
    this.root.querySelectorAll('.rr-workspace [data-new-field]').forEach(function (button) { button.addEventListener('click', function () { self.openFieldDialog(); }); });
    this.root.querySelectorAll('.rr-workspace [data-open-command]').forEach(function (button) { button.addEventListener('click', function () { self.openCommandPalette(); }); });
    this.root.querySelectorAll('.rr-field-card[data-open-field]').forEach(function (card) { card.addEventListener('click', function (event) { if (event.target.closest('.rr-card-menu')) return; self.openField(card.dataset.openField); }); card.addEventListener('keydown', function (event) { if (event.key === 'Enter') self.openField(card.dataset.openField); }); });
    this.root.querySelectorAll('[data-card-action]').forEach(function (button) { button.addEventListener('click', function (event) { event.preventDefault(); event.stopPropagation(); self.handleFieldAction(button.dataset.cardAction, button.dataset.fieldId, button); }); });
  };

  App.prototype.showSearch = function () {
    var tabs = [['all','All'],['papers','Papers'],['authors','Authors']], self = this;
    var content = '<div class="rr-search-page"><header class="rr-page-header"><span class="rr-kicker">Local library</span><h1>Search</h1><p>Find papers and researchers across every research field.</p></header><label class="rr-search-page-input">' + icon('search', 22) + '<input type="search" data-global-search aria-label="Search papers, authors, and research fields" placeholder="Search papers, authors, research fields..." autocomplete="off"><button class="rr-icon-button" type="button" data-clear-search aria-label="Clear search" hidden>' + icon('x') + '</button></label><div class="rr-search-tabs" role="tablist">' + tabs.map(function (tab) { return '<button role="tab" data-search-tab="' + tab[0] + '" aria-selected="' + (tab[0] === self.state.searchTab) + '" class="' + (tab[0] === self.state.searchTab ? 'is-active' : '') + '">' + tab[1] + '</button>'; }).join('') + '</div><div class="rr-search-page-results"></div></div>';
    this.renderShell({ view: 'search', title: 'Search', content: content }); this.bindSearchPage();
  };

  App.prototype.bindSearchPage = function () {
    var self = this, input = this.root.querySelector('[data-global-search]'), target = this.root.querySelector('.rr-search-page-results'), clear = this.root.querySelector('[data-clear-search]'), recent = recentSearches();
    target.innerHTML = recent.length ? '<section class="rr-recent-searches"><h2>Recent searches</h2>' + recent.map(function (term) { return '<button type="button" data-recent-search="' + esc(term) + '">' + icon('refresh', 15) + esc(term) + '</button>'; }).join('') + '</section>' : '<div class="rr-search-welcome">' + icon('search', 26) + '<strong>Search your research library</strong><p>Results stay local and include every field you track.</p></div>';
    var run = debounce(function () { self.runSearchPage(input.value, target); }, 300);
    input.addEventListener('input', function () { clear.hidden = !input.value; run(); });
    input.addEventListener('keydown', function (event) { if (event.key === 'Enter') { event.preventDefault(); self.runSearchPage(input.value, target, true); } });
    clear.addEventListener('click', function () { input.value = ''; clear.hidden = true; input.focus(); self.runSearchPage('', target); });
    this.root.querySelectorAll('[data-search-tab]').forEach(function (button) { button.addEventListener('click', function () { self.state.searchTab = button.dataset.searchTab; self.updateUrl(); self.root.querySelectorAll('[data-search-tab]').forEach(function (item) { item.classList.toggle('is-active', item === button); item.setAttribute('aria-selected', item === button ? 'true' : 'false'); }); self.runSearchPage(input.value, target); }); });
    this.root.querySelectorAll('[data-recent-search]').forEach(function (button) { button.addEventListener('click', function () { input.value = button.dataset.recentSearch; clear.hidden = false; self.runSearchPage(input.value, target); }); }); input.focus();
  };

  App.prototype.runSearchPage = function (query, target, save) {
    var self = this; query = String(query || '').trim();
    if (!query) { target.innerHTML = '<div class="rr-search-welcome">' + icon('search', 26) + '<strong>Search your research library</strong><p>Try a paper title, author, or research field.</p></div>'; return Promise.resolve(); }
    if (save) saveRecentSearch(query); target.innerHTML = listSkeleton('paper', 4);
    return this.source.search(query).then(function (data) { var fields = self.fields.filter(function (field) { return (field.name + ' ' + (field.description || '')).toLowerCase().indexOf(query.toLowerCase()) >= 0; }); target.innerHTML = renderSearchResults(data, fields, query, self.state.searchTab); target.querySelectorAll('[data-open-field]').forEach(function (button) { button.addEventListener('click', function () { self.openField(button.dataset.openField); }); }); }).catch(function (error) { target.innerHTML = inlineError(error); });
  };

  App.prototype.showSettings = function () {
    var self = this;
    this.renderShell({ view: 'settings', title: 'Settings', content: '<div class="rr-settings-page"><header class="rr-page-header"><span class="rr-kicker">Workspace preferences</span><h1>Settings</h1><p>Application, discovery, and local data preferences.</p></header>' + settingsSkeleton() + '</div>' });
    if (!this.source.getSettings) return;
    this.source.getSettings().then(function (data) { var target = self.root.querySelector('.rr-settings-page'); if (target) target.innerHTML = '<header class="rr-page-header"><span class="rr-kicker">Workspace preferences</span><h1>Settings</h1><p>Application, discovery, and local data preferences.</p></header>' + renderSettings(data); }).catch(function (error) { var target = self.root.querySelector('.rr-settings-page'); if (target) target.insertAdjacentHTML('beforeend', inlineError(error)); });
  };

  App.prototype.showField = function () {
    if (!this.field) return this.showHome(false);
    if (!String(root.location.hash).includes('startYear=')) this.state = State.applyRange(this.state, this.state.range, this.field.max_year);
    var self = this;
    var content = '<div class="rr-field-view"><header class="rr-field-header"><div class="rr-field-title"><span class="rr-kicker">Research field</span><h1>' + esc(this.field.name) + '</h1><p>' + esc(this.field.description || 'A living map of papers, researchers, and collaborations in this field.') + '</p><div class="rr-field-meta"><span>' + Number(this.field.paper_count || 0).toLocaleString() + ' Papers</span><i>·</i><span>' + Number(this.field.author_count || 0).toLocaleString() + ' Authors</span>' + (this.field.collaboration_count != null ? '<i>·</i><span>' + Number(this.field.collaboration_count).toLocaleString() + ' Collaborations</span>' : '') + '</div></div><div class="rr-field-actions">' + statusPill(this.field.sync_status) + '<button class="rr-button rr-button-secondary rr-sync-now" type="button"' + (this.field.sync_status === 'running' ? ' disabled' : '') + '>' + icon('refresh') + (this.field.sync_status === 'running' ? 'Updating' : 'Sync Now') + '</button><details class="rr-overflow-menu"><summary aria-label="Field actions">' + icon('more') + '</summary><div><button data-field-action="edit">Edit field</button><button data-field-action="disable">' + (this.field.enabled === false ? 'Enable field' : 'Disable field') + '</button></div></details></div></header>' +
      (this.field.sync_status === 'running' ? renderSetupProgress() : '') + fieldNotice(this.field) + '<div class="rr-field-toolbar"><nav class="rr-tabs" role="tablist" aria-label="Field sections">' + [['overview','Overview'],['papers','Papers'],['authors','Authors'],['graph','Scholar Graph']].map(function (tab) { return '<button role="tab" data-tab="' + tab[0] + '" aria-selected="' + (self.state.tab === tab[0]) + '" class="' + (self.state.tab === tab[0] ? 'is-active' : '') + '">' + tab[1] + '</button>'; }).join('') + '</nav><div class="rr-time-range" role="group" aria-label="Time range">' + ['1y','3y','5y'].map(function (range) { return '<button data-range="' + range + '" class="' + (self.state.range === range ? 'is-active' : '') + '">' + range.toUpperCase() + '</button>'; }).join('') + '</div></div><section class="rr-content" aria-live="polite">' + tabSkeleton(this.state.tab) + '</section></div>';
    this.renderShell({ view: 'field', title: this.field.name, content: content }); this.bindField();
    if (this.field.sync_status === 'running' && this.field.latest_sync_run_id) this.watchSync(this.field.latest_sync_run_id);
    return this.loadTab();
  };

  App.prototype.bindField = function () {
    var self = this, sync = this.root.querySelector('.rr-sync-now'); if (sync) sync.addEventListener('click', function () { self.startSync(sync); });
    this.root.querySelectorAll('[data-field-action]').forEach(function (button) { button.addEventListener('click', function () { self.handleFieldAction(button.dataset.fieldAction, self.field.id, button); }); });
    this.root.querySelectorAll('[data-tab]').forEach(function (button) { button.addEventListener('click', function () { self.state.tab = button.dataset.tab; self.updateUrl(); self.showField(); }); });
    this.root.querySelectorAll('[data-range]').forEach(function (button) { button.addEventListener('click', function () { self.state = State.applyRange(self.state, button.dataset.range, self.field.max_year); self.updateUrl(); self.showField(); }); });
    this.root.querySelectorAll('.rr-fix-field').forEach(function (button) { button.addEventListener('click', function () { self.openFieldDialog(self.field); }); });
  };

  App.prototype.loadTab = function () {
    if (this.graph) { this.graph.destroy(); this.graph = null; }
    var self = this, content = this.root.querySelector('.rr-content'), query = State.queryForTab(this.state), promise;
    var tab = this.state.tab, fieldId = this.field.id, requestId = (this.tabLoadId || 0) + 1;
    this.tabLoadId = requestId;
    if (!content) return Promise.resolve(); content.innerHTML = tabSkeleton(tab);
    if (tab === 'papers') promise = this.source.getFieldPapers(fieldId, query);
    else if (tab === 'authors') promise = this.source.getFieldAuthors(fieldId, query);
    else if (tab === 'graph') promise = this.source.getScholarGraph(fieldId, query);
    else promise = this.source.getFieldBrief ? Promise.all([this.source.getFieldOverview(this.field.id, query), this.source.getFieldBrief(this.field.id, {})]).then(function (items) { return Object.assign({}, items[0], { brief: items[1] }); }) : this.source.getFieldOverview(this.field.id, query);
    return promise.then(function (data) {
      if (requestId !== self.tabLoadId || self.state.tab !== tab || !self.field || self.field.id !== fieldId) return;
      self.renderTab(data);
    }).catch(function (error) {
      if (requestId === self.tabLoadId && self.state.tab === tab) content.innerHTML = inlineError(error);
    });
  };

  App.prototype.renderTab = function (data) {
    var content = this.root.querySelector('.rr-content'), self = this; if (!content) return;
    if (this.state.tab === 'papers') content.innerHTML = root.ResearchRadarPapers.render(data, this.state);
    else if (this.state.tab === 'authors') content.innerHTML = root.ResearchRadarAuthors.render(data, this.state);
    else if (this.state.tab === 'graph') {
      if (!data.nodes || !data.nodes.length) content.innerHTML = '<div class="rr-empty-message rr-graph-empty">' + icon('network', 28) + '<strong>No collaborations yet</strong><p>They will appear as more papers are discovered.</p></div>';
      else { content.innerHTML = root.ResearchRadarGraph.renderToolbar(this.state, data.total_nodes, data.nodes.length) + '<div class="rr-graph-stage"><div class="rr-graph" aria-label="Scholar collaboration network"></div><div class="rr-graph-rendering"><i class="rr-spinner"></i><span>Building research network</span></div></div>'; try { this.graph = root.ResearchRadarGraph.mount(content.querySelector('.rr-graph'), data, { onAuthor: function (id) { self.openAuthor(id); }, onCollaboration: function (a, b) { self.openCollaboration(a, b); }, onBackground: function () { self.closeDrawer(); } }); content.querySelector('.rr-graph-rendering').remove(); } catch (error) { content.innerHTML = inlineError(error); return; } }
    } else { content.innerHTML = root.ResearchRadarOverview.render(data); this.field.paper_count = data.paper_count; this.field.author_count = data.author_count; this.field.collaboration_count = data.collaboration_count; var meta = this.root.querySelector('.rr-field-meta'); if (meta) meta.innerHTML = '<span>' + Number(data.paper_count || 0).toLocaleString() + ' Papers</span><i>·</i><span>' + Number(data.author_count || 0).toLocaleString() + ' Authors</span><i>·</i><span>' + Number(data.collaboration_count || 0).toLocaleString() + ' Collaborations</span>'; }
    this.bindContent();
  };

  App.prototype.bindContent = function () {
    var self = this, update = debounce(function () { self.updateUrl(); self.loadTab(); }, 300);
    this.root.querySelectorAll('.rr-content [data-state]').forEach(function (input) { input.addEventListener(input.type === 'search' || input.tagName === 'INPUT' ? 'input' : 'change', function () { var value = input.type === 'checkbox' ? input.checked : input.value; if (input.type === 'number') value = Number(value); self.state[input.dataset.state] = value; update(); }); });
    this.root.querySelectorAll('.rr-author-open').forEach(function (button) { button.addEventListener('click', function () { self.openAuthor(button.dataset.authorId); }); });
    this.root.querySelectorAll('[data-toggle-filters]').forEach(function (button) { button.addEventListener('click', function () { var popover = button.parentElement.querySelector('[data-filter-popover]'); if (popover) popover.hidden = !popover.hidden; }); });
    this.root.querySelectorAll('[data-clear-state]').forEach(function (button) { button.addEventListener('click', function () { var key = button.dataset.clearState; self.state[key] = key === 'minimumRelevance' ? 0 : ''; self.updateUrl(); self.loadTab(); }); });
    this.root.querySelectorAll('[data-save-paper]').forEach(function (button) { button.addEventListener('click', function () { button.classList.toggle('is-saved'); self.toast(button.classList.contains('is-saved') ? 'Paper saved locally' : 'Paper removed from saved items', 'success'); }); }); this.bindGraphActions();
  };

  App.prototype.bindGraphActions = function () {
    var self = this; this.root.querySelectorAll('[data-graph-action]').forEach(function (button) { button.addEventListener('click', function () { var actions = { fit: 'fit', reset: 'reset', 'zoom-in': 'zoomIn', 'zoom-out': 'zoomOut' }; if (self.graph) self.graph[actions[button.dataset.graphAction]](); }); });
    var search = this.root.querySelector('[data-state="graphSearch"]'); if (search) search.addEventListener('change', function () { var term = search.value.trim().toLowerCase(); if (!term || !self.graph) return; var match = self.graph.cy.nodes().filter(function (node) { return String(node.data('name')).toLowerCase().indexOf(term) >= 0; })[0]; if (match) { self.graph.selectAuthor(match.id()); self.openAuthor(match.id()); } });
  };

  App.prototype.openFieldDialog = function (field) {
    var editing = !!field;
    this.openDialog('<div class="rr-modal-header"><div><span class="rr-kicker">' + (editing ? 'Field settings' : 'New radar') + '</span><h2 id="rr-dialog-title">' + (editing ? 'Edit Research Field' : 'Create Research Field') + '</h2><p>' + (editing ? 'Update how this field is described and monitored.' : 'Start with a clear topic. Search planning happens automatically in the background.') + '</p></div><button class="rr-icon-button" type="button" data-close-dialog aria-label="Close dialog">' + icon('x') + '</button></div>' + fieldForm(field), 'rr-dialog-title'); this.bindFieldForm(field);
  };

  App.prototype.bindFieldForm = function (field) {
    var self = this, form = this.root.querySelector('.rr-field-form'), status = form.querySelector('.rr-form-status');
    form.addEventListener('submit', function (event) {
      event.preventDefault(); var submit = form.querySelector('[type="submit"]'); submit.disabled = true; status.textContent = field ? 'Saving field...' : 'Creating field...';
      var data = new FormData(form), payload = { name: data.get('name'), description: data.get('description'), core_keywords: splitLines(data.get('core_keywords')), optional_keywords: splitLines(data.get('optional_keywords')), excluded_keywords: splitLines(data.get('excluded_keywords')), intent_queries: splitLines(data.get('intent_queries')), seed_papers: splitLines(data.get('seed_papers')), seed_authors: splitLines(data.get('seed_authors')) };
      if (field) {
        payload.enabled = data.get('enabled') === 'on'; payload.auto_sync = data.get('auto_sync') === 'on'; payload.sync_frequency = data.get('sync_frequency');
        self.source.updateResearchField(field.id, payload).then(function (updated) { self.closeDialog(); self.field = updated; self.state.field = updated.id; self.toast('Research field updated', 'success'); self.start(); }).catch(function (error) { submit.disabled = false; status.textContent = error.message || String(error); });
      } else {
        self.source.createResearchField(payload).then(function (created) { self.closeDialog(); self.fields.push(created); self.field = created; self.state.view = 'field'; self.state.field = created.id; self.state.tab = 'overview'; self.updateUrl(); self.toast('Research field created', 'success'); created.sync_status = 'running'; self.showField(); return self.source.startFieldSync(created.id, { years: 3, max_pages: 1 }); }).then(function (run) { self.field.latest_sync_run_id = run.run_id; self.watchSync(run.run_id); self.toast('Discovery started in the background', 'info'); }).catch(function (error) { submit.disabled = false; status.textContent = error.message || String(error); self.toast('Field setup could not start', 'danger'); });
      }
    });
  };

  App.prototype.handleFieldAction = function (action, fieldId, button) {
    var self = this, field = this.fields.find(function (item) { return item.id === fieldId; }) || this.field; if (!field) return;
    if (action === 'edit') return this.openFieldDialog(field);
    if (action === 'sync') { button.disabled = true; return this.source.startFieldSync(field.id, { years: 1, max_pages: 1 }).then(function (run) { field.sync_status = 'running'; field.latest_sync_run_id = run.run_id; self.watchSync(run.run_id, button); self.toast('Sync started', 'info'); if (self.field && self.field.id === field.id) self.showField(); }).catch(function (error) { button.disabled = false; self.toast(error.message || 'Sync failed', 'danger'); }); }
    if (action === 'disable') { var enabling = field.enabled === false; if (enabling) return this.source.updateResearchField(field.id, { enabled: true }).then(function () { self.toast('Research field enabled', 'success'); self.start(); }); this.openConfirm('Disable “' + field.name + '”?', 'Automatic updates will stop, but existing papers and researcher data will remain available.', 'Disable field', function () { self.source.updateResearchField(field.id, { enabled: false }).then(function () { self.closeDialog(); self.toast('Research field disabled', 'success'); self.start(); }).catch(function (error) { self.toast(error.message || 'Could not disable field', 'danger'); }); }); }
  };

  App.prototype.startSync = function (button) { var self = this; button.disabled = true; this.source.startFieldSync(this.field.id, { years: 1, max_pages: 1 }).then(function (run) { self.field.sync_status = 'running'; self.field.latest_sync_run_id = run.run_id; self.showField(); self.watchSync(run.run_id); self.toast('Sync started', 'info'); }).catch(function (error) { button.disabled = false; self.toast(error.message || 'Sync failed', 'danger'); }); };
  App.prototype.watchSync = function (runId, button) { if (!runId || !this.source.getSyncRun) return; if (this.syncPollRunId === runId) { if (button) this.syncPollButton = button; return; } this.stopSyncWatcher(false); this.syncPollRunId = runId; this.syncPollButton = button || null; this.pollSync(runId, 0); };
  App.prototype.pollSync = function (runId, count) { var self = this; if (this.syncPollRunId !== runId) return; if (count > 240) { this.stopSyncWatcher(true); return; } this.source.getSyncRun(runId).then(function (run) { if (self.syncPollRunId !== runId) return; self.updateSyncProgress(run); if (run.status === 'succeeded' || run.status === 'partial' || run.status === 'failed') { self.stopSyncWatcher(true); if (run.status === 'failed') self.toast(syncErrorMessage(run), 'danger'); else self.toast((run.papers_inserted || 0) + ' papers discovered', 'success'); self.start(); return; } self.syncPollTimer = setTimeout(function () { self.pollSync(runId, count + 1); }, 1500); }).catch(function () { self.stopSyncWatcher(true); self.toast('Could not read sync progress', 'danger'); }); };
  App.prototype.updateSyncProgress = function (run) { var target = this.root.querySelector('[data-setup-progress]'); if (target) target.outerHTML = renderSetupProgress(run); };
  App.prototype.stopSyncWatcher = function (resetButton) { if (this.syncPollTimer) clearTimeout(this.syncPollTimer); if (resetButton && this.syncPollButton) this.syncPollButton.disabled = false; this.syncPollTimer = null; this.syncPollRunId = null; this.syncPollButton = null; };

  App.prototype.openAuthor = function (id) { var self = this, request = ++this.drawerRequest; this.openDrawer(drawerSkeleton()); this.source.getAuthorDetail(this.field.id, id, State.queryForTab(this.state)).then(function (data) { if (request !== self.drawerRequest) return; self.openDrawer(root.ResearchRadarDetailPanel.renderAuthor(data)); self.bindDrawer(); }).catch(function (error) { self.openDrawer(inlineError(error)); }); };
  App.prototype.openCollaboration = function (a, b) { var self = this, request = ++this.drawerRequest; this.openDrawer(drawerSkeleton()); this.source.getCollaborationDetail(this.field.id, a, b, State.queryForTab(this.state)).then(function (data) { if (request !== self.drawerRequest) return; self.openDrawer(root.ResearchRadarDetailPanel.renderCollaboration(data)); self.bindDrawer(); }).catch(function (error) { self.openDrawer(inlineError(error)); }); };
  App.prototype.openDrawer = function (html) { var drawer = this.root.querySelector('.rr-drawer'), app = this.root.querySelector('.rr-app'); if (!drawer || !app) return; drawer.innerHTML = html; drawer.setAttribute('aria-hidden', 'false'); app.classList.add('rr-drawer-open'); };
  App.prototype.closeDrawer = function () { this.drawerRequest += 1; var drawer = this.root.querySelector('.rr-drawer'), app = this.root.querySelector('.rr-app'); if (drawer) drawer.setAttribute('aria-hidden', 'true'); if (app) app.classList.remove('rr-drawer-open'); };
  App.prototype.bindDrawer = function () { var self = this, close = this.root.querySelector('.rr-drawer-close'); if (close) close.addEventListener('click', function () { self.closeDrawer(); }); this.root.querySelectorAll('.rr-drawer .rr-author-open').forEach(function (button) { button.addEventListener('click', function () { if (self.graph) self.graph.selectAuthor(button.dataset.authorId); self.openAuthor(button.dataset.authorId); }); }); };

  App.prototype.openCommandPalette = function () {
    var self = this;
    this.openDialog('<div class="rr-command"><label class="rr-command-input">' + icon('search', 20) + '<input id="rr-command-input" type="search" placeholder="Search Research Radar" autocomplete="off"><kbd>Esc</kbd></label><div class="rr-command-results" role="listbox">' + commandDefaults(this.fields) + '</div></div>', 'rr-command-input', true);
    var input = this.root.querySelector('#rr-command-input'), target = this.root.querySelector('.rr-command-results');
    var search = debounce(function () { var query = input.value.trim(); if (!query) { target.innerHTML = commandDefaults(self.fields); self.bindCommandActions(); return; } target.innerHTML = '<div class="rr-command-loading">Searching...</div>'; self.source.search(query).then(function (data) { target.innerHTML = commandResults(data, self.fields, query); self.bindCommandActions(); }); }, 250);
    input.addEventListener('input', search); this.bindCommandActions(); input.focus();
  };
  App.prototype.bindCommandActions = function () { var self = this; this.root.querySelectorAll('[data-command]').forEach(function (button) { button.addEventListener('click', function () { var command = button.dataset.command; self.closeDialog(); if (command === 'new') self.openFieldDialog(); else self.navigate(command); }); }); this.root.querySelectorAll('.rr-command-results [data-open-field]').forEach(function (button) { button.addEventListener('click', function () { self.closeDialog(); self.openField(button.dataset.openField); }); }); };
  App.prototype.openDialog = function (html, labelledBy, command) { var overlay = this.root.querySelector('.rr-overlay-root'); if (!overlay) return; overlay.innerHTML = '<div class="rr-modal-backdrop" data-close-dialog></div><section class="rr-modal' + (command ? ' rr-command-modal' : '') + '" role="dialog" aria-modal="true" aria-labelledby="' + esc(labelledBy || 'rr-dialog-title') + '">' + html + '</section>'; this.bindDialog(); };
  App.prototype.bindDialog = function () { var self = this, overlay = this.root.querySelector('.rr-overlay-root'), modal = overlay && overlay.querySelector('.rr-modal'); if (!modal) return; overlay.querySelectorAll('[data-close-dialog]').forEach(function (button) { button.addEventListener('click', function () { self.closeDialog(); }); }); var focusable = modal.querySelector('input,button,textarea,select,summary'); if (focusable) focusable.focus(); modal.addEventListener('keydown', function (event) { if (event.key !== 'Tab') return; var items = Array.from(modal.querySelectorAll('button:not([disabled]),input:not([disabled]),textarea:not([disabled]),select:not([disabled]),summary')).filter(function (item) { return item.offsetParent !== null; }); if (!items.length) return; var first = items[0], last = items[items.length - 1]; if (event.shiftKey && root.document.activeElement === first) { event.preventDefault(); last.focus(); } else if (!event.shiftKey && root.document.activeElement === last) { event.preventDefault(); first.focus(); } }); };
  App.prototype.closeDialog = function () { var overlay = this.root.querySelector('.rr-overlay-root'); if (overlay) overlay.innerHTML = ''; };
  App.prototype.openConfirm = function (title, message, actionLabel, onConfirm) { this.openDialog('<div class="rr-modal-header"><div><span class="rr-kicker rr-kicker-danger">Confirm action</span><h2 id="rr-dialog-title">' + esc(title) + '</h2><p>' + esc(message) + '</p></div><button class="rr-icon-button" data-close-dialog aria-label="Close dialog">' + icon('x') + '</button></div><div class="rr-modal-actions"><button class="rr-button rr-button-secondary" data-close-dialog>Cancel</button><button class="rr-button rr-button-danger" data-confirm-action>' + esc(actionLabel) + '</button></div>', 'rr-dialog-title'); var confirm = this.root.querySelector('[data-confirm-action]'); if (confirm) confirm.addEventListener('click', onConfirm); };

  App.prototype.toast = function (message, type) { var region = this.root.querySelector('.rr-toast-region'); if (!region) return; var toast = root.document.createElement('div'); toast.className = 'rr-toast rr-toast-' + (type || 'info'); toast.innerHTML = (type === 'success' ? icon('check') : type === 'danger' ? icon('alert') : icon('refresh')) + '<span>' + esc(message) + '</span><button class="rr-icon-button" aria-label="Dismiss notification">' + icon('x', 15) + '</button>'; region.appendChild(toast); requestAnimationFrame(function () { toast.classList.add('is-visible'); }); var close = function () { toast.classList.remove('is-visible'); setTimeout(function () { toast.remove(); }, 180); }; toast.querySelector('button').addEventListener('click', close); setTimeout(close, 4200); };
  App.prototype.toggleTheme = function () { this.theme = this.theme === 'dark' ? 'light' : 'dark'; writeStorage('rr-theme', this.theme); this.start(); };
  App.prototype.onGlobalKeydown = function (event) { if (!isRoute()) return; if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); this.openCommandPalette(); } else if (event.key === 'Escape') { if (this.root.querySelector('.rr-modal')) this.closeDialog(); else if (this.root.querySelector('.rr-app.rr-drawer-open')) this.closeDrawer(); else { var app = this.root.querySelector('.rr-app'); if (app) app.classList.remove('rr-sidebar-open'); } } };
  App.prototype.updateUrl = function () { var next = State.serialize(this.state); if (root.location.hash !== next) root.history.replaceState(null, '', next); };
  App.prototype.renderFatal = function (error) { this.root.innerHTML = '<div class="rr-fatal"><strong>Research Radar could not load</strong><p>' + esc(error && error.message || error) + '</p><button type="button">Try again</button></div>'; var self = this; this.root.querySelector('button').addEventListener('click', function () { self.start(); }); };
  App.prototype.destroy = function () { this.stopSyncWatcher(false); if (this.graph) this.graph.destroy(); root.document.removeEventListener('keydown', this.keydownHandler); };

  function fieldForm(field) {
    field = field || {};
    return '<form class="rr-field-form"><div class="rr-form-grid"><label>Field name<input name="name" required value="' + esc(field.name || '') + '" placeholder="Incomplete Multimodal Recommendation"></label><label>Description<textarea name="description" rows="3" placeholder="What should this field track?">' + esc(field.description || '') + '</textarea></label><label>Core keywords<textarea name="core_keywords" rows="2" placeholder="multimodal recommendation, missing modality">' + esc((field.core_keywords || []).join('\n')) + '</textarea></label></div><details class="rr-advanced"><summary>Advanced options</summary><div class="rr-advanced-grid"><label>Optional keywords<textarea name="optional_keywords" rows="2">' + esc((field.optional_keywords || []).join('\n')) + '</textarea></label><label>Excluded keywords<textarea name="excluded_keywords" rows="2">' + esc((field.excluded_keywords || []).join('\n')) + '</textarea></label><label>Intent queries<textarea name="intent_queries" rows="2">' + esc((field.intent_queries || []).join('\n')) + '</textarea></label><label>Seed papers<textarea name="seed_papers" rows="2">' + esc((field.seed_papers || []).join('\n')) + '</textarea></label><label>Seed authors<textarea name="seed_authors" rows="2">' + esc((field.seed_authors || []).join('\n')) + '</textarea></label></div></details>' + (field.id ? '<div class="rr-form-preferences"><label class="rr-check"><input type="checkbox" name="enabled"' + (field.enabled === false ? '' : ' checked') + '> Field enabled</label><label class="rr-check"><input type="checkbox" name="auto_sync"' + (field.auto_sync === false ? '' : ' checked') + '> Automatic updates</label><label>Frequency<select name="sync_frequency"><option value="daily"' + (field.sync_frequency !== 'weekly' && field.sync_frequency !== 'hourly' ? ' selected' : '') + '>Daily</option><option value="hourly"' + (field.sync_frequency === 'hourly' ? ' selected' : '') + '>Hourly</option><option value="weekly"' + (field.sync_frequency === 'weekly' ? ' selected' : '') + '>Weekly</option></select></label></div>' : '') + '<div class="rr-modal-actions"><small class="rr-form-status"></small><button class="rr-button rr-button-secondary" type="button" data-close-dialog>Cancel</button><button class="rr-button rr-button-primary" type="submit">' + (field.id ? 'Save changes' : 'Create Field') + '</button></div></form>';
  }

  function fieldCard(field) { var running = field.sync_status === 'running'; return '<article class="rr-field-card' + (field.enabled === false ? ' is-disabled' : '') + '" data-open-field="' + esc(field.id) + '" tabindex="0"><div class="rr-card-top"><span class="rr-field-symbol">' + esc(String(field.name || 'R').charAt(0).toUpperCase()) + '</span><details class="rr-card-menu"><summary aria-label="Field actions">' + icon('more') + '</summary><div><button data-card-action="sync" data-field-id="' + esc(field.id) + '"' + (running ? ' disabled' : '') + '>' + icon('refresh', 15) + 'Sync now</button><button data-card-action="edit" data-field-id="' + esc(field.id) + '">' + icon('settings', 15) + 'Edit field</button><button data-card-action="disable" data-field-id="' + esc(field.id) + '">' + icon('alert', 15) + (field.enabled === false ? 'Enable field' : 'Disable field') + '</button></div></details></div><h3>' + esc(field.name) + '</h3><p>' + esc(field.description || 'A monitored academic research field.') + '</p><div class="rr-card-metrics"><span><strong>' + Number(field.paper_count || 0).toLocaleString() + '</strong>Papers</span><span><strong>' + Number(field.author_count || 0).toLocaleString() + '</strong>Authors</span></div><footer>' + statusPill(field.sync_status) + '<span>' + esc(relativeTime(field.last_sync_at || field.updated_at)) + '</span>' + (field.new_papers_since_last_visit ? '<b>+' + esc(field.new_papers_since_last_visit) + ' new</b>' : '') + '</footer></article>'; }
  function renderSetupProgress(run) { var checkpoint = run && run.checkpoint || {}, current = 0; if (checkpoint.stage === 'searching') current = 2; if (Number(run && run.papers_inserted || 0) > 0) current = 3; var steps = ['Understanding your research field', 'Building search strategy', 'Discovering papers', 'Analyzing authors and collaborations']; return '<details class="rr-setup-progress" data-setup-progress open><summary><span><i class="rr-spinner"></i><strong>Setting up your research radar</strong></span><small>Working in the background ' + icon('chevron', 15) + '</small></summary><div class="rr-progress-steps">' + steps.map(function (step, index) { var state = index < current ? 'complete' : index === current ? 'current' : 'pending'; return '<div class="rr-progress-step is-' + state + '"><span>' + (state === 'complete' ? icon('check', 14) : state === 'current' ? '<i class="rr-spinner"></i>' : '') + '</span><p>' + step + '</p></div>'; }).join('') + '</div></details>'; }
  function fieldNotice(field) { var hasSearch = (field.core_keywords || []).length || (field.intent_queries || []).length; if (field.sync_status === 'failed') return '<section class="rr-field-notice rr-field-warning"><div>' + icon('alert') + '</div><span><strong>Discovery needs attention</strong><p>' + (hasSearch ? 'Review this field or try syncing again.' : 'Add a few core keywords to improve discovery.') + '</p></span><button class="rr-button rr-button-secondary rr-fix-field">Edit field</button></section>'; if (!hasSearch && field.sync_status !== 'running') return '<section class="rr-field-notice"><div>' + icon('alert') + '</div><span><strong>Search definition is broad</strong><p>Add core keywords to make future discovery more precise.</p></span><button class="rr-button rr-button-secondary rr-fix-field">Add keywords</button></section>'; return ''; }
  function statusPill(status) { var state = status === 'running' ? 'updating' : status === 'failed' ? 'attention' : 'ready', label = state === 'updating' ? 'Updating' : state === 'attention' ? 'Needs attention' : 'Up to date'; return '<span class="rr-status rr-status-' + state + '"><i></i>' + label + '</span>'; }
  function syncTopStatus(field, view) { return view !== 'field' || !field ? '' : '<span class="rr-top-sync">' + statusPill(field.sync_status) + '</span>'; }
  function relativeTime(value) { if (!value) return 'Not updated yet'; var date = new Date(value), delta = Date.now() - date.getTime(); if (isNaN(date.getTime())) return String(value); var minutes = Math.max(1, Math.floor(delta / 60000)); if (minutes < 60) return 'Updated ' + minutes + 'm ago'; var hours = Math.floor(minutes / 60); if (hours < 24) return 'Updated ' + hours + 'h ago'; return 'Updated ' + Math.floor(hours / 24) + 'd ago'; }
  function syncErrorMessage(run) { return run && run.error_summary && run.error_summary.message || 'Discovery could not finish. Review the field and try again.'; }

  function renderSearchResults(data, fields, query, tab) { var papers = data && data.papers && data.papers.items || [], authors = data && data.authors && data.authors.items || []; if (!papers.length && !authors.length && !fields.length) return '<div class="rr-empty-message"><strong>No results for “' + esc(query) + '”</strong><p>Try another title, author, or research field.</p></div>'; var html = ''; if (tab === 'all' && fields.length) html += '<section class="rr-search-group"><h2>Research Fields</h2>' + fields.map(function (field) { return '<button class="rr-search-field-result" data-open-field="' + esc(field.id) + '"><span class="rr-field-symbol">' + esc(field.name.charAt(0).toUpperCase()) + '</span><span><strong>' + esc(field.name) + '</strong><small>' + esc(field.description || 'Research field') + '</small></span>' + icon('chevron') + '</button>'; }).join('') + '</section>'; if ((tab === 'all' || tab === 'papers') && papers.length) html += '<section class="rr-search-group"><h2>Papers <span>' + papers.length + '</span></h2>' + papers.map(function (paper) { return '<article class="rr-search-result"><span class="rr-result-icon">' + icon('file') + '</span><div><strong>' + esc(paper.title) + '</strong><small>' + esc((paper.authors || []).slice(0, 3).map(function (author) { return author.name; }).join(', ')) + '</small><p>' + esc(paper.snippet || '') + '</p><em>' + esc([paper.year, paper.venue].filter(Boolean).join(' · ')) + '</em></div></article>'; }).join('') + '</section>'; if ((tab === 'all' || tab === 'authors') && authors.length) html += '<section class="rr-search-group"><h2>Authors <span>' + authors.length + '</span></h2>' + authors.map(function (author) { return '<article class="rr-search-result"><span class="rr-avatar">' + esc(root.ResearchRadarAuthors.initials(author.name)) + '</span><div><strong>' + esc(author.name) + '</strong><small>' + esc(author.primary_institution || 'Institution unavailable') + '</small><em>' + esc(author.field_paper_count || 0) + ' field papers · ' + esc(author.works_count || 0) + ' works</em></div></article>'; }).join('') + '</section>'; return html || '<div class="rr-empty-message"><strong>No ' + esc(tab) + ' found</strong><p>Try a broader search.</p></div>'; }
  function commandDefaults(fields) { return '<div class="rr-command-group"><span>Navigate</span><button data-command="search">' + icon('search') + '<strong>Search Research Radar</strong></button><button data-command="new">' + icon('plus') + '<strong>Create New Field</strong></button><button data-command="settings">' + icon('settings') + '<strong>Go to Settings</strong></button></div><div class="rr-command-group"><span>Research Fields</span>' + fields.slice(0, 8).map(function (field) { return '<button data-open-field="' + esc(field.id) + '"><span class="rr-field-dot"></span><strong>' + esc(field.name) + '</strong></button>'; }).join('') + '</div>'; }
  function commandResults(data, fields, query) { var matchFields = fields.filter(function (field) { return field.name.toLowerCase().indexOf(query.toLowerCase()) >= 0; }), papers = data && data.papers && data.papers.items || [], authors = data && data.authors && data.authors.items || []; return '<div class="rr-command-group"><span>Fields</span>' + matchFields.slice(0, 4).map(function (field) { return '<button data-open-field="' + esc(field.id) + '"><span class="rr-field-dot"></span><strong>' + esc(field.name) + '</strong></button>'; }).join('') + '</div><div class="rr-command-group"><span>Papers</span>' + papers.slice(0, 4).map(function (paper) { return '<button><span>' + icon('file') + '</span><strong>' + esc(paper.title) + '</strong></button>'; }).join('') + '</div><div class="rr-command-group"><span>Authors</span>' + authors.slice(0, 4).map(function (author) { return '<button><span>' + icon('users') + '</span><strong>' + esc(author.name) + '</strong></button>'; }).join('') + '</div>'; }
  function renderSettings(data) { return '<div class="rr-settings-layout"><section class="rr-settings-section"><h2>Application</h2><div class="rr-setting-row"><span><strong>Theme</strong><small>Use the theme control in the top bar.</small></span><b>System aware</b></div><div class="rr-setting-row"><span><strong>Open browser on start</strong><small>Launch Research Radar when the local app starts.</small></span><b>' + (data.application && data.application.open_browser ? 'On' : 'Off') + '</b></div></section><section class="rr-settings-section"><h2>Discovery</h2><div class="rr-setting-row"><span><strong>Default history</strong><small>Initial period used for new research fields.</small></span><b>' + esc(data.sync && data.sync.historical_years) + ' years</b></div><div class="rr-setting-row"><span><strong>Academic discovery</strong><small>Online paper discovery connection.</small></span><b>' + (data.openalex && data.openalex.api_key_configured ? 'Connected' : 'Ready') + '</b></div></section><section class="rr-settings-section"><h2>Local Data</h2><div class="rr-setting-row"><span><strong>Storage</strong><small>Your research library is stored on this computer.</small></span><b>Local</b></div></section><details class="rr-developer-info"><summary>Developer information</summary><dl><div><dt>Port</dt><dd>' + esc(data.application && data.application.port) + '</dd></div><div><dt>Local planning</dt><dd>' + esc(data.local_ai && data.local_ai.enabled ? data.local_ai.provider + ' · ' + data.local_ai.model : 'Off') + '</dd></div><div><dt>Storage path</dt><dd>' + esc(data.storage && data.storage.database_path) + '</dd></div></dl></details></div>'; }
  function saveRecentSearch(query) { var items = recentSearches().filter(function (item) { return item !== query; }); items.unshift(query); writeStorage('rr-recent-searches', JSON.stringify(items.slice(0, 6))); }
  function recentSearches() { try { return JSON.parse(readStorage('rr-recent-searches', '[]')) || []; } catch (error) { return []; } }
  function inlineError(error) { return '<div class="rr-error"><strong>Something went wrong</strong><p>' + esc(error && error.message || error) + '</p></div>'; }
  function appSkeleton() { return '<div class="rr-app-loading"><i class="rr-spinner"></i><span>Opening Research Radar</span></div>'; }
  function skeletonPage() { return '<div class="rr-page-skeleton"><span></span><span></span><span></span></div>'; }
  function tabSkeleton(tab) { if (tab === 'graph') return '<div class="rr-graph-skeleton"><i class="rr-spinner"></i><span>Preparing research network</span></div>'; if (tab === 'overview') return '<div class="rr-metric-skeleton">' + '<span></span>'.repeat(4) + '</div><div class="rr-panel-skeleton"></div>'; return listSkeleton(tab === 'authors' ? 'author' : 'paper', 6); }
  function listSkeleton(type, count) { return '<div class="rr-list-skeleton rr-list-skeleton-' + type + '">' + '<span></span>'.repeat(count || 5) + '</div>'; }
  function settingsSkeleton() { return '<div class="rr-settings-skeleton">' + '<span></span>'.repeat(3) + '</div>'; }
  function drawerSkeleton() { return '<div class="rr-drawer-skeleton"><span></span><span></span><span></span></div>'; }

  function mount() { root.document.body.classList.toggle('rr-page', isRoute()); var chat = root.document.getElementById('paper-chat-container'); if (chat) { if (isRoute()) chat.style.setProperty('display', 'none', 'important'); else chat.style.removeProperty('display'); } if (!isRoute()) return; var rootEl = root.document.getElementById('research-radar-root'); if (!rootEl) return; if (current) current.destroy(); current = new App(rootEl); current.start(); }
  root.$docsify = root.$docsify || {}; root.$docsify.plugins = (root.$docsify.plugins || []).concat(function (hook) { hook.doneEach(mount); });
  root.ResearchRadarApp = { App: App, mount: mount, isRoute: isRoute };
})(typeof window !== 'undefined' ? window : null);
