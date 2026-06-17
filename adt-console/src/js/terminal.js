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
    syncSize(sessionId, term);

    requestAnimationFrame(() => {
      fitAddon.fit();
      syncSize(sessionId, term);
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

    // Handle resize -> notify PTY (debounced to prevent rapid re-fitting)
    let resizeTimer = null;
    const resizeObserver = new ResizeObserver(() => {
      if (resizeTimer) clearTimeout(resizeTimer);
      resizeTimer = setTimeout(() => {
        fitAddon.fit();
        syncSize(sessionId, term);
      }, 50);
    });
    resizeObserver.observe(wrapper);

    // Listen for PTY output from Rust backend.
    // Await both listen() calls before replay() — event.listen() is async IPC;
    // calling replay() before it resolves drops the replayed bytes.
    if (window.__TAURI__) {
      await window.__TAURI__.event.listen(`pty-output-${sessionId}`, (event) => {
        term.write(event.payload);
      });

      await window.__TAURI__.event.listen(`pty-closed-${sessionId}`, () => {
        term.write('\r\n\x1b[90m[Session ended]\x1b[0m\r\n');
      });

      // SPEC-048 task_301: Request replay of recent output buffer
      replay(sessionId);
    }

    terminals.set(sessionId, { term, fitAddon, wrapper, resizeObserver });
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
      window.__TAURI__.core.invoke('resize_session', {
        request: {
          sessionId: sessionId,
          cols: term.cols,
          rows: term.rows,
        }
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
        // Skip syncSize if activate() just fired for this session — it already sent
        // one SIGWINCH. Sending another 100ms later causes Gemini to clear+redraw
        // again, which is the primary cause of the blank terminal bug.
        const now = Date.now();
        const timeSinceActive = now - (entry._activatedAt || 0);
        if (timeSinceActive > 300) {
          syncSize(sessionId, entry.term);
        }
        entry._activatedAt = now;
        entry._suppressResize = false;
        entry.term.focus();
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

    // Create the entry first so the listener closures can reference it.
    // _opened tracks whether term.open() has been called.
    // _pending buffers output that arrives before open() — writing to xterm.js
    // before open() feeds raw bytes into the parser state machine but nothing
    // is rendered until open() fires. For TUI agents (Gemini) the startup
    // sequence clears the screen; by the time open() renders the final state
    // the screen looks blank. We buffer here and flush immediately after open().
    const entry = { term, fitAddon, wrapper, resizeObserver: null, _prepared: true, _opened: false, _pending: [] };
    terminals.set(sessionId, entry);

    if (window.__TAURI__) {
      await window.__TAURI__.event.listen(`pty-output-${sessionId}`, (event) => {
        if (entry._opened) {
          entry.term.write(event.payload);
        } else {
          entry._pending.push(event.payload);
        }
      });
      await window.__TAURI__.event.listen(`pty-closed-${sessionId}`, () => {
        entry.term.write('\r\n\x1b[90m[Session ended]\x1b[0m\r\n');
      });
    }

    return term;
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
        });
        await window.__TAURI__.event.listen(`pty-closed-${sessionId}`, () => {
          entry.term.write('\r\n\x1b[90m[Session ended]\x1b[0m\r\n');
        });

        // SPEC-048 task_301: Request replay of recent output buffer
        replay(sessionId);
      }
    }

    const { term, fitAddon, wrapper } = entry;

    document.querySelectorAll('#terminal-container .terminal-wrapper.active').forEach(w => {
      w.classList.remove('active');
    });
    wrapper.classList.add('active');
    document.getElementById('terminal-container').appendChild(wrapper);

    term.open(wrapper);

    // Force synchronous reflow so fitAddon.fit() measures real pixel dimensions.
    wrapper.getBoundingClientRect();
    fitAddon.fit();

    // Flush buffered output BEFORE sending SIGWINCH so xterm.js has the old TUI
    // rendered before Gemini clears and redraws. This prevents the flicker window
    // where xterm.js is empty when the SIGWINCH clear-screen arrives.
    entry._opened = true;
    if (entry._pending && entry._pending.length > 0) {
      for (const chunk of entry._pending) {
        term.write(chunk);
      }
      entry._pending = [];
    }

    // ONE syncSize — sends SIGWINCH so Gemini redraws at the correct terminal size.
    // This is intentionally the ONLY syncSize call for a new session. show() will
    // skip its syncSize (via _justActivated) to avoid flooding Gemini with SIGWINCHs
    // that cause repeated clear+redraw cycles and a blank terminal.
    syncSize(sessionId, term);
    entry._activatedAt = Date.now();

    term.onData((data) => {
      if (window.__TAURI__) {
        window.__TAURI__.core.invoke('write_to_session', {
          request: { sessionId, data }
        }).catch(err => {
          term.write(`\r\n\x1b[31m[IPC Write Error: ${err}]\x1b[0m\r\n`);
        });
      }
    });

    requestAnimationFrame(() => {
      term.focus();
    });

    // Replay at 2000 ms: Gemini needs up to ~1-2s to finish redrawing after SIGWINCH.
    // Firing replay too early (250ms) catches Gemini mid-clear, leaving a blank screen.
    setTimeout(() => replay(sessionId), 2000);

    // Suppress ResizeObserver for the first 2.5s after activation.
    // When observe() is called below the wrapper already has real dimensions, so
    // ResizeObserver fires immediately and would send a second SIGWINCH at ~50ms —
    // right while Gemini is mid-TUI-draw — blanking the terminal.
    entry._suppressResize = true;
    setTimeout(() => { entry._suppressResize = false; }, 2500);

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

  return { create, prepare, activate, show, destroy, get, getSize };
})();