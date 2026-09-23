(function (root, factory) {
  var api = factory(); if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.ResearchRadarGraph = api;
})(typeof window !== 'undefined' ? window : globalThis, function () {
  'use strict';
  function nodeSize(count) { return Math.min(44, 16 + 8 * Math.sqrt(Math.max(1, Number(count) || 1))); }
  function edgeWidth(count) { return Math.min(7, 1 + 1.6 * Math.sqrt(Math.max(1, Number(count) || 1))); }
  function icon(name) { return typeof window !== 'undefined' && window.ResearchRadarIcons ? window.ResearchRadarIcons.icon(name, 17) : ''; }
  function buildElements(data) {
    return (data.nodes || []).map(function (node, index) { return { group: 'nodes', data: Object.assign({}, node, {
      size: nodeSize(node.field_paper_count), show_label: index < 6 ? 1 : 0
    }) }; }).concat((data.edges || []).map(function (edge) { return { group: 'edges', data: Object.assign({}, edge, {
      id: [edge.source, edge.target].sort().join('--'), width: edgeWidth(edge.field_collaboration_count)
    }) }; }));
  }
  function renderToolbar(state, total, visible) {
    function selected(value) { return String(state.maxNodes) === String(value) ? ' selected' : ''; }
    return '<div class="rr-graph-toolbar"><label class="rr-toolbar-search">' + icon('search') + '<span class="rr-sr-only">Search author</span><input data-state="graphSearch" type="search" placeholder="Search author..." value="' + String(state.graphSearch || '').replace(/"/g, '&quot;') + '"></label>' +
      '<div class="rr-graph-primary-filters"><label class="rr-number-control"><span>Min papers</span><input data-state="minimumPapers" type="number" min="1" value="' + Number(state.minimumPapers || 1) + '"></label><label class="rr-number-control"><span>Min links</span><input data-state="minimumCollaborations" type="number" min="1" value="' + Number(state.minimumCollaborations || 1) + '"></label></div>' +
      '<div class="rr-graph-actions"><button class="rr-icon-button" data-graph-action="fit" aria-label="Fit graph" title="Fit graph">' + icon('fit') + '</button><button class="rr-icon-button" data-graph-action="reset" aria-label="Reset graph" title="Reset graph">' + icon('refresh') + '</button><button class="rr-icon-button" data-graph-action="zoom-in" aria-label="Zoom in" title="Zoom in">' + icon('zoomIn') + '</button><button class="rr-icon-button" data-graph-action="zoom-out" aria-label="Zoom out" title="Zoom out">' + icon('zoomOut') + '</button><div class="rr-popover-wrap"><button class="rr-icon-button" data-toggle-filters aria-label="More graph filters" title="More filters">' + icon('filter') + '</button><div class="rr-filter-popover rr-graph-filter-popover" data-filter-popover hidden><label class="rr-check"><input data-state="coreOnly" type="checkbox"' + (state.coreOnly ? ' checked' : '') + '> Core papers only</label><label>Maximum authors<select data-state="maxNodes"><option' + selected(250) + '>250</option><option' + selected(500) + '>500</option><option' + selected(1000) + '>1000</option><option value="all"' + selected('all') + '>All</option></select></label></div></div></div><span class="rr-graph-count">' + visible + ' of ' + total + ' authors</span></div>';
  }
  function mount(container, data, options) {
    options = options || {};
    var cyFactory = options.cytoscape || (typeof cytoscape !== 'undefined' ? cytoscape : null);
    if (!cyFactory) throw new Error('Cytoscape is not available');
    var dark = typeof document !== 'undefined' && document.querySelector('.rr-app[data-theme="dark"]');
    var colors = dark ? { node:'#6ea8c3', text:'#dce8ee', selected:'#e8a25f', edge:'#637582', neighbor:'#9dc4d5' } : { node:'#4f839a', text:'#263b46', selected:'#c86b32', edge:'#a5b2ba', neighbor:'#5c879a' };
    var cy = cyFactory({ container: container, elements: buildElements(data), minZoom: 0.15, maxZoom: 3, style: [
        { selector: 'node', style: { width: 'data(size)', height: 'data(size)', 'background-color': colors.node, 'border-width': 1, 'border-color': colors.node, label: 'data(name)', 'font-size': 10, color: colors.text, 'text-valign': 'bottom', 'text-margin-y': 6, 'text-max-width': 110, 'text-wrap': 'ellipsis', 'text-opacity': 0 } },
        { selector: 'node[show_label = 1], node:selected', style: { 'text-opacity': 1 } },
        { selector: 'node:selected', style: { 'border-width': 4, 'border-color': colors.selected, 'background-color': colors.node } },
        { selector: 'node:active', style: { 'border-width': 3, 'border-color': colors.selected } },
        { selector: 'edge', style: { width: 'data(width)', 'line-color': colors.edge, 'curve-style': 'bezier', opacity: 0.62 } },
        { selector: '.rr-dim', style: { opacity: 0.18, 'text-opacity': 0 } },
        { selector: '.rr-neighbor', style: { opacity: 1, 'line-color': colors.neighbor } }
      ], layout: { name: 'cose', animate: false, fit: true, padding: 36, nodeRepulsion: function () { return 6500; }, idealEdgeLength: function () { return 80; } } });
    function clearFocus() { cy.elements().removeClass('rr-dim rr-neighbor'); }
    function focus(node) {
      clearFocus(); var neighborhood = node.closedNeighborhood();
      cy.elements().difference(neighborhood).addClass('rr-dim'); neighborhood.addClass('rr-neighbor');
    }
    cy.on('tap', 'node', function (event) { focus(event.target); if (options.onAuthor) options.onAuthor(event.target.data('id')); });
    cy.on('tap', 'edge', function (event) { clearFocus(); event.target.addClass('rr-neighbor'); if (options.onCollaboration) options.onCollaboration(event.target.data('source'), event.target.data('target')); });
    cy.on('tap', function (event) { if (event.target === cy) { clearFocus(); if (options.onBackground) options.onBackground(); } });
    cy.on('mouseover', 'node', function (event) { event.target.style({ 'text-opacity': 1, 'border-width': 2, 'border-color': colors.selected }); });
    cy.on('mouseout', 'node', function (event) { if (!event.target.selected()) event.target.style({ 'border-width': 1, 'border-color': colors.node }); if (!event.target.selected() && !event.target.data('show_label')) event.target.style('text-opacity', 0); });
    var resizeObserver = typeof ResizeObserver === 'function' ? new ResizeObserver(function () { cy.resize(); }) : null;
    var onWindowResize = function () { cy.resize(); };
    if (resizeObserver) resizeObserver.observe(container);
    else if (typeof window !== 'undefined') window.addEventListener('resize', onWindowResize);
    return { cy: cy, fit: function () { cy.fit(undefined, 36); }, reset: function () { clearFocus(); cy.elements().unselect(); cy.fit(undefined, 36); },
      zoomIn: function () { cy.zoom({ level: Math.min(3, cy.zoom() * 1.25), renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } }); },
      zoomOut: function () { cy.zoom({ level: Math.max(0.15, cy.zoom() / 1.25), renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } }); },
      selectAuthor: function (id) { var node = cy.getElementById(id); if (!node.length) return false; cy.animate({ center: { eles: node }, zoom: Math.max(1.2, cy.zoom()) }, { duration: 250 }); node.select(); focus(node); return true; },
      destroy: function () { if (resizeObserver) resizeObserver.disconnect(); else if (typeof window !== 'undefined') window.removeEventListener('resize', onWindowResize); cy.destroy(); } };
  }
  return { nodeSize: nodeSize, edgeWidth: edgeWidth, buildElements: buildElements, renderToolbar: renderToolbar, mount: mount };
});
