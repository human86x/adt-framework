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

  function create(sessionId) {
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

    // Fit after browser layout pass ensures correct dimensions
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

    // Listen for PTY output from Rust backend
    if (window.__TAURI__) {
      window.__TAURI__.event.listen(`pty-output-${sessionId}`, (event) => {
        term.write(event.payload);
      });

      window.__TAURI__.event.listen(`pty-closed-${sessionId}`, () => {
        term.write('\r\n\x1b[90m[Session ended]\x1b[0m\r\n');
      });
    }

    terminals.set(sessionId, { term, fitAddon, wrapper, resizeObserver });
    return term;
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
      setTimeout(() => {
        entry.fitAddon.fit();
        entry.term.focus();
      }, 100);
    }
  }

  function destroy(sessionId) {
    const entry = terminals.get(sessionId);
    if (entry) {
      entry.resizeObserver.disconnect();
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

  return { create, show, destroy, get, getSize };
})();