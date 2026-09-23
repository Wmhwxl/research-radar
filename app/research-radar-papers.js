(function (root, factory) {
  var api = factory(); if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.ResearchRadarPapers = api;
})(typeof window !== 'undefined' ? window : globalThis, function () {
  'use strict';
  function esc(value) { return String(value == null ? '' : value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
  function safeUrl(value) { try { var u = new URL(String(value || '')); return /^https?:$/.test(u.protocol) ? u.href : ''; } catch (e) { return ''; } }
  function icon(name) { return typeof window !== 'undefined' && window.ResearchRadarIcons ? window.ResearchRadarIcons.icon(name, 17) : ''; }
  function filters(state) {
    var chips = [];
    if (state.paperVenue) chips.push(['paperVenue', 'Venue: ' + state.paperVenue]);
    if (state.paperAuthor) chips.push(['paperAuthor', 'Author: ' + state.paperAuthor]);
    if (state.relevanceLabel) chips.push(['relevanceLabel', state.relevanceLabel === 'core' ? 'Core only' : 'Related only']);
    if (Number(state.minimumRelevance) > 0) chips.push(['minimumRelevance', 'Relevance ≥ ' + state.minimumRelevance]);
    return '<div class="rr-list-toolbar"><label class="rr-toolbar-search">' + icon('search') + '<span class="rr-sr-only">Search papers</span><input data-state="paperSearch" type="search" placeholder="Search papers..." value="' + esc(state.paperSearch) + '"></label>' +
      '<div class="rr-toolbar-actions"><div class="rr-popover-wrap"><button class="rr-button rr-button-secondary" type="button" data-toggle-filters>' + icon('filter') + 'Filters' + (chips.length ? '<span class="rr-filter-count">' + chips.length + '</span>' : '') + '</button><div class="rr-filter-popover" data-filter-popover hidden>' +
      '<label>Venue<input data-state="paperVenue" value="' + esc(state.paperVenue) + '" placeholder="e.g. SIGIR"></label><label>Author<input data-state="paperAuthor" value="' + esc(state.paperAuthor) + '" placeholder="Author name"></label>' +
      '<label>Relevance<select data-state="relevanceLabel"><option value="">Core + related</option><option value="core"' + (state.relevanceLabel === 'core' ? ' selected' : '') + '>Core only</option><option value="related"' + (state.relevanceLabel === 'related' ? ' selected' : '') + '>Related only</option></select></label>' +
      '<label>Minimum relevance<input data-state="minimumRelevance" type="number" min="0" max="1" step="0.05" value="' + esc(state.minimumRelevance) + '"></label></div></div>' +
      '<label class="rr-sort-label"><span>Sort</span><select data-state="paperSort">' + [['newest','Newest'],['oldest','Oldest'],['relevance','Relevance'],['citations','Citations']].map(function (item) { return '<option value="' + item[0] + '"' + (state.paperSort === item[0] ? ' selected' : '') + '>' + item[1] + '</option>'; }).join('') + '</select></label></div></div>' +
      (chips.length ? '<div class="rr-active-filters">' + chips.map(function (chip) { return '<button type="button" data-clear-state="' + chip[0] + '">' + esc(chip[1]) + icon('x') + '</button>'; }).join('') + '</div>' : '');
  }
  function render(result, state) {
    var rows = result.items || [];
    return filters(state) + '<div class="rr-result-summary">' + result.total + ' papers</div><div class="rr-paper-list">' + (rows.length ? rows.map(function (paper) {
      var url = safeUrl(paper.external_url || paper.doi_url || paper.openalex_url);
      var authors = (paper.authors || []).map(function (a) { return a.name; });
      var authorText = authors.slice(0, 4).join(', ') + (authors.length > 4 ? ' +' + (authors.length - 4) : '');
      var snippet = String(paper.abstract || paper.snippet || '').trim();
      if (snippet.length > 240) snippet = snippet.slice(0, 237) + '...';
      return '<article class="rr-paper-row"><div class="rr-paper-main"><h3 class="rr-paper-title">' + esc(paper.title) + '</h3><div class="rr-paper-authors">' + esc(authorText || 'Authors unavailable') + '</div><div class="rr-paper-meta">' + esc(paper.venue || 'Venue unavailable') + ' · ' + esc(paper.year || 'Year unavailable') + '</div>' + (snippet ? '<p class="rr-paper-snippet">' + esc(snippet) + '</p>' : '') + '<div class="rr-paper-facts"><span class="rr-badge rr-badge-' + esc(paper.relevance_label) + '">' + esc(String(paper.relevance_label || '').toUpperCase()) + '</span><span>Relevance ' + Number(paper.relevance_score || 0).toFixed(2) + '</span><span>' + (paper.citation_count == null ? '—' : esc(paper.citation_count)) + ' citations</span></div></div><div class="rr-row-actions"><button type="button" class="rr-icon-button" data-save-paper="' + esc(paper.id) + '" aria-label="Save paper" title="Save paper">' + icon('bookmark') + '</button>' + (url ? '<a class="rr-icon-button" href="' + esc(url) + '" target="_blank" rel="noopener noreferrer" aria-label="Open paper" title="Open paper">' + icon('external') + '</a>' : '') + '</div></article>';
    }).join('') : '<div class="rr-empty-message"><strong>No papers found</strong><p>Try expanding the time range or adjusting your field keywords.</p></div>') + '</div>';
  }
  return { render: render, renderFilters: filters, safeUrl: safeUrl };
});
