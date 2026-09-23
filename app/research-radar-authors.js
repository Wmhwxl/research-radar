(function (root, factory) {
  var api = factory(); if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.ResearchRadarAuthors = api;
})(typeof window !== 'undefined' ? window : globalThis, function () {
  'use strict';
  function esc(value) { return String(value == null ? '' : value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
  function initials(name) { return String(name || '?').split(/\s+/).filter(Boolean).slice(0, 2).map(function (part) { return part.charAt(0); }).join('').toUpperCase(); }
  function icon(name) { return typeof window !== 'undefined' && window.ResearchRadarIcons ? window.ResearchRadarIcons.icon(name, 17) : ''; }
  function render(result, state) {
    var rows = result.items || [];
    return '<div class="rr-list-toolbar"><label class="rr-toolbar-search">' + icon('search') + '<span class="rr-sr-only">Search authors</span><input data-state="authorSearch" type="search" placeholder="Search authors..." value="' + esc(state.authorSearch) + '"></label><div class="rr-toolbar-actions"><label class="rr-compact-control"><span>Institution</span><input data-state="institution" value="' + esc(state.institution) + '" placeholder="All institutions"></label><label class="rr-compact-control rr-number-control"><span>Min papers</span><input data-state="minimumPapers" type="number" min="1" value="' + esc(state.minimumPapers) + '"></label></div></div>' +
      '<div class="rr-result-summary">' + result.total + ' authors</div><div class="rr-author-list">' + (rows.length ? rows.map(function (author) {
        return '<button class="rr-author-row rr-author-open" data-author-id="' + esc(author.id) + '"><span class="rr-avatar" aria-hidden="true">' + esc(initials(author.name)) + '</span><span class="rr-author-identity"><strong>' + esc(author.name) + '</strong><small>' + esc(author.primary_institution || 'Institution unavailable') + '</small></span><span><b>' + esc(author.field_paper_count) + '</b><small>field papers</small></span><span><b>' + esc(author.first_field_year || '—') + '–' + esc(author.latest_field_year || '—') + '</b><small>active years</small></span><span><b>' + esc(author.citation_count == null ? '—' : author.citation_count) + '</b><small>citations</small></span><span class="rr-row-chevron">' + icon('chevron') + '</span></button>';
      }).join('') : '<div class="rr-empty-message"><strong>No authors found</strong><p>Try a broader name or institution search.</p></div>') + '</div>';
  }
  return { render: render, initials: initials };
});
