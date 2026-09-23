(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
    return;
  }

  var api = factory();
  var hostWindow = root && root.window ? root.window : root;
  if (hostWindow) {
    hostWindow.DPRSiteStats = api;
    if (typeof api.autoInit === 'function') {
      api.autoInit(hostWindow);
    }
  }
})(
  typeof globalThis !== 'undefined'
    ? globalThis
    : typeof self !== 'undefined'
      ? self
      : this,
  function () {
    'use strict';

    var DEFAULTS = {
      supabaseUrl: 'https://lyucdwgefyfbmaiopjbk.supabase.co',
      supabaseKey: 'sb_publishable_lX-oi64Uxyd7SIVv3_w2Uw_MTOojeKq',
      countsDateColumn: 'visit_date',
      historyDays: 14,
      githubRepoApi: 'https://api.github.com/repos/ziwenhahaha/daily-paper-reader',
      forkCacheMs: 6 * 60 * 60 * 1000,
      timezone: 'Asia/Shanghai',
      selectors: {
        container: '[data-dpr-site-stats]',
        readers: '[data-dpr-daily-readers]',
        yesterday: '[data-dpr-yesterday-readers]',
        forks: '[data-dpr-fork-count]',
        historyChart: '[data-dpr-history-chart]',
        historyRange: '[data-dpr-history-range]',
        historyPeak: '[data-dpr-history-peak]',
      },
      storageKeys: {
        visitorId: 'dpr-site-stats-visitor-id',
        successDate: 'dpr-site-stats-last-success-date',
        forkCache: 'dpr-site-stats-fork-cache',
      },
    };

    function mergeObjects(base, extra) {
      var merged = {};
      var key;
      base = base || {};
      extra = extra || {};
      for (key in base) {
        if (Object.prototype.hasOwnProperty.call(base, key)) {
          merged[key] = base[key];
        }
      }
      for (key in extra) {
        if (Object.prototype.hasOwnProperty.call(extra, key)) {
          if (
            merged[key] &&
            typeof merged[key] === 'object' &&
            !Array.isArray(merged[key]) &&
            extra[key] &&
            typeof extra[key] === 'object' &&
            !Array.isArray(extra[key])
          ) {
            merged[key] = mergeObjects(merged[key], extra[key]);
          } else {
            merged[key] = extra[key];
          }
        }
      }
      return merged;
    }

    function resolveConfig(win, overrideConfig) {
      var windowConfig = win && win.DPR_SITE_STATS_CONFIG ? win.DPR_SITE_STATS_CONFIG : null;
      return mergeObjects(DEFAULTS, mergeObjects(windowConfig, overrideConfig));
    }

    function resolveTextEncoder() {
      if (typeof TextEncoder !== 'undefined') return TextEncoder;
      try {
        return require('node:util').TextEncoder;
      } catch (_err) {
        return null;
      }
    }

    function resolveNodeCrypto() {
      try {
        return require('node:crypto');
      } catch (_err) {
        return null;
      }
    }

    function getBeijingDateString(input) {
      var date = input instanceof Date ? input : new Date(input || Date.now());
      var formatter = new Intl.DateTimeFormat('en-CA', {
        timeZone: DEFAULTS.timezone,
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
      });
      var parts = formatter.formatToParts(date);
      var result = { year: '', month: '', day: '' };
      var i;
      for (i = 0; i < parts.length; i += 1) {
        if (parts[i] && result[parts[i].type] !== undefined) {
          result[parts[i].type] = parts[i].value;
        }
      }
      return result.year + '-' + result.month + '-' + result.day;
    }

    function shiftBeijingDateString(dateString, offsetDays) {
      var match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(dateString || ''));
      if (!match) return '';
      var shifted = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]) + Number(offsetDays || 0)));
      return shifted.toISOString().slice(0, 10);
    }

    function getPreviousBeijingDateString(dateString) {
      return shiftBeijingDateString(dateString, -1);
    }

    function buildContinuousBeijingDates(endDateString, totalDays) {
      var days = toPositiveInteger(totalDays, 1);
      if (days < 1) days = 1;
      var startDate = shiftBeijingDateString(endDateString, -(days - 1));
      var dates = [];
      var index;
      for (index = 0; index < days; index += 1) {
        dates.push(shiftBeijingDateString(startDate, index));
      }
      return dates;
    }

    function createUuid(cryptoImpl) {
      if (cryptoImpl && typeof cryptoImpl.randomUUID === 'function') {
        return cryptoImpl.randomUUID();
      }

      var randomBytes = new Uint8Array(16);
      if (cryptoImpl && typeof cryptoImpl.getRandomValues === 'function') {
        cryptoImpl.getRandomValues(randomBytes);
      } else {
        var idx;
        for (idx = 0; idx < randomBytes.length; idx += 1) {
          randomBytes[idx] = Math.floor(Math.random() * 256);
        }
      }

      randomBytes[6] = (randomBytes[6] & 15) | 64;
      randomBytes[8] = (randomBytes[8] & 63) | 128;

      var hex = [];
      var i;
      for (i = 0; i < randomBytes.length; i += 1) {
        hex.push((randomBytes[i] + 256).toString(16).slice(1));
      }
      return [
        hex.slice(0, 4).join(''),
        hex.slice(4, 6).join(''),
        hex.slice(6, 8).join(''),
        hex.slice(8, 10).join(''),
        hex.slice(10, 16).join(''),
      ].join('-');
    }

    async function sha256Hex(value, cryptoImpl) {
      var text = String(value == null ? '' : value);
      var Encoder = resolveTextEncoder();
      if (cryptoImpl && cryptoImpl.subtle && typeof cryptoImpl.subtle.digest === 'function' && Encoder) {
        var digest = await cryptoImpl.subtle.digest('SHA-256', new Encoder().encode(text));
        var bytes = new Uint8Array(digest);
        return Array.prototype.map.call(bytes, function (byte) {
          return byte.toString(16).padStart(2, '0');
        }).join('');
      }

      var nodeCrypto = resolveNodeCrypto();
      if (nodeCrypto && typeof nodeCrypto.createHash === 'function') {
        return nodeCrypto.createHash('sha256').update(text, 'utf8').digest('hex');
      }

      throw new Error('sha256 unavailable');
    }

    function getLocalStorageValue(storage, key) {
      try {
        return storage && typeof storage.getItem === 'function' ? storage.getItem(key) : null;
      } catch (_err) {
        return null;
      }
    }

    function setLocalStorageValue(storage, key, value) {
      try {
        if (storage && typeof storage.setItem === 'function') {
          storage.setItem(key, value);
        }
      } catch (_err) {
        // ignore
      }
    }

    function resolveGithubToken(win, explicitToken) {
      var token = String(explicitToken || '').trim();
      if (token) return token;

      try {
        var secret = (win && win.decoded_secret_private) || {};
        token = String((secret.github && secret.github.token) || '').trim();
        if (token) return token;
      } catch (_err) {
        // ignore
      }

      try {
        var tokenLoader = win
          && win.SubscriptionsGithubToken
          && typeof win.SubscriptionsGithubToken.loadGithubToken === 'function'
          ? win.SubscriptionsGithubToken.loadGithubToken
          : null;
        var stored = tokenLoader ? tokenLoader.call(win.SubscriptionsGithubToken) : null;
        return String((stored && stored.token) || stored || '').trim();
      } catch (_err) {
        return '';
      }
    }

    function setHidden(element, hidden) {
      if (!element) return;
      element.hidden = !!hidden;
      try {
        if (hidden) {
          element.setAttribute && element.setAttribute('hidden', '');
        } else if (element.removeAttribute) {
          element.removeAttribute('hidden');
        }
      } catch (_err) {
        // ignore
      }
    }

    function toPositiveInteger(value, fallback) {
      var numeric = Number(value);
      if (!Number.isFinite(numeric) || numeric < 0) return fallback;
      return Math.round(numeric);
    }

    function formatCount(value) {
      return toPositiveInteger(value, 0).toLocaleString('zh-CN');
    }

    function formatMonthDay(dateString) {
      var match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(dateString || ''));
      if (!match) return '';
      return String(Number(match[2])) + '/' + String(Number(match[3]));
    }

    function formatHistoryRange(history) {
      if (!Array.isArray(history) || history.length === 0) return '';
      return formatMonthDay(history[0].date) + '-' + formatMonthDay(history[history.length - 1].date);
    }

    function getHistoryPeak(history) {
      var peak = 0;
      var index;
      if (!Array.isArray(history)) return peak;
      for (index = 0; index < history.length; index += 1) {
        peak = Math.max(peak, toPositiveInteger(history[index] && history[index].count, 0));
      }
      return peak;
    }

    function renderHistoryChart(history) {
      var items = Array.isArray(history) ? history : [];
      if (!items.length) return '';

      var width = 160;
      var height = 52;
      var paddingX = 8;
      var paddingTop = 6;
      var paddingBottom = 8;
      var chartHeight = height - paddingTop - paddingBottom;
      var peak = Math.max(getHistoryPeak(items), 1);
      var stepX = items.length > 1 ? (width - paddingX * 2) / (items.length - 1) : 0;
      var lineParts = [];
      var areaParts = [];
      var pointMarkup = [];
      var index;

      for (index = 0; index < items.length; index += 1) {
        var point = items[index] || {};
        var count = toPositiveInteger(point.count, 0);
        var x = items.length > 1 ? paddingX + stepX * index : width / 2;
        var y = paddingTop + chartHeight - (count / peak) * chartHeight;
        var coordinate = x.toFixed(2) + ',' + y.toFixed(2);
        lineParts.push(coordinate);
        areaParts.push((index === 0 ? 'M' : 'L') + x.toFixed(2) + ' ' + y.toFixed(2));
        pointMarkup.push(
          '<circle cx="' +
            x.toFixed(2) +
            '" cy="' +
            y.toFixed(2) +
            '" r="2.5" fill="#0f766e"></circle>',
        );
      }

      var baselineY = (height - paddingBottom).toFixed(2);
      var firstX = items.length > 1 ? paddingX : width / 2;
      var lastX = items.length > 1 ? width - paddingX : width / 2;
      var areaPath =
        areaParts.join(' ') +
        ' L' +
        lastX.toFixed(2) +
        ' ' +
        baselineY +
        ' L' +
        firstX.toFixed(2) +
        ' ' +
        baselineY +
        ' Z';

      return (
        '<svg viewBox="0 0 ' +
        width +
        ' ' +
        height +
        '" width="100%" height="52" aria-hidden="true" focusable="false">' +
        '<path class="dpr-home-history-area" d="' +
        areaPath +
        '" fill="#14b8a61f"></path>' +
        '<polyline class="dpr-home-history-line" points="' +
        lineParts.join(' ') +
        '" fill="none" stroke="#0f766e" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"></polyline>' +
        pointMarkup.join('') +
        '</svg>'
      );
    }

    function normalizeCountStats(readerStats) {
      var history = [];
      if (readerStats && typeof readerStats === 'object' && !Array.isArray(readerStats)) {
        history = Array.isArray(readerStats.history) ? readerStats.history : [];
        return {
          todayCount: toPositiveInteger(
            readerStats.todayCount != null ? readerStats.todayCount : readerStats.readerCount,
            0,
          ),
          yesterdayCount: toPositiveInteger(readerStats.yesterdayCount, 0),
          history: history,
        };
      }
      return {
        todayCount: toPositiveInteger(readerStats, 0),
        yesterdayCount: 0,
        history: history,
      };
    }

    function readForkCache(storage, storageKey, nowMs, maxAgeMs) {
      var raw = getLocalStorageValue(storage, storageKey);
      if (!raw) return null;
      try {
        var parsed = JSON.parse(raw);
        if (
          parsed &&
          Number.isFinite(parsed.forkCount) &&
          Number.isFinite(parsed.savedAt) &&
          nowMs - parsed.savedAt < maxAgeMs
        ) {
          return {
            forkCount: Math.round(parsed.forkCount),
            savedAt: parsed.savedAt,
          };
        }
      } catch (_err) {
        return null;
      }
      return null;
    }

    function createSiteStats(options) {
      options = options || {};
      var win = options.window || (typeof window !== 'undefined' ? window : null);
      var doc = options.document || (win && win.document) || null;
      var storage = options.localStorage || (win && win.localStorage) || null;
      var fetchImpl = options.fetch || (win && typeof win.fetch === 'function' ? win.fetch.bind(win) : null);
      var cryptoImpl = options.crypto || (win && win.crypto) || (typeof crypto !== 'undefined' ? crypto : null);
      var githubToken = resolveGithubToken(win, options.githubToken);
      var config = resolveConfig(win, options.config);
      var now = typeof options.now === 'function' ? options.now : function () {
        return new Date();
      };
      var state = {
        inFlight: null,
        rerunRequested: false,
      };

      function getToday() {
        return getBeijingDateString(now());
      }

      function getTargets() {
        if (!doc || typeof doc.querySelector !== 'function') {
          return {
            container: null,
            readers: null,
            forks: null,
          };
        }
        return {
          container: doc.querySelector(config.selectors.container),
          readers: doc.querySelector(config.selectors.readers),
          yesterday: doc.querySelector(config.selectors.yesterday),
          forks: doc.querySelector(config.selectors.forks),
          historyChart: doc.querySelector(config.selectors.historyChart),
          historyRange: doc.querySelector(config.selectors.historyRange),
          historyPeak: doc.querySelector(config.selectors.historyPeak),
        };
      }

      function hideStats() {
        var targets = getTargets();
        setHidden(targets.container, true);
        return targets;
      }

      function showStats(readerCount, forkCount, targets) {
        targets = targets || getTargets();
        var normalized = normalizeCountStats(readerCount);
        if (targets.readers) {
          targets.readers.textContent = formatCount(normalized.todayCount);
        }
        if (targets.yesterday) {
          targets.yesterday.textContent = formatCount(normalized.yesterdayCount);
        }
        if (targets.forks) {
          targets.forks.textContent = formatCount(forkCount);
        }
        if (targets.historyRange) {
          targets.historyRange.textContent = formatHistoryRange(normalized.history);
        }
        if (targets.historyPeak) {
          targets.historyPeak.textContent = formatCount(getHistoryPeak(normalized.history));
        }
        if (targets.historyChart) {
          targets.historyChart.innerHTML = renderHistoryChart(normalized.history);
        }
        setHidden(targets.container, false);
        return targets;
      }

      function ensureVisitorId() {
        var stored = getLocalStorageValue(storage, config.storageKeys.visitorId);
        if (stored) return stored;
        var created = createUuid(cryptoImpl);
        setLocalStorageValue(storage, config.storageKeys.visitorId, created);
        return created;
      }

      async function ensureDailyEvent(today) {
        var lastSuccess = getLocalStorageValue(storage, config.storageKeys.successDate);
        if (lastSuccess === today) {
          return { ok: true, skipped: true };
        }
        if (!fetchImpl) {
          return { ok: false, error: new Error('fetch unavailable') };
        }

        try {
          var visitorHash = await sha256Hex(ensureVisitorId(), cryptoImpl);
          var response = await fetchImpl(config.supabaseUrl + '/rest/v1/site_daily_reader_events', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              Accept: 'application/json',
              Prefer: 'return=minimal',
              apikey: config.supabaseKey,
              Authorization: 'Bearer ' + config.supabaseKey,
            },
            body: JSON.stringify({
              visit_date: today,
              visitor_hash: visitorHash,
            }),
          });
          if (!response || (!response.ok && response.status !== 409)) {
            return { ok: false, status: response ? response.status : 0 };
          }
          setLocalStorageValue(storage, config.storageKeys.successDate, today);
          return { ok: true, skipped: false, duplicate: response.status === 409 };
        } catch (error) {
          return { ok: false, error: error };
        }
      }

      async function fetchDailyReaderCount(today) {
        if (!fetchImpl) {
          return { ok: false, error: new Error('fetch unavailable') };
        }

        var historyDays = toPositiveInteger(config.historyDays, DEFAULTS.historyDays);
        if (historyDays < 1) historyDays = DEFAULTS.historyDays;
        var historyDates = buildContinuousBeijingDates(today, historyDays);
        var startDate = historyDates[0];
        var params = new URLSearchParams();
        params.set('select', config.countsDateColumn + ',reader_count');
        params.append(config.countsDateColumn, 'gte.' + startDate);
        params.append(config.countsDateColumn, 'lte.' + today);
        params.set('order', config.countsDateColumn + '.asc');
        params.set('limit', String(historyDays));
        var url = config.supabaseUrl + '/rest/v1/site_daily_reader_counts?' + params.toString();

        try {
          var response = await fetchImpl(url, {
            method: 'GET',
            headers: {
              Accept: 'application/json',
              apikey: config.supabaseKey,
              Authorization: 'Bearer ' + config.supabaseKey,
            },
          });
          if (!response || !response.ok) {
            return { ok: false, status: response ? response.status : 0 };
          }
          var payload = await response.json();
          var rows = Array.isArray(payload) ? payload : payload && typeof payload === 'object' ? [payload] : [];
          var countsByDate = {};
          var rowIndex;
          for (rowIndex = 0; rowIndex < rows.length; rowIndex += 1) {
            var row = rows[rowIndex];
            if (!row || typeof row !== 'object') continue;
            var rowDate = row[config.countsDateColumn];
            if (rowDate == null && rows.length === 1) {
              rowDate = today;
            }
            rowDate = String(rowDate || '').slice(0, 10);
            if (!rowDate) continue;
            countsByDate[rowDate] = toPositiveInteger(row.reader_count, 0);
          }
          var history = historyDates.map(function (dateString) {
            return {
              date: dateString,
              count: toPositiveInteger(countsByDate[dateString], 0),
            };
          });
          var todayCount = history.length ? history[history.length - 1].count : 0;
          var yesterdayCount = history.length > 1 ? history[history.length - 2].count : 0;
          return {
            ok: true,
            readerCount: todayCount,
            todayCount: todayCount,
            yesterdayCount: yesterdayCount,
            history: history,
          };
        } catch (error) {
          return { ok: false, error: error };
        }
      }

      async function fetchForkCount() {
        var currentTime = now().getTime();
        var cached = readForkCache(storage, config.storageKeys.forkCache, currentTime, config.forkCacheMs);
        if (cached) {
          return { ok: true, forkCount: cached.forkCount, cached: true };
        }
        if (!fetchImpl) {
          return { ok: false, error: new Error('fetch unavailable') };
        }

        try {
          var githubHeaders = {
            Accept: 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2022-11-28',
          };
          if (githubToken) {
            githubHeaders.Authorization = 'Bearer ' + githubToken;
          }
          var response = await fetchImpl(config.githubRepoApi, {
            method: 'GET',
            headers: githubHeaders,
          });
          if (!response || !response.ok) {
            return { ok: false, status: response ? response.status : 0 };
          }
          var payload = await response.json();
          var forkCount = toPositiveInteger(payload && payload.forks_count, 0);
          setLocalStorageValue(
            storage,
            config.storageKeys.forkCache,
            JSON.stringify({
              forkCount: forkCount,
              savedAt: currentTime,
            }),
          );
          return { ok: true, forkCount: forkCount, cached: false };
        } catch (error) {
          return { ok: false, error: error };
        }
      }

      async function runInit() {
        hideStats();

        try {
          var today = getToday();
          var postResult = await ensureDailyEvent(today);
          if (!postResult.ok) {
            return { ok: false, reason: 'post-failed', detail: postResult };
          }

          var targets = getTargets();
          if (!targets.container || !targets.readers || !targets.forks) {
            return {
              ok: true,
              date: today,
              displayed: false,
              postSkipped: !!postResult.skipped,
            };
          }

          var countResult = await fetchDailyReaderCount(today);
          if (!countResult.ok) {
            return { ok: false, reason: 'count-failed', detail: countResult };
          }

          var forkResult = await fetchForkCount();
          if (!forkResult.ok) {
            return { ok: false, reason: 'fork-failed', detail: forkResult };
          }

          targets = getTargets();
          if (!targets.container || !targets.readers || !targets.forks) {
            return {
              ok: true,
              date: today,
              displayed: false,
              readerCount: countResult.readerCount,
              forkCount: forkResult.forkCount,
              postSkipped: !!postResult.skipped,
              forkCached: !!forkResult.cached,
            };
          }

          showStats(countResult, forkResult.forkCount, targets);
          return {
            ok: true,
            date: today,
            displayed: true,
            readerCount: countResult.readerCount,
            todayCount: countResult.todayCount,
            yesterdayCount: countResult.yesterdayCount,
            history: countResult.history,
            forkCount: forkResult.forkCount,
            postSkipped: !!postResult.skipped,
            forkCached: !!forkResult.cached,
          };
        } catch (error) {
          return { ok: false, reason: 'unexpected', error: error };
        }
      }

      function init() {
        if (state.inFlight) {
          state.rerunRequested = true;
          return state.inFlight;
        }
        state.inFlight = Promise.resolve(runInit()).finally(function () {
          state.inFlight = null;
          if (state.rerunRequested) {
            state.rerunRequested = false;
            init();
          }
        });
        return state.inFlight;
      }

      function getConfig() {
        return config;
      }

      return {
        init: init,
        getToday: getToday,
        getConfig: getConfig,
        hideStats: hideStats,
        showStats: showStats,
        ensureVisitorId: ensureVisitorId,
        ensureDailyEvent: ensureDailyEvent,
        fetchDailyReaderCount: fetchDailyReaderCount,
        fetchForkCount: fetchForkCount,
      };
    }

    function autoInit(hostWindow) {
      hostWindow = hostWindow || (typeof window !== 'undefined' ? window : null);
      if (!hostWindow || hostWindow.__DPR_SITE_STATS_AUTO_INIT__) {
        return hostWindow && hostWindow.DPRSiteStatsInstance ? hostWindow.DPRSiteStatsInstance : null;
      }

      var doc = hostWindow.document;
      var instance = createSiteStats({
        window: hostWindow,
        document: doc,
        localStorage: hostWindow.localStorage,
        fetch: hostWindow.fetch && hostWindow.fetch.bind ? hostWindow.fetch.bind(hostWindow) : hostWindow.fetch,
        crypto: hostWindow.crypto,
      });

      hostWindow.DPRSiteStatsInstance = instance;
      hostWindow.__DPR_SITE_STATS_AUTO_INIT__ = true;

      function triggerInit() {
        try {
          var result = instance.init();
          if (result && typeof result.catch === 'function') {
            result.catch(function () {
              return null;
            });
          }
        } catch (_err) {
          // ignore
        }
      }

      if (doc && typeof doc.addEventListener === 'function') {
        doc.addEventListener('dpr-docsify-ready', triggerInit);
        if (doc.readyState === 'loading') {
          doc.addEventListener('DOMContentLoaded', triggerInit, { once: true });
        } else {
          triggerInit();
        }
      } else {
        triggerInit();
      }

      return instance;
    }

    return {
      DEFAULTS: DEFAULTS,
      autoInit: autoInit,
      createSiteStats: createSiteStats,
      createUuid: createUuid,
      formatCount: formatCount,
      buildContinuousBeijingDates: buildContinuousBeijingDates,
      getBeijingDateString: getBeijingDateString,
      getPreviousBeijingDateString: getPreviousBeijingDateString,
      resolveGithubToken: resolveGithubToken,
      sha256Hex: sha256Hex,
      shiftBeijingDateString: shiftBeijingDateString,
    };
  },
);
