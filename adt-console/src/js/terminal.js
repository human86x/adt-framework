// Terminal manager — xterm.js wrapper
// SPEC-021: PTY <-> xterm.js bridge

const TerminalManager = (() => {
  const terminals = new Map();

  const THEME = {
    background: '#0d1117',
    foreground: '#e6edf3',
    cursor: '#e6edf3',
    selectionBackground: '#264f78',
    black: '#484f58',
    red: '#f85149',
    green: '#4CAF50',
    yellow: '#d29922',
    blue: '#6B7FD7',
    magenta: '#bc8cff',
    cyan: '#76e3ea',
    white: '#e6edf3',
    brightBlack: '#6e7681',
    brightRed: '#ffa198',
    brightGreen: '#56d364',
    brightYellow: '#e3b341',
    brightBlue: '#79c0ff',
    brightMagenta: '#d2a8ff',
    brightCyan: '#b3f0ff',
    brightWhite: '#f0f6fc',
  };

  async function create(sessionId) {
    const term = new Terminal({
      theme: THEME,
      fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', 'Consolas', monospace",
      fontSize: 16,
      lineHeight: 1.2,
      cursorBlink: true,
      cursorStyle: 'block',
      scrollback: 10000,
      allowProposedApi: true,
    });

    // Disable focus reporting which sends \x1b[I and \x1b[O
    // These confuse many CLI tools when received as stdin
    term.options.focusReport = false;

    const fitAddon = new FitAddon.FitAddon();
    term.loadAddon(fitAddon);

    // Create DOM wrapper — must be VISIBLE before term.open() so xterm.js
    // can measure font/cell dimensions correctly for row/col calculation
    const wrapper = document.createElement('div');
    wrapper.id = `terminal-${sessionId}`;
    wrapper.className = 'terminal-wrapper active';

    // Deactivate other wrappers so only this one is visible
    document.querySelectorAll('#terminal-container .terminal-wrapper.active').forEach(w => {
      w.classList.remove('active');
    });

    document.getElementById('terminal-container').appendChild(wrapper);

    term.open(wrapper);

    // Synchronous fit before any output arrives.
    wrapper.getBoundingClientRect();
    fitAddon.fit();
    // ONE syncSize — sends SIGWINCH so the PTY knows the real terminal size.
    // Do NOT call syncSize again in requestAnimationFrame: a second SIGWINCH while
    // Gemini is processing the first one causes a blank screen.
    syncSize(sessionId, term);

    requestAnimationFrame(() => {
      fitAddon.fit();
      term.focus();
    });

    // Handle user input -> send to PTY via Tauri IPC
    term.onData((data) => {
      if (window.__TAURI__) {
        window.__TAURI__.core.invoke('write_to_session', {
          request: {
            sessionId: sessionId,
            data: data,
          }
        }).catch(err => {
          term.write(`\r\n\x1b[31m[IPC Write Error: ${err}]\x1b[0m\r\n`);
        });
      }
    });

    // Create entry before ResizeObserver so the closure can reference _suppressResize.
    // _suppressResize is set true for 8s to protect Gemini's initial TUI draw
    // from spurious ResizeObserver-triggered SIGWINCHes (same as activate() path).
    const entry = { term, fitAddon, wrapper, resizeObserver: null,
                    _suppressResize: true, _activatedAt: Date.now() };
    terminals.set(sessionId, entry);
    setTimeout(() => { entry._suppressResize = false; }, 8000);

    // Handle resize -> notify PTY (debounced, guarded against the initial suppress window)
    let resizeTimer = null;
    const resizeObserver = new ResizeObserver(() => {
      if (entry._suppressResize) return;
      if (resizeTimer) clearTimeout(resizeTimer);
      resizeTimer = setTimeout(() => {
        fitAddon.fit();
        syncSize(sessionId, term);
      }, 50);
    });
    resizeObserver.observe(wrapper);
    entry.resizeObserver = resizeObserver;

    // Listen for PTY output from Rust backend.
    // Await both listen() calls before replay() — event.listen() is async IPC;
    // calling replay() before it resolves drops the replayed bytes.
    if (window.__TAURI__) {
      await window.__TAURI__.event.listen(`pty-output-${sessionId}`, (event) => {
        term.write(event.payload);
        term.scrollToBottom();
      });

      await window.__TAURI__.event.listen(`pty-closed-${sessionId}`, () => {
        term.write('\r\n\x1b[90m[Session ended]\x1b[0m\r\n');
      });

      // SPEC-048 task_301: Request replay of recent output buffer
      replay(sessionId);
    }

    return term;
  }

  function replay(sessionId) {
    if (window.__TAURI__) {
      window.__TAURI__.core.invoke('replay_session_output', {
        request: { sessionId: sessionId }
      }).catch(err => console.error('[JS REPLAY ERROR]:', err));
    }
  }

  function syncSize(sessionId, term) {
    if (window.__TAURI__) {
      const entry = terminals.get(sessionId);
      window.__TAURI__.core.invoke('resize_session', {
        request: {
          sessionId: sessionId,
          cols: term.cols,
          rows: term.rows,
        }
      }).then(() => {
        if (entry) { entry._lastCols = term.cols; entry._lastRows = term.rows; }
      }).catch(err => console.error('[JS RESIZE ERROR]:', err));
    }
  }

  // Handle window resize globally
  window.addEventListener('resize', () => {
    terminals.forEach(t => {
      if (t.wrapper.classList.contains('active')) {
        t.fitAddon.fit();
      }
    });
  });

  function show(sessionId) {
    terminals.forEach((t, id) => {
      t.wrapper.classList.toggle('active', id === sessionId);
    });
    const entry = terminals.get(sessionId);
    if (entry) {
      // Suppress ResizeObserver SIGWINCH during the tab-switch window — the wrapper
      // going from display:none → display:block fires ResizeObserver which would send
      // a spurious second SIGWINCH that blanks Gemini's TUI.
      entry._suppressResize = true;
      setTimeout(() => {
        entry.fitAddon.fit();
        // Only send SIGWINCH if the size genuinely changed AND we are outside the
        // activate() suppress window (8s). Within that window activate() already
        // sent the correct size and Gemini is still mid-draw — a second SIGWINCH here
        // clears the screen before the first draw completes, leaving a blank terminal.
        const now = Date.now();
        const sizeChanged = entry.term.cols !== (entry._lastCols || 0)
                         || entry.term.rows !== (entry._lastRows || 0);
        if ((now - (entry._activatedAt || 0) > 8000) && sizeChanged) {
          syncSize(sessionId, entry.term);
        }
        entry.term.focus();
        // Only re-enable ResizeObserver if we are outside activate()'s 8s protect
        // window. If show() is called during that window (e.g. immediately after session
        // creation via switchTo), letting the 250ms timer fire here would prematurely
        // end the suppression and allow layout-shift ResizeObserver events to fire
        // SIGWINCHes while Gemini is still drawing — blanking the screen.
        // activate()'s own 8s timer is the sole owner of re-enabling in that case.
        setTimeout(() => {
          if (entry && Date.now() > ((entry._activatedAt || 0) + 8000)) {
            entry._suppressResize = false;
          }
        }, 250);
      }, 100);
    }
  }

  function destroy(sessionId) {
    const entry = terminals.get(sessionId);
    if (entry) {
      if (entry.resizeObserver) entry.resizeObserver.disconnect();
      entry.term.dispose();
      entry.wrapper.remove();
      terminals.delete(sessionId);
    }
  }

  function get(sessionId) {
    return terminals.get(sessionId)?.term;
  }

  function getSize(sessionId) {
    const entry = terminals.get(sessionId);
    if (entry) {
      return { cols: entry.term.cols, rows: entry.term.rows };
    }
    return { cols: 80, rows: 24 };
  }

  // SPEC-048 §4.2: Register PTY listeners BEFORE invoking spawn_child_session so the
  // first bytes of the child's banner are not dropped.  xterm.write() is safe before
  // term.open() — the data is buffered and flushed when activate() calls term.open().
  // MUST be async and awaited by callers: event.listen() is an async IPC call and the
  // listener is not active until its promise resolves. Calling it without await races
  // against PTY output (Gemini in particular emits its TUI banner immediately).
  async function prepare(sessionId) {
    const term = new Terminal({
      theme: THEME,
      fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', 'Consolas', monospace",
      fontSize: 16,
      lineHeight: 1.2,
      cursorBlink: true,
      cursorStyle: 'block',
      scrollback: 10000,
      allowProposedApi: true,
    });
    term.options.focusReport = false;

    const fitAddon = new FitAddon.FitAddon();
    term.loadAddon(fitAddon);

    const wrapper = document.createElement('div');
    wrapper.id = `terminal-${sessionId}`;
    wrapper.className = 'terminal-wrapper';
    wrapper.style.position = 'relative';

    // Startup status overlay — shown until first PTY bytes arrive, giving the
    // user real-time feedback during Gemini's OAuth + relaunch startup sequence.
    const overlay = document.createElement('div');
    overlay.style.cssText = [
      'position:absolute', 'inset:0', 'display:flex', 'flex-direction:column',
      'align-items:center', 'justify-content:center', 'z-index:10',
      'background:rgba(13,17,23,0.93)', 'pointer-events:none',
      'transition:opacity 0.4s', 'font-family:monospace',
    ].join(';');
    overlay.innerHTML = `
      <div style="color:#6e7681;font-size:13px;margin-bottom:6px" class="adt-startup-phase">Spawning process...</div>
      <div style="color:#484f58;font-size:11px" class="adt-startup-timer">0.0s</div>
    `;
    wrapper.appendChild(overlay);
    const overlayStart = Date.now();
    const overlayTimer = setInterval(() => {
      const el = overlay.querySelector('.adt-startup-timer');
      if (el) el.textContent = `${((Date.now() - overlayStart) / 1000).toFixed(1)}s`;
    }, 100);

    // Create the entry first so the listener closures can reference it.
    // _opened tracks whether term.open() has been called.
    // _pending buffers output that arrives before open() — writing to xterm.js
    // before open() feeds raw bytes into the parser state machine but nothing
    // is rendered until open() fires. For TUI agents (Gemini) the startup
    // sequence clears the screen; by the time open() renders the final state
    // the screen looks blank. We buffer here and flush immediately after open().
    const entry = {
      term, fitAddon, wrapper, resizeObserver: null,
      _prepared: true, _opened: false, _pending: [],
      _startupOverlay: overlay, _startupOverlayTimer: overlayTimer,
    };
    terminals.set(sessionId, entry);

    if (window.__TAURI__) {
      await window.__TAURI__.event.listen(`pty-output-${sessionId}`, (event) => {
        // Dismiss startup overlay on first real PTY bytes
        if (entry._startupOverlay) {
          clearInterval(entry._startupOverlayTimer);
          entry._startupOverlay.style.opacity = '0';
          setTimeout(() => {
            if (entry._startupOverlay) { entry._startupOverlay.remove(); entry._startupOverlay = null; }
          }, 400);
        }
        if (entry._opened) {
          entry.term.write(event.payload);
          entry.term.scrollToBottom();
        } else {
          entry._pending.push(event.payload);
        }
      });
      await window.__TAURI__.event.listen(`pty-closed-${sessionId}`, () => {
        if (entry._startupOverlay) {
          clearInterval(entry._startupOverlayTimer);
          entry._startupOverlay.remove();
          entry._startupOverlay = null;
        }
        entry.term.write('\r\n\x1b[90m[Session ended]\x1b[0m\r\n');
      });
    }

    return term;
  }

  function setStartupPhase(sessionId, phase) {
    const entry = terminals.get(sessionId);
    if (entry && entry._startupOverlay) {
      const el = entry._startupOverlay.querySelector('.adt-startup-phase');
      if (el) el.textContent = phase;
    }
  }

  // Mount a previously prepare()d terminal to the DOM and open it.
  // If preparedId differs from sessionId (Rust used its own id), renames the map entry.
  // Async so callers can await listener registration in the re-registration and fallback paths.
  async function activate(sessionId, preparedId) {
    const lookupId = preparedId || sessionId;
    const entry = terminals.get(lookupId);

    if (!entry || !entry._prepared) {
      return await create(sessionId);
    }

    if (lookupId !== sessionId) {
      terminals.delete(lookupId);
      entry.wrapper.id = `terminal-${sessionId}`;
      terminals.set(sessionId, entry);
      // Re-register PTY listeners for the real session ID (Rust may not have honoured reservedId).
      // Await both before replay() to avoid the same race as in prepare().
      if (window.__TAURI__) {
        await window.__TAURI__.event.listen(`pty-output-${sessionId}`, (event) => {
          entry.term.write(event.payload);
          entry.term.scrollToBottom();
        });
        await window.__TAURI__.event.listen(`pty-closed-${sessionId}`, () => {
          entry.term.write('\r\n\x1b[90m[Session ended]\x1b[0m\r\n');
        });

        // SPEC-048 task_301: Request replay of recent output buffer
        replay(sessionId);
      }
    }

    const { term, fitAddon, wrapper } = entry;

    // Update startup overlay to "Activating..." phase while we open xterm.js
    if (entry._startupOverlay) {
      const phaseEl = entry._startupOverlay.querySelector('.adt-startup-phase');
      if (phaseEl) phaseEl.textContent = 'Waiting for Gemini TUI...';
    }

    document.querySelectorAll('#terminal-container .terminal-wrapper.active').forEach(w => {
      w.classList.remove('active');
    });
    wrapper.classList.add('active');
    document.getElementById('terminal-container').appendChild(wrapper);

    term.open(wrapper);

    // Force synchronous reflow so fitAddon.fit() measures real pixel dimensions.
    wrapper.getBoundingClientRect();
    fitAddon.fit();

    // Register onData BEFORE flushing _pending. xterm.js generates terminal
    // capability responses (DA1 etc.) when processing the initial Gemini output —
    // if the handler is not yet registered those bytes are silently dropped and
    // Gemini hangs waiting for capability negotiation it never receives.
    term.onData((data) => {
      if (window.__TAURI__) {
        window.__TAURI__.core.invoke('write_to_session', {
          request: { sessionId, data }
        }).catch(err => {
          term.write(`\r\n\x1b[31m[IPC Write Error: ${err}]\x1b[0m\r\n`);
        });
      }
    });

    // Flush buffered output BEFORE sending SIGWINCH so xterm.js has the old TUI
    // rendered before Gemini clears and redraws. This prevents the flicker window
    // where xterm.js is empty when the SIGWINCH clear-screen arrives.
    entry._opened = true;
    if (entry._pending && entry._pending.length > 0) {
      for (const chunk of entry._pending) {
        term.write(chunk);
      }
      entry._pending = [];
      // Dismiss overlay — buffered output means TUI is already rendered underneath
      if (entry._startupOverlay) {
        clearInterval(entry._startupOverlayTimer);
        entry._startupOverlay.style.opacity = '0';
        setTimeout(() => {
          if (entry._startupOverlay) { entry._startupOverlay.remove(); entry._startupOverlay = null; }
        }, 400);
      }
    }

    // ONE syncSize — sends SIGWINCH so Gemini redraws at the correct terminal size.
    syncSize(sessionId, term);
    entry._activatedAt = Date.now();

    requestAnimationFrame(() => {
      term.focus();
    });

    // Suppress ResizeObserver for 8s after activation. Gemini's startup sequence
    // (parent init → OAuth refresh → relaunch → child TUI draw) takes 2-5+ seconds;
    // the old 2500ms window expired before the TUI was ready, so a subsequent resize
    // event sent a SIGWINCH mid-draw that blanked the terminal.
    entry._suppressResize = true;
    setTimeout(() => { entry._suppressResize = false; }, 8000);

    let resizeTimer = null;
    const resizeObserver = new ResizeObserver(() => {
      if (entry._suppressResize) return;
      if (resizeTimer) clearTimeout(resizeTimer);
      resizeTimer = setTimeout(() => { fitAddon.fit(); syncSize(sessionId, term); }, 50);
    });
    resizeObserver.observe(wrapper);
    entry.resizeObserver = resizeObserver;
    entry._prepared = false;

    return term;
  }

  return { create, prepare, activate, show, destroy, get, getSize, setStartupPhase };
})();