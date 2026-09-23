(function (root, factory) {
  var api = factory(); if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.ResearchRadarOverview = api;
})(typeof window !== 'undefined' ? window : globalThis, function () {
  'use strict';
  function esc(value) { return String(value == null ? '' : value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
  function bars(title, rows) {
    var max = Math.max.apply(Math, (rows || []).map(function (row) { return row.count; }).concat([1]));
    return '<section class="rr-section rr-activity"><div class="rr-section-heading"><div><span class="rr-kicker">Activity</span><h2>' + esc(title) + '</h2></div><div class="rr-mini-range" aria-label="Chart range"><button data-range="1y">1Y</button><button data-range="3y">3Y</button><button data-range="5y" class="is-active">5Y</button></div></div><div class="rr-bars">' + (rows || []).map(function (row) {
      return '<div class="rr-bar-column" title="' + esc(row.count) + ' papers in ' + esc(row.year) + '"><span class="rr-bar-value">' + esc(row.count) + '</span><span class="rr-bar-track"><i style="height:' + Math.max(6, row.count / max * 100) + '%"></i></span><small>' + esc(row.year) + '</small></div>';
    }).join('') + '</div></section>';
  }
  function render(data) {
    var brief = data.brief || {};
    var stats = [
      ['Papers', data.paper_count, brief.new_paper_count ? '+' + brief.new_paper_count + ' recently' : 'In this field'],
      ['Authors', data.author_count, brief.new_author_count ? '+' + brief.new_author_count + ' newly observed' : 'Contributing researchers'],
      ['Institutions', data.institution_count, 'Represented in papers'],
      ['Collaborations', data.collaboration_count, brief.new_collaboration_count ? '+' + brief.new_collaboration_count + ' new links' : 'Coauthor connections']
    ];
    var news = [
      [brief.new_paper_count || 0, 'new papers'],
      [brief.new_author_count || 0, 'authors newly appearing'],
      [brief.new_collaboration_count || 0, 'new collaborations']
    ];
    return '<div class="rr-overview"><div class="rr-stats">' + stats.map(function (item) {
      return '<article class="rr-stat"><span>' + item[0] + '</span><strong>' + Number(item[1] || 0).toLocaleString() + '</strong><small>' + esc(item[2]) + '</small></article>';
    }).join('') + '</div><div class="rr-overview-primary">' + bars('Paper activity', data.yearly_paper_counts) +
      '<section class="rr-section rr-whats-new"><div class="rr-section-heading"><div><span class="rr-kicker">Recent brief</span><h2>What’s New</h2></div></div><div class="rr-news-metrics">' + news.map(function (item) { return '<div><strong>' + esc(item[0]) + '</strong><span>' + esc(item[1]) + '</span></div>'; }).join('') + '</div></section></div>' +
      '<div class="rr-overview-grid"><section class="rr-section"><div class="rr-section-heading"><div><span class="rr-kicker">Discovery</span><h2>Recent Highly Relevant Papers</h2></div></div>' + ((data.recent_core_papers || []).length ? (data.recent_core_papers || []).map(function (paper) {
        return '<article class="rr-compact-row"><div><strong>' + esc(paper.title) + '</strong><small>' + esc((paper.authors || []).slice(0, 3).map(function (a) { return a.name; }).join(', ')) + '</small></div><span>' + esc(paper.year || '') + '</span></article>';
      }).join('') : '<div class="rr-empty-inline">Highly relevant papers will appear after discovery.</div>') + '</section><section class="rr-section"><div class="rr-section-heading"><div><span class="rr-kicker">Community</span><h2>Active Researchers</h2></div></div>' + (data.active_authors || []).map(function (author) {
        return '<button class="rr-compact-row rr-author-open" data-author-id="' + esc(author.id) + '"><span><strong>' + esc(author.name) + '</strong><small>' + esc(author.primary_institution || 'Institution unavailable') + '</small></span><b>' + esc(author.field_paper_count) + ' papers</b></button>';
      }).join('') + '</section></div></div>';
  }
  return { render: render, escapeHtml: esc };
});
