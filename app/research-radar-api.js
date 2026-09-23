(function (root, factory) {
  var api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.ResearchRadarAPI = api;
})(typeof window !== 'undefined' ? window : globalThis, function () {
  'use strict';

  var FIXTURE_FILES = {
    fields: 'field.json', overview: 'overview.json', papers: 'papers.json',
    authors: 'authors.json', graph: 'graph.json', authorDetail: 'author_detail.json',
    collaborationDetail: 'collaboration_detail.json'
  };

  function fetchJson(url, options, fetchImpl) {
    return (fetchImpl || fetch)(url, options).then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (data) {
        if (!response.ok) {
          var detail = data && data.detail;
          throw new Error(detail || 'Research Radar request failed (' + response.status + ')');
        }
        return data;
      });
    });
  }

  function inYears(item, query) {
    var year = Number(item.year);
    return (!query.startYear || year >= Number(query.startYear)) &&
      (!query.endYear || year <= Number(query.endYear));
  }

  function safeUrl(value) {
    try {
      var url = new URL(String(value || ''));
      return url.protocol === 'http:' || url.protocol === 'https:' ? url.href : '';
    } catch (e) { return ''; }
  }

  function FixtureDataSource(options) {
    options = options || {};
    this.baseUrl = String(options.baseUrl || 'fixtures/research_radar').replace(/\/$/, '');
    this.fetchImpl = options.fetchImpl;
    this.cache = {};
    this.mode = 'fixture';
  }

  FixtureDataSource.prototype._load = function (key) {
    var self = this;
    if (!FIXTURE_FILES[key]) return Promise.reject(new Error('Unknown fixture: ' + key));
    if (!this.cache[key]) {
      this.cache[key] = fetchJson(this.baseUrl + '/' + FIXTURE_FILES[key], {}, this.fetchImpl).then(function (data) {
        if (!data || data.demo_fixture !== true) throw new Error('Fixture is missing demo_fixture marker: ' + key);
        return data;
      }).catch(function (error) {
        delete self.cache[key];
        throw error;
      });
    }
    return this.cache[key];
  };

  FixtureDataSource.prototype._bundle = function () {
    var self = this;
    return Promise.all(['fields', 'overview', 'papers', 'authors', 'graph', 'authorDetail', 'collaborationDetail'].map(function (key) {
      return self._load(key);
    })).then(function (items) {
      return { fields: items[0].fields, overview: items[1], papers: items[2].papers,
        authors: items[3].authors, edges: items[4].edges, authorDetails: items[5].authors,
        collaborationDetails: items[6].collaborations };
    });
  };

  FixtureDataSource.prototype.listResearchFields = function () {
    return this._load('fields').then(function (data) { return data.fields; });
  };

  FixtureDataSource.prototype.getFieldPapers = function (fieldId, query) {
    query = query || {};
    return this._bundle().then(function (data) {
      var search = String(query.search || '').trim().toLowerCase();
      var venue = String(query.venue || '').trim().toLowerCase();
      var author = String(query.author || '').trim().toLowerCase();
      var label = String(query.relevanceLabel || '').toLowerCase();
      var rows = data.papers.filter(function (paper) {
        return inYears(paper, query) && (!search || paper.title.toLowerCase().indexOf(search) >= 0) &&
          (!venue || String(paper.venue || '').toLowerCase().indexOf(venue) >= 0) &&
          (!author || paper.authors.some(function (item) { return item.name.toLowerCase().indexOf(author) >= 0; })) &&
          (!label || paper.relevance_label === label) &&
          (!query.minimumRelevance || Number(paper.relevance_score) >= Number(query.minimumRelevance));
      });
      var sort = query.sort || 'newest';
      rows.sort(function (a, b) {
        if (sort === 'oldest') return a.year - b.year || a.title.localeCompare(b.title);
        if (sort === 'relevance') return b.relevance_score - a.relevance_score;
        if (sort === 'citations') return (b.citation_count || 0) - (a.citation_count || 0);
        return b.year - a.year || a.title.localeCompare(b.title);
      });
      var total = rows.length;
      var offset = Number(query.offset) || 0;
      var limit = Number(query.limit) || 50;
      return { items: rows.slice(offset, offset + limit), total: total, demo_fixture: true };
    });
  };

  FixtureDataSource.prototype.getFieldAuthors = function (fieldId, query) {
    query = query || {};
    return this._bundle().then(function (data) {
      var papers = data.papers.filter(function (paper) { return inYears(paper, query); });
      var paperMap = Object.fromEntries(papers.map(function (paper) { return [paper.id, paper]; }));
      var search = String(query.search || '').trim().toLowerCase();
      var institution = String(query.institution || '').trim().toLowerCase();
      var rows = data.authors.map(function (author) {
        var ids = author.paper_ids.filter(function (id) { return !!paperMap[id]; });
        var years = ids.map(function (id) { return paperMap[id].year; });
        return Object.assign({}, author, { field_paper_count: ids.length, visible_paper_ids: ids,
          first_field_year: years.length ? Math.min.apply(Math, years) : null,
          latest_field_year: years.length ? Math.max.apply(Math, years) : null });
      }).filter(function (author) {
        return author.field_paper_count > 0 && (!search || author.name.toLowerCase().indexOf(search) >= 0) &&
          (!institution || String(author.primary_institution || '').toLowerCase().indexOf(institution) >= 0) &&
          (!query.minimumPapers || author.field_paper_count >= Number(query.minimumPapers)) &&
          (!query.firstYear || author.first_field_year >= Number(query.firstYear)) &&
          (!query.latestYear || author.latest_field_year <= Number(query.latestYear));
      });
      rows.sort(function (a, b) { return b.field_paper_count - a.field_paper_count || a.name.localeCompare(b.name); });
      var total = rows.length;
      var offset = Number(query.offset) || 0;
      var limit = Number(query.limit) || 50;
      return { items: rows.slice(offset, offset + limit), total: total, demo_fixture: true };
    });
  };

  FixtureDataSource.prototype.getScholarGraph = function (fieldId, query) {
    query = query || {};
    return this._bundle().then(function (data) {
      var papers = data.papers.filter(function (paper) {
        return inYears(paper, query) && (!query.coreOnly || paper.relevance_label === 'core');
      });
      var paperMap = Object.fromEntries(papers.map(function (paper) { return [paper.id, paper]; }));
      var nodes = data.authors.map(function (author) {
        var ids = author.paper_ids.filter(function (id) { return !!paperMap[id]; });
        var years = ids.map(function (id) { return paperMap[id].year; });
        return { id: author.id, name: author.name, institution: author.primary_institution,
          field_paper_count: ids.length, citation_count: author.citation_count,
          first_year: years.length ? Math.min.apply(Math, years) : null,
          latest_year: years.length ? Math.max.apply(Math, years) : null };
      }).filter(function (node) { return node.field_paper_count >= (Number(query.minimumPapers) || 1); });
      nodes.sort(function (a, b) { return b.field_paper_count - a.field_paper_count || a.name.localeCompare(b.name); });
      var totalNodes = nodes.length;
      var maxNodes = query.maxNodes === 'all' ? totalNodes : Number(query.maxNodes || 500);
      nodes = nodes.slice(0, maxNodes);
      var nodeIds = new Set(nodes.map(function (node) { return node.id; }));
      var edges = data.edges.map(function (edge) {
        var shared = edge.shared_paper_ids.filter(function (id) { return !!paperMap[id]; });
        var years = shared.map(function (id) { return paperMap[id].year; });
        return { source: edge.source, target: edge.target, shared_paper_ids: shared,
          field_collaboration_count: shared.length,
          first_year: years.length ? Math.min.apply(Math, years) : null,
          latest_year: years.length ? Math.max.apply(Math, years) : null };
      }).filter(function (edge) {
        return nodeIds.has(edge.source) && nodeIds.has(edge.target) &&
          edge.field_collaboration_count >= (Number(query.minimumCollaborations) || 1);
      });
      return { nodes: nodes, edges: edges, total_nodes: totalNodes, demo_fixture: true };
    });
  };

  FixtureDataSource.prototype.getFieldOverview = function (fieldId, query) {
    var self = this;
    return Promise.all([this._bundle(), this.getFieldPapers(fieldId, Object.assign({}, query, { limit: 1000 })),
      this.getFieldAuthors(fieldId, Object.assign({}, query, { limit: 1000 })), this.getScholarGraph(fieldId, Object.assign({}, query, { maxNodes: 'all' }))])
      .then(function (result) {
        var data = result[0], papers = result[1].items, authors = result[2].items, graph = result[3];
        var years = {};
        papers.forEach(function (paper) { years[paper.year] = (years[paper.year] || 0) + 1; });
        var newAuthors = {};
        authors.forEach(function (author) { var y = author.first_field_year; if (y) newAuthors[y] = (newAuthors[y] || 0) + 1; });
        var institutions = new Set(authors.map(function (author) { return author.primary_institution; }).filter(Boolean));
        var venues = new Set(papers.map(function (paper) { return paper.venue; }).filter(Boolean));
        return { paper_count: papers.length, author_count: authors.length, institution_count: institutions.size,
          collaboration_count: graph.edges.length, venue_count: venues.size,
          yearly_paper_counts: Object.keys(years).sort().map(function (year) { return { year: Number(year), count: years[year] }; }),
          yearly_new_author_counts: Object.keys(newAuthors).sort().map(function (year) { return { year: Number(year), count: newAuthors[year] }; }),
          recent_core_papers: papers.filter(function (paper) { return paper.relevance_label === 'core'; }).slice(0, 6),
          active_authors: authors.slice(0, 6), demo_fixture: true };
      });
  };

  FixtureDataSource.prototype.getAuthorDetail = function (fieldId, authorId, query) {
    var self = this;
    return Promise.all([this._bundle(), this.getFieldPapers(fieldId, Object.assign({}, query, { limit: 1000 })), this.getScholarGraph(fieldId, Object.assign({}, query, { maxNodes: 'all' }))])
      .then(function (result) {
        var data = result[0], papers = result[1].items, graph = result[2];
        var author = data.authors.find(function (item) { return item.id === authorId; });
        if (!author) throw new Error('Author not found');
        var paperRows = papers.filter(function (paper) { return paper.authors.some(function (item) { return item.id === authorId; }); });
        var collaborators = graph.edges.filter(function (edge) { return edge.source === authorId || edge.target === authorId; }).map(function (edge) {
          var id = edge.source === authorId ? edge.target : edge.source;
          var item = data.authors.find(function (candidate) { return candidate.id === id; });
          return { id: id, name: item ? item.name : id, shared_paper_count: edge.field_collaboration_count };
        }).sort(function (a, b) { return b.shared_paper_count - a.shared_paper_count; });
        return Object.assign({}, author, data.authorDetails[authorId] || {}, { field_paper_count: paperRows.length,
          first_field_year: paperRows.length ? Math.min.apply(Math, paperRows.map(function (p) { return p.year; })) : null,
          latest_field_year: paperRows.length ? Math.max.apply(Math, paperRows.map(function (p) { return p.year; })) : null,
          papers: paperRows, collaborators: collaborators, openalex_url: '', demo_fixture: true });
      });
  };

  FixtureDataSource.prototype.getCollaborationDetail = function (fieldId, authorA, authorB, query) {
    return this._bundle().then(function (data) {
      var ids = [authorA, authorB].sort();
      var papers = data.papers.filter(function (paper) {
        var authorIds = paper.authors.map(function (item) { return item.id; });
        return inYears(paper, query || {}) && authorIds.indexOf(ids[0]) >= 0 && authorIds.indexOf(ids[1]) >= 0;
      });
      var authors = ids.map(function (id) { return data.authors.find(function (item) { return item.id === id; }); });
      var key = ids.join('--');
      return { authors: authors, shared_paper_count: papers.length,
        first_year: papers.length ? Math.min.apply(Math, papers.map(function (p) { return p.year; })) : null,
        latest_year: papers.length ? Math.max.apply(Math, papers.map(function (p) { return p.year; })) : null,
        papers: papers, note: (data.collaborationDetails[key] || {}).note || '', demo_fixture: true };
    });
  };

  function SupabaseDataSource(options) {
    options = options || {};
    if (!options.url || !options.anonKey) throw new Error('Supabase Research Radar is not configured');
    this.url = String(options.url).replace(/\/$/, '');
    this.anonKey = options.anonKey;
    this.fetchImpl = options.fetchImpl;
    this.mode = 'supabase';
  }

  function LocalApiDataSource(options) {
    options = options || {};
    this.baseUrl = String(options.baseUrl || '').replace(/\/$/, '');
    this.fetchImpl = options.fetchImpl;
    this.mode = 'local';
  }
  LocalApiDataSource.prototype._get = function (path, query) {
    var params = new URLSearchParams();
    Object.keys(query || {}).forEach(function (key) {
      var value = query[key];
      if (value !== '' && value != null && value !== false) params.set(key, value === true ? '1' : String(value));
    });
    var suffix = params.toString() ? '?' + params.toString() : '';
    return fetchJson(this.baseUrl + path + suffix, { headers: { Accept: 'application/json' } }, this.fetchImpl);
  };
  LocalApiDataSource.prototype._post = function (path, body) {
    return fetchJson(this.baseUrl + path, {
      method: 'POST',
      headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {})
    }, this.fetchImpl);
  };
  LocalApiDataSource.prototype._patch = function (path, body) {
    return fetchJson(this.baseUrl + path, {
      method: 'PATCH',
      headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {})
    }, this.fetchImpl);
  };
  LocalApiDataSource.prototype.getHome = function () { return this._get('/api/home'); };
  LocalApiDataSource.prototype.listResearchFields = function () { return this._get('/api/research-fields'); };
  LocalApiDataSource.prototype.createResearchField = function (body) { return this._post('/api/research-fields', body); };
  LocalApiDataSource.prototype.updateResearchField = function (id, body) { return this._patch('/api/research-fields/' + encodeURIComponent(id), body); };
  LocalApiDataSource.prototype.startFieldSync = function (id, body) { return this._post('/api/research-fields/' + encodeURIComponent(id) + '/sync', body || { years: 1, max_pages: 1 }); };
  LocalApiDataSource.prototype.getSyncRun = function (id) { return this._get('/api/sync-runs/' + encodeURIComponent(id)); };
  LocalApiDataSource.prototype.getFieldBrief = function (id, q) { return this._get('/api/research-fields/' + encodeURIComponent(id) + '/brief', q || {}); };
  LocalApiDataSource.prototype.getSettings = function () { return this._get('/api/settings'); };
  LocalApiDataSource.prototype.search = function (q) { return this._get('/api/search', { q: q }); };
  LocalApiDataSource.prototype.getFieldOverview = function (id, q) { return this._get('/api/research-fields/' + encodeURIComponent(id) + '/overview', localQuery(q)); };
  LocalApiDataSource.prototype.getFieldPapers = function (id, q) { return this._get('/api/research-fields/' + encodeURIComponent(id) + '/papers', localQuery(q)); };
  LocalApiDataSource.prototype.getFieldAuthors = function (id, q) { return this._get('/api/research-fields/' + encodeURIComponent(id) + '/authors', localQuery(q)); };
  LocalApiDataSource.prototype.getScholarGraph = function (id, q) { return this._get('/api/research-fields/' + encodeURIComponent(id) + '/graph', localQuery(q)); };
  LocalApiDataSource.prototype.getAuthorDetail = function (id, authorId, q) { return this._get('/api/authors/' + encodeURIComponent(authorId), Object.assign(localQuery(q), { field_id: id })); };
  LocalApiDataSource.prototype.getCollaborationDetail = function (id, a, b, q) { return this._get('/api/collaborations/' + encodeURIComponent(a) + '/' + encodeURIComponent(b), Object.assign(localQuery(q), { field_id: id })); };

  function localQuery(query) {
    query = query || {};
    return {
      start_year: query.startYear, end_year: query.endYear, search: query.search,
      venue: query.venue, author: query.author, relevance_label: query.relevanceLabel,
      minimum_relevance: query.minimumRelevance, minimum_papers: query.minimumPapers,
      minimum_collaborations: query.minimumCollaborations, core_only: query.coreOnly,
      sort: query.sort, limit: query.limit, offset: query.offset, max_nodes: query.maxNodes
    };
  }
  SupabaseDataSource.prototype._request = function (path, body, method) {
    return fetchJson(this.url + '/rest/v1/' + path, { method: method || 'POST', headers: {
      apikey: this.anonKey, Authorization: 'Bearer ' + this.anonKey, 'Content-Type': 'application/json'
    }, body: body == null ? undefined : JSON.stringify(body) }, this.fetchImpl);
  };
  SupabaseDataSource.prototype._rpc = function (name, body) { return this._request('rpc/' + name, body || {}); };
  SupabaseDataSource.prototype.listResearchFields = function () { return this._request('research_fields?select=id,slug,name,description,core_keywords,updated_at&order=name', null, 'GET'); };
  function years(id, q) { return { p_field_id: id, p_start_year: Number((q || {}).startYear) || null, p_end_year: Number((q || {}).endYear) || null }; }
  SupabaseDataSource.prototype.getFieldOverview = function (id, q) { return this._rpc('get_research_field_overview', years(id, q)); };
  SupabaseDataSource.prototype.getFieldPapers = function (id, q) { q = q || {}; return this._rpc('get_research_field_papers', Object.assign(years(id, q), { p_search: q.search || null, p_venue: q.venue || null, p_author: q.author || null, p_relevance_label: q.relevanceLabel || null, p_min_relevance: q.minimumRelevance == null ? null : Number(q.minimumRelevance), p_sort: q.sort || 'newest', p_limit: Number(q.limit) || 50, p_offset: Number(q.offset) || 0 })); };
  SupabaseDataSource.prototype.getFieldAuthors = function (id, q) { q = q || {}; return this._rpc('get_research_field_authors', Object.assign(years(id, q), { p_search: q.search || null, p_institution: q.institution || null, p_min_papers: Number(q.minimumPapers) || 1, p_limit: Number(q.limit) || 50, p_offset: Number(q.offset) || 0 })); };
  SupabaseDataSource.prototype.getScholarGraph = function (id, q) { q = q || {}; return this._rpc('get_research_field_scholar_graph', Object.assign(years(id, q), { p_min_papers: Number(q.minimumPapers) || 1, p_min_collaborations: Number(q.minimumCollaborations) || 1, p_core_only: !!q.coreOnly, p_max_nodes: q.maxNodes === 'all' ? null : Number(q.maxNodes) || 500 })); };
  SupabaseDataSource.prototype.getAuthorDetail = function (id, authorId, q) { return this._rpc('get_research_field_author_detail', Object.assign(years(id, q), { p_author_id: authorId })); };
  SupabaseDataSource.prototype.getCollaborationDetail = function (id, a, b, q) { return this._rpc('get_research_field_collaboration_detail', Object.assign(years(id, q), { p_author_a_id: a, p_author_b_id: b })); };

  function rpcArgs(fieldId, query) {
    query = query || {};
    return { p_field_id: fieldId, p_start_year: Number(query.startYear) || null, p_end_year: Number(query.endYear) || null,
      p_search: query.search || null, p_relevance_label: query.relevanceLabel || null,
      p_min_relevance: query.minimumRelevance == null ? null : Number(query.minimumRelevance),
      p_min_papers: query.minimumPapers == null ? null : Number(query.minimumPapers),
      p_min_collaborations: query.minimumCollaborations == null ? null : Number(query.minimumCollaborations),
      p_core_only: !!query.coreOnly, p_sort: query.sort || null,
      p_limit: query.maxNodes === 'all' ? null : Number(query.limit || query.maxNodes) || null,
      p_offset: Number(query.offset) || 0 };
  }

  function createDataSource(config) {
    config = config || {};
    if (config.mode === 'fixture') return new FixtureDataSource(config);
    if (config.mode === 'local') return new LocalApiDataSource(config);
    if (config.mode === 'supabase') return new SupabaseDataSource(config);
    throw new Error('Research Radar data mode must be explicitly configured as fixture, local, or supabase');
  }

  return { FixtureDataSource: FixtureDataSource, LocalApiDataSource: LocalApiDataSource,
    SupabaseDataSource: SupabaseDataSource, createDataSource: createDataSource,
    safeUrl: safeUrl, rpcArgs: rpcArgs, localQuery: localQuery };
});
