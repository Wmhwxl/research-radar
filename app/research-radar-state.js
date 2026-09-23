(function (root, factory) {
  var api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.ResearchRadarState = api;
})(typeof window !== 'undefined' ? window : globalThis, function () {
  'use strict';
  var TABS = ['overview', 'papers', 'authors', 'graph'];
  function defaults(maxYear) {
    var end = Number(maxYear) || new Date().getFullYear();
    return { view: 'home', tab: 'overview', range: '5y', startYear: end - 4, endYear: end, field: '', searchTab: 'all',
      paperSearch: '', paperVenue: '', paperAuthor: '', relevanceLabel: '', minimumRelevance: 0,
      paperSort: 'newest', authorSearch: '', institution: '', minimumPapers: 1,
      minimumCollaborations: 1, graphSearch: '', coreOnly: false, maxNodes: 500 };
  }
  function parseHash(hash, maxYear) {
    var state = defaults(maxYear);
    var query = String(hash || '').split('?')[1] || '';
    var params = new URLSearchParams(query);
    if (['home', 'search', 'settings', 'field'].indexOf(params.get('view')) >= 0) state.view = params.get('view');
    if (TABS.indexOf(params.get('tab')) >= 0) state.tab = params.get('tab');
    if (params.get('field')) { state.field = params.get('field'); if (!params.get('view')) state.view = 'field'; }
    if (['all', 'papers', 'authors'].indexOf(params.get('searchTab')) >= 0) state.searchTab = params.get('searchTab');
    if (['1y', '3y', '5y', 'custom'].indexOf(params.get('range')) >= 0) state.range = params.get('range');
    ['startYear', 'endYear', 'minimumPapers', 'minimumCollaborations', 'maxNodes'].forEach(function (key) {
      var value = params.get(key); if (value && /^\d+$/.test(value)) state[key] = Number(value);
    });
    if (params.get('maxNodes') === 'all') state.maxNodes = 'all';
    ['paperSearch', 'paperVenue', 'paperAuthor', 'relevanceLabel', 'paperSort', 'authorSearch', 'institution', 'graphSearch'].forEach(function (key) {
      if (params.get(key)) state[key] = params.get(key);
    });
    if (params.has('minimumRelevance')) state.minimumRelevance = Math.max(0, Math.min(1, Number(params.get('minimumRelevance')) || 0));
    state.coreOnly = params.get('coreOnly') === '1';
    if (state.startYear > state.endYear) { var swap = state.startYear; state.startYear = state.endYear; state.endYear = swap; }
    return state;
  }
  function serialize(state) {
    var params = new URLSearchParams();
    Object.keys(state).forEach(function (key) {
      var value = state[key];
      if (value === '' || value == null || value === false) return;
      params.set(key, value === true ? '1' : String(value));
    });
    return '#/research-radar/?' + params.toString();
  }
  function applyRange(state, range, maxYear) {
    var end = Number(maxYear) || state.endYear || new Date().getFullYear();
    var years = range === '1y' ? 1 : range === '3y' ? 3 : 5;
    return Object.assign({}, state, { range: range, startYear: range === 'custom' ? state.startYear : end - years + 1, endYear: range === 'custom' ? state.endYear : end });
  }
  function queryForTab(state) {
    var common = { startYear: state.startYear, endYear: state.endYear };
    if (state.tab === 'papers') return Object.assign(common, { search: state.paperSearch, venue: state.paperVenue,
      author: state.paperAuthor, relevanceLabel: state.relevanceLabel, minimumRelevance: state.minimumRelevance, sort: state.paperSort });
    if (state.tab === 'authors') return Object.assign(common, { search: state.authorSearch, institution: state.institution, minimumPapers: state.minimumPapers });
    if (state.tab === 'graph') return Object.assign(common, { search: state.graphSearch, minimumPapers: state.minimumPapers,
      minimumCollaborations: state.minimumCollaborations, coreOnly: state.coreOnly, maxNodes: state.maxNodes });
    return common;
  }
  return { TABS: TABS, defaults: defaults, parseHash: parseHash, serialize: serialize, applyRange: applyRange, queryForTab: queryForTab };
});
