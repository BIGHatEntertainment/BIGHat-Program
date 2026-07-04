/**
 * v32.0.0-alpha.42 — client-side debug capture.
 *
 * The frozen Tauri release build ships without DevTools, so when the
 * merchant reports a UI bug we can't see the network tab or the console.
 * This module wires three global capture points:
 *
 *   1. Every mouse click captured (target's `data-testid`, tag, text, route)
 *   2. Every axios request + response (URL, status, timing, error msg)
 *   3. Every React Router route change
 *
 * Events are buffered in memory and POSTed in batches every 2s to
 * `POST /api/debug/log` — which rotates a 2-file, 1MB-each log at
 * `<Documents>/BIG Hat Entertainment/Files/Logs/app.log`.
 *
 * Zero deps beyond axios (already imported everywhere).
 *
 * Usage:  called once from App.js — `installDebugCapture()`.
 */
import axios from 'axios';

const API_BASE = process.env.REACT_APP_BACKEND_URL || '';
const ENDPOINT = `${API_BASE}/api/debug/log`;
const FLUSH_MS = 2000;
const MAX_QUEUE = 200;

// One session id per page load so the merchant can group events.
const SESSION = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;

let queue = [];
let flushTimer = null;

/** Push an event onto the queue and schedule a flush. */
function enqueue(type, data) {
  if (queue.length >= MAX_QUEUE) queue.shift();
  queue.push({
    type,
    at: new Date().toISOString(),
    session: SESSION,
    data: data || {},
  });
  scheduleFlush();
}

function scheduleFlush() {
  if (flushTimer) return;
  flushTimer = setTimeout(flushNow, FLUSH_MS);
}

async function flushNow() {
  flushTimer = null;
  if (!queue.length) return;
  const batch = queue.splice(0, queue.length);
  try {
    // Use fetch here — axios interceptors would create an infinite loop.
    await fetch(ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ events: batch }),
      keepalive: true,
    });
  } catch (e) {
    // Best-effort. If flushing fails we drop the batch — the point is
    // to help debugging, not to be a source of new bugs.
    // eslint-disable-next-line no-console
    console.warn('[debug-log] flush failed:', e?.message || e);
  }
}

/** Wrap document-level `click` events. Captures data-testid, text,
 *  href, and the current route so we can replay merchant flows. */
function installClickListener() {
  document.addEventListener(
    'click',
    (ev) => {
      const t = ev.target;
      if (!t) return;
      let el = t;
      // Walk up to the first element with data-testid or a semantic role.
      let steps = 0;
      while (el && steps < 6) {
        if (el.dataset && el.dataset.testid) break;
        if (el.tagName === 'BUTTON' || el.tagName === 'A') break;
        el = el.parentElement;
        steps += 1;
      }
      const tgt = el || t;
      enqueue('click', {
        testid: tgt.dataset?.testid || '',
        tag: tgt.tagName || '',
        text: (tgt.textContent || '').trim().slice(0, 80),
        href: tgt.getAttribute?.('href') || '',
        route: window.location.pathname + window.location.search,
      });
    },
    true, // capture phase so we see clicks even if a child stops propagation
  );
}

/** Axios interceptors — one for request start, one for response.
 *  Measures ms elapsed so we can spot slow calls at a glance. */
function installAxiosInterceptors() {
  axios.interceptors.request.use((cfg) => {
    // eslint-disable-next-line no-param-reassign
    cfg.metadata = { start: performance.now() };
    return cfg;
  });
  axios.interceptors.response.use(
    (res) => {
      const ms = Math.round(performance.now() - (res.config?.metadata?.start || performance.now()));
      const url = res.config?.url || '';
      // Don't log the flush endpoint itself — infinite loop.
      if (!url.includes('/api/debug/log')) {
        enqueue('axios', {
          url,
          method: (res.config?.method || 'get').toUpperCase(),
          status: res.status,
          ms,
          resultSize: (() => {
            try {
              if (Array.isArray(res.data)) return `array(${res.data.length})`;
              if (res.data && typeof res.data === 'object') return `obj(${Object.keys(res.data).length}k)`;
              return typeof res.data;
            } catch { return '?'; }
          })(),
        });
      }
      return res;
    },
    (err) => {
      const cfg = err.config || {};
      const ms = Math.round(performance.now() - (cfg.metadata?.start || performance.now()));
      const url = cfg.url || '';
      if (!url.includes('/api/debug/log')) {
        enqueue('axios_error', {
          url,
          method: (cfg.method || 'get').toUpperCase(),
          status: err.response?.status || 0,
          ms,
          message: err.message || 'unknown',
          detail: (() => {
            try {
              const d = err.response?.data;
              if (typeof d === 'string') return d.slice(0, 200);
              if (d && typeof d === 'object') return JSON.stringify(d).slice(0, 200);
              return '';
            } catch { return ''; }
          })(),
        });
      }
      return Promise.reject(err);
    },
  );
}

/** Route change hook — captures `pushState` / `popstate`. */
function installRouteListener() {
  const emit = () => {
    enqueue('route', {
      route: window.location.pathname + window.location.search + window.location.hash,
      referrer: document.referrer || '',
    });
  };
  window.addEventListener('popstate', emit);
  const originalPushState = window.history.pushState;
  window.history.pushState = function (...args) {
    const result = originalPushState.apply(this, args);
    emit();
    return result;
  };
  // Emit the initial route once at install time.
  emit();
}

/** Global error handler — catches uncaught JS errors + Promise rejections. */
function installErrorListener() {
  window.addEventListener('error', (ev) => {
    enqueue('js_error', {
      message: ev.message || '',
      filename: ev.filename || '',
      lineno: ev.lineno || 0,
      colno: ev.colno || 0,
      stack: (ev.error?.stack || '').slice(0, 400),
    });
  });
  window.addEventListener('unhandledrejection', (ev) => {
    enqueue('promise_rejection', {
      reason: String(ev.reason || '').slice(0, 400),
      stack: (ev.reason?.stack || '').slice(0, 400),
    });
  });
}

let installed = false;

/**
 * Install all capture hooks. Idempotent — safe to call multiple times.
 * Wraps everything in a try/catch so a bug in the LOGGER can never
 * take down the app.
 */
export function installDebugCapture() {
  if (installed) return;
  installed = true;
  try {
    installClickListener();
    installAxiosInterceptors();
    installRouteListener();
    installErrorListener();
    enqueue('boot', {
      session: SESSION,
      url: window.location.href,
      ua: navigator.userAgent,
      api_base: API_BASE || '(relative)',
    });
    // Flush on page unload — best effort.
    window.addEventListener('beforeunload', () => { flushNow(); });
    // eslint-disable-next-line no-console
    console.info(`[debug-log] capture active (session ${SESSION})`);
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error('[debug-log] install failed:', e);
  }
}

/** Manual logger — components can call `debugLog('some_event', {...})` */
export function debugLog(type, data) {
  enqueue(type, data);
}
