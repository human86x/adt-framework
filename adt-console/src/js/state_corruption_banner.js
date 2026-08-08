/**
 * REQ-125 Priority 5: Console recovery banner.
 *
 * Polls the ADS events endpoint every 5 seconds for events of type
 * `state_corruption_detected` that fired *after* the page loaded. On hit,
 * renders a fixed-top red banner with three actions:
 *
 *   - "Show error"  -> modal with the parser message + last 10 lines of
 *                      the corrupt file (GET /api/state/file_head)
 *   - "Restore last known good" -> POST /api/state/restore_backup
 *   - "Dismiss"     -> hides banner (event stays in ADS; next corruption
 *                      re-shows)
 *
 * Style: dark red banner (#7a1f1f), cyan/console-theme action buttons.
 * Load-order-safe: uses IIFE + defer, does not depend on other modules.
 */
(function () {
  'use strict';

  var PAGE_LOAD_TS = Math.floor(Date.now() / 1000);
  var POLL_INTERVAL_MS = 5000;
  var API_BASE = (function () {
    try {
      return (window.localStorage && localStorage.getItem('adt_center_url'))
        || 'http://localhost:5001';
    } catch (e) {
      return 'http://localhost:5001';
    }
  })();

  // Track which corruption events we've already surfaced so a re-poll
  // with the same event id doesn't stack banners.
  var seenEventIds = Object.create(null);
  // If the operator dismisses, we hide this specific event id but keep
  // it in seenEventIds so it doesn't come back until a *new* one fires.
  var dismissedEventIds = Object.create(null);

  function el(tag, props, children) {
    var e = document.createElement(tag);
    if (props) {
      for (var k in props) {
        if (k === 'style' && typeof props[k] === 'object') {
          for (var s in props[k]) e.style[s] = props[k][s];
        } else if (k === 'onclick') {
          e.onclick = props[k];
        } else if (k in e) {
          e[k] = props[k];
        } else {
          e.setAttribute(k, props[k]);
        }
      }
    }
    (children || []).forEach(function (c) {
      if (c == null) return;
      e.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
    });
    return e;
  }

  function ensureBannerRoot() {
    var root = document.getElementById('state-corruption-banner-root');
    if (root) return root;
    root = el('div', {
      id: 'state-corruption-banner-root',
      style: {
        position: 'fixed',
        top: '0',
        left: '0',
        right: '0',
        zIndex: '10001',
      },
    });
    document.body.appendChild(root);
    return root;
  }

  function renderBanner(evt) {
    var root = ensureBannerRoot();
    // Only one banner at a time; replace whatever's there.
    root.innerHTML = '';

    var data = evt.action_data || {};
    var file = data.file || '(unknown file)';
    var line = data.line != null ? data.line : '?';
    var col = data.col != null ? data.col : '?';
    var detail = data.detail || '';
    var shortFile = String(file).split('/').pop();

    var showBtn = el('button', {
      style: btnStyle('#39c5cf'),
      onclick: function () { openErrorModal(file, detail); },
    }, ['Show error']);

    var restoreBtn = el('button', {
      style: btnStyle('#39c5cf'),
      onclick: function () { doRestore(file, evt.id); },
    }, ['Restore last known good']);

    var dismissBtn = el('button', {
      style: btnStyle('#8b949e'),
      onclick: function () {
        dismissedEventIds[evt.id] = true;
        root.innerHTML = '';
      },
    }, ['Dismiss']);

    var msg = el('div', {
      style: {
        flex: '1',
        color: '#ffe5e5',
        fontSize: '13px',
        fontWeight: '600',
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        whiteSpace: 'nowrap',
      },
      title: file + ' line ' + line + ' col ' + col + ': ' + detail,
    }, [
      '⚠️ State corruption detected: ',
      el('code', { style: { background: 'rgba(0,0,0,0.35)', padding: '1px 5px', borderRadius: '3px' } }, [shortFile]),
      ' (line ' + line + ', col ' + col + ')',
    ]);

    var banner = el('div', {
      style: {
        background: '#7a1f1f',
        borderBottom: '1px solid #c62828',
        color: '#fff',
        padding: '8px 14px',
        display: 'flex',
        alignItems: 'center',
        gap: '10px',
        boxShadow: '0 2px 8px rgba(0,0,0,0.4)',
        fontFamily: "'Inter', 'Segoe UI', sans-serif",
      },
    }, [msg, showBtn, restoreBtn, dismissBtn]);

    root.appendChild(banner);
  }

  function btnStyle(color) {
    return {
      background: '#21262d',
      color: color,
      border: '1px solid ' + color,
      borderRadius: '4px',
      padding: '5px 12px',
      fontSize: '12px',
      fontWeight: '600',
      cursor: 'pointer',
      whiteSpace: 'nowrap',
    };
  }

  function openErrorModal(file, detail) {
    var overlay = el('div', {
      style: {
        position: 'fixed', top: '0', left: '0', right: '0', bottom: '0',
        background: 'rgba(0,0,0,0.65)', zIndex: '10002',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      },
      onclick: function (e) { if (e.target === overlay) document.body.removeChild(overlay); },
    });

    var body = el('pre', {
      style: {
        margin: '0', padding: '10px', background: '#0d1117', color: '#e6edf3',
        fontFamily: 'monospace', fontSize: '11px', maxHeight: '60vh',
        overflow: 'auto', border: '1px solid #30363d', borderRadius: '4px',
        whiteSpace: 'pre-wrap',
      },
    }, ['Loading ' + file + ' …']);

    var closeBtn = el('button', {
      style: btnStyle('#8b949e'),
      onclick: function () { document.body.removeChild(overlay); },
    }, ['Close']);

    var modal = el('div', {
      style: {
        background: '#161b22', border: '1px solid #7a1f1f', borderRadius: '6px',
        padding: '18px', maxWidth: '80vw', minWidth: '520px',
        color: '#e6edf3', fontFamily: "'Inter', sans-serif",
      },
    }, [
      el('h3', { style: { margin: '0 0 8px 0', color: '#ff6b6b' } }, ['State corruption error']),
      el('div', { style: { marginBottom: '8px', fontSize: '12px', color: '#8b949e' } }, [file]),
      el('div', { style: { marginBottom: '10px', fontSize: '13px', color: '#ffd6d6' } }, ['Parser: ' + detail]),
      el('div', { style: { marginBottom: '6px', fontSize: '11px', color: '#8b949e', textTransform: 'uppercase' } }, ['Last 10 lines']),
      body,
      el('div', { style: { marginTop: '14px', textAlign: 'right' } }, [closeBtn]),
    ]);

    overlay.appendChild(modal);
    document.body.appendChild(overlay);

    fetch(
      API_BASE + '/api/state/file_head?path=' + encodeURIComponent(file) + '&lines=10',
      { credentials: 'include' }
    ).then(function (r) { return r.json(); }).then(function (j) {
      if (j.error) {
        body.textContent = 'Could not fetch file: ' + (j.error) + (j.detail ? '\n' + j.detail : '');
      } else if (j.exists === false) {
        body.textContent = '(file does not exist on disk)';
      } else {
        body.textContent = (j.lines || []).join('');
      }
    }).catch(function (err) {
      body.textContent = 'Fetch failed: ' + err;
    });
  }

  function doRestore(file, eventId) {
    fetch(
      API_BASE + '/api/state/restore_backup?path=' + encodeURIComponent(file),
      { method: 'POST', credentials: 'include' }
    ).then(function (r) {
      return r.json().then(function (j) { return { ok: r.ok, body: j }; });
    }).then(function (res) {
      if (res.ok) {
        dismissedEventIds[eventId] = true;
        var root = document.getElementById('state-corruption-banner-root');
        if (root) root.innerHTML = '';
        showToast(
          '✓ Restored ' + String(file).split('/').pop()
          + ' from ' + String(res.body.restored_from || '').split('/').pop(),
          '#238636'
        );
      } else {
        showToast(
          '✗ Restore failed: ' + (res.body.error || 'unknown')
          + (res.body.detail ? ' (' + res.body.detail + ')' : ''),
          '#7a1f1f'
        );
      }
    }).catch(function (err) {
      showToast('✗ Restore request failed: ' + err, '#7a1f1f');
    });
  }

  function showToast(text, bg) {
    var t = el('div', {
      style: {
        position: 'fixed', bottom: '30px', right: '30px', zIndex: '10003',
        background: bg, color: '#fff', padding: '10px 16px',
        borderRadius: '5px', fontFamily: "'Inter', sans-serif",
        fontSize: '13px', fontWeight: '600',
        boxShadow: '0 4px 12px rgba(0,0,0,0.5)',
      },
    }, [text]);
    document.body.appendChild(t);
    setTimeout(function () {
      if (t.parentNode) t.parentNode.removeChild(t);
    }, 4500);
  }

  function poll() {
    var url = API_BASE + '/api/ads/events?action_type=state_corruption_detected&limit=5';
    fetch(url, { credentials: 'include' }).then(function (r) {
      return r.ok ? r.json() : [];
    }).then(function (events) {
      if (!Array.isArray(events) || events.length === 0) return;
      // Filter to events after page load and not yet acknowledged.
      var fresh = events.filter(function (e) {
        var ts = e.timestamp || e.ts || 0;
        // Timestamps in ADS can be ISO strings; treat unparseable as "recent enough".
        var tsSec = typeof ts === 'number'
          ? ts
          : (function () {
              var d = new Date(ts);
              return isNaN(d.getTime()) ? PAGE_LOAD_TS : Math.floor(d.getTime() / 1000);
            })();
        if (tsSec < PAGE_LOAD_TS) return false;
        if (seenEventIds[e.id]) return false;
        return true;
      });
      if (fresh.length === 0) return;
      // Newest first; ADS query usually returns newest last, so pick the latest.
      var latest = fresh[fresh.length - 1];
      seenEventIds[latest.id] = true;
      if (dismissedEventIds[latest.id]) return;
      renderBanner(latest);
    }).catch(function () {
      // Silent -- polling failure shouldn't spam.
    });
  }

  function start() {
    // First poll after a short delay so it doesn't race the initial page render.
    setTimeout(poll, 2000);
    setInterval(poll, POLL_INTERVAL_MS);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }

  // Expose for tests / manual trigger.
  window.StateCorruptionBanner = {
    _renderForTest: renderBanner,
    _poll: poll,
  };
})();
