const assert = require('assert').strict;
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const context = {
  console: console, setTimeout: setTimeout, setInterval: setInterval, clearInterval: clearInterval,
  Date: Date, Math: Math,
  fetch: async () => ({ ok: true, json: async () => ({ tasks: [], events: [] }) }),
  window: { addEventListener: () => {} },
  document: {
    getElementById: () => ({ textContent: '', innerHTML: '', appendChild: () => {}, classList: { add: () => {}, remove: () => {}, toggle: () => {} }, addEventListener: () => {}, showModal: () => {}, close: () => {}, dataset: {}, style: { display: '' }, querySelector: () => null }),
    querySelectorAll: () => [],
    createElement: () => ({ innerHTML: '', appendChild: () => {}, addEventListener: () => {}, dataset: {}, classList: { toggle: () => {} } }),
    activeElement: { tagName: '' }
  },
  Terminal: class { 
    constructor() {}
    loadAddon() {}
    open() {}
    write() {}
    dispose() {}
    onData() {}
    onResize() {}
  },
  FitAddon: { FitAddon: class { constructor() {} } },
  ToastManager: { show: () => {} }
};
context.window.window = context.window;
context.addEventListener = () => {};
vm.createContext(context);

const scripts = [
    ['TerminalManager', 'terminal.js'],
    ['SessionManager', 'sessions.js'],
    ['DashboardManager', 'dashboard.js'],
    ['ContextPanel', 'context.js']
];

scripts.forEach(([name, file]) => {
    const fullPath = path.join(__dirname, '..', 'src', 'js', file);
    let code = fs.readFileSync(fullPath, 'utf8');
    code = code.replace(`const ${name} =`, `this.${name} =`);
    vm.runInContext(code, context, { filename: file });
});

async function runTests() {
  console.log("Running ADT Console JS Unit Tests...");
  try {
    const session = await context.SessionManager.create('claude', 'Backend_Engineer', 'bash', '/tmp');
    assert.ok(session, "Session created");
    console.log("✓ SessionManager: session creation ok");
    console.log("All JS logic tests passed!");
  } catch (err) {
    console.error("\nTest failure:", err);
    process.exit(1);
  }
}
runTests();
