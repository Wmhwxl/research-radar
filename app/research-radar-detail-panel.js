(function (root, factory) {
  var api = factory(); if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.ResearchRadarDetailPanel = api;
})(typeof window !== 'undefined' ? window : globalThis, function () {
  'use strict';
  function esc(value) { return String(value == null ? '' : value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
  function icon(name) { return typeof window !== 'undefined' && window.ResearchRadarIcons ? window.ResearchRadarIcons.icon(name, 18) : ''; }
  function initials(name) { return String(name || '?').split(/\s+/).filter(Boolean).slice(0, 2).map(function (part) { return part.charAt(0); }).join('').toUpperCase(); }
  function safeUrl(value) { try { var url = new URL(String(value || '')); return /^https?:$/.test(url.protocol) ? url.href : ''; } catch (error) { return ''; } }
  function papers(items) { return '<div class="rr-drawer-list">' + (items || []).map(function (paper) { return '<article><strong>' + esc(paper.title) + '</strong><small>' + esc(paper.year) + ' · ' + esc(paper.venue || 'Venue unavailable') + ' · ' + esc(String(paper.relevance_label || '').toUpperCase()) + '</small></article>'; }).join('') + '</div>'; }
  function author(data) {
    var external = safeUrl(data.openalex_url);
    return '<button class="rr-drawer-close rr-icon-button" aria-label="Close detail">' + icon('x') + '</button><div class="rr-drawer-profile"><span class="rr-avatar rr-avatar-large">' + esc(initials(data.name)) + '</span><div><div class="rr-drawer-kicker">Researcher</div><h2>' + esc(data.name) + '</h2><p>' + esc(data.primary_institution || 'Institution unavailable') + '</p></div></div>' +
      ((data.other_affiliations || []).length ? '<p class="rr-muted">Other affiliations: ' + esc(data.other_affiliations.join(', ')) + '</p>' : '') +
      '<div class="rr-detail-facts"><span><b>' + esc(data.field_paper_count) + '</b> Field papers</span><span><b>' + esc(data.total_works == null ? '—' : data.total_works) + '</b> Total works</span><span><b>' + esc(data.citation_count == null ? '—' : data.citation_count) + '</b> Citations</span><span><b>' + esc(data.first_field_year) + '–' + esc(data.latest_field_year) + '</b> Field years</span></div>' +
      '<h3>Top Collaborators</h3><div class="rr-collaborators">' + (data.collaborators || []).map(function (item) { return '<button class="rr-author-open" data-author-id="' + esc(item.id) + '"><span>' + esc(item.name) + '</span><b>' + esc(item.shared_paper_count) + ' papers</b></button>'; }).join('') + '</div><h3>Recent Papers</h3>' + papers(data.papers) + (external ? '<a class="rr-external-profile" href="' + esc(external) + '" target="_blank" rel="noopener noreferrer">Open external profile ' + icon('external') + '</a>' : '');
  }
  function collaboration(data) {
    var a = data.authors[0] || {}, b = data.authors[1] || {};
    return '<button class="rr-drawer-close rr-icon-button" aria-label="Close detail">' + icon('x') + '</button><div class="rr-drawer-kicker">Collaboration</div><h2>' + esc(a.name) + '<span> × </span>' + esc(b.name) + '</h2><div class="rr-detail-facts"><span><b>' + esc(data.shared_paper_count) + '</b> Shared papers</span><span><b>' + esc(data.first_year || '—') + '</b> First collaboration</span><span><b>' + esc(data.latest_year || '—') + '</b> Latest collaboration</span></div><h3>Shared Papers</h3>' + papers(data.papers);
  }
  return { renderAuthor: author, renderCollaboration: collaboration };
});
