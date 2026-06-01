'use strict';

let TOKEN = '';
let logsVisible = false;
let logSource = null;

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

function login() {
  const val = document.getElementById('token-input').value.trim();
  if (!val) return;
  TOKEN = val;
  fetch('/api/status', { headers: { Authorization: `Bearer ${TOKEN}` } })
    .then(r => {
      if (r.status === 401) throw new Error('Unauthorized');
      return r.json();
    })
    .then(() => {
      document.getElementById('token-gate').style.display   = 'none';
      document.getElementById('main-header').style.display  = 'flex';
      document.getElementById('main-panel').style.display   = 'grid';
      startPolling();
    })
    .catch(() => {
      document.getElementById('token-error').textContent =
        '(\u256D\u255F_\u255F\u256E) invalid token, try again!';
      TOKEN = '';
    });
}

document.getElementById('token-input').addEventListener('keydown', e => {
  if (e.key === 'Enter') login();
});

// ---------------------------------------------------------------------------
// API helper
// ---------------------------------------------------------------------------

function apiFetch(path, opts = {}) {
  return fetch(path, {
    ...opts,
    headers: {
      Authorization: `Bearer ${TOKEN}`,
      'Content-Type': 'application/json',
      ...(opts.headers || {})
    }
  });
}

// ---------------------------------------------------------------------------
// Status polling
// ---------------------------------------------------------------------------

function startPolling() {
  fetchStatus();
  setInterval(fetchStatus, 5000);
}

function fetchStatus() {
  apiFetch('/api/status')
    .then(r => r.json())
    .then(data => {
      updateServiceStatus(data.service);
      updatePlayerCount(data.players, data.max_players);
      updateTimestamp(data.timestamp);
      updateRestartState(data.restart_in_progress, data.restart_log);
    })
    .catch(() => {});
}

function updateServiceStatus(service) {
  const pulse = document.getElementById('pulse');
  const svc   = document.getElementById('svc-status');
  svc.textContent = service;
  pulse.className = 'pulse';
  if (service === 'running') {
    pulse.classList.add('active');
    svc.style.color = 'var(--ok)';
  } else if (service === 'exited' || service === 'not found') {
    pulse.classList.add('failed');
    svc.style.color = 'var(--danger)';
  } else {
    pulse.classList.add('warn');
    svc.style.color = 'var(--warn)';
  }
}

function updatePlayerCount(players, maxPlayers) {
  const pc = document.getElementById('player-count');
  if (players === null) {
    pc.textContent = '\u2014';
    pc.className = 'stat-value muted';
  } else {
    pc.textContent = players;
    pc.className = 'stat-value accent';
  }
  document.getElementById('max-players').textContent = maxPlayers ?? '\u2014';
}

function updateTimestamp(timestamp) {
  document.getElementById('last-update').textContent =
    'last update: ' + new Date(timestamp).toLocaleTimeString();
}

function updateRestartState(inProgress, log) {
  const btn     = document.getElementById('btn-restart');
  const btnNow  = document.getElementById('btn-restart-now');
  const rs      = document.getElementById('restart-status');
  const logCard = document.getElementById('restart-log-card');
  const logBox  = document.getElementById('restart-log');

  if (inProgress) {
    btn.disabled    = true;
    btnNow.disabled = true;
    rs.style.display    = 'block';
    logCard.style.display = 'block';
  } else {
    btn.disabled    = false;
    btnNow.disabled = false;
    rs.style.display = 'none';
    if (log && log.length > 0) logCard.style.display = 'block';
  }

  if (log && log.length > 0) {
    logBox.innerHTML = log.map(line => {
      const cls = line.includes('Done') ? 'done' : line.includes('Error') ? 'err' : '';
      return `<span class="log-line ${cls}">${escHtml(line)}</span>`;
    }).join('');
    logBox.scrollTop = logBox.scrollHeight;
  }
}

// ---------------------------------------------------------------------------
// Log streaming
// ---------------------------------------------------------------------------

function toggleLogs(btn) {
  logsVisible = !logsVisible;
  document.getElementById('log-container').style.display = logsVisible ? 'block' : 'none';
  btn.textContent = logsVisible ? 'hide' : 'show';
  btn.classList.toggle('active', logsVisible);
  logsVisible ? startLogStream() : stopLogStream();
}

function startLogStream() {
  stopLogStream();
  const tail   = document.getElementById('log-tail').value || 100;
  const box    = document.getElementById('container-logs');
  const status = document.getElementById('stream-status');
  box.textContent = '';
  status.textContent = '\u2B24 connecting...';
  status.style.color = 'var(--warn)';

  logSource = new EventSource(`/api/logs/stream?tail=${tail}&token=${TOKEN}`);
  logSource.onopen = () => {
    status.textContent = '\u2B24 live';
    status.style.color = 'var(--ok)';
  };
  logSource.onmessage = e => {
    const line = document.createElement('div');
    line.textContent = e.data;
    box.appendChild(line);
    box.scrollTop = box.scrollHeight;
  };
  logSource.onerror = () => {
    status.textContent = '\u2B24 disconnected';
    status.style.color = 'var(--danger)';
  };
}

function stopLogStream() {
  if (logSource) { logSource.close(); logSource = null; }
  const status = document.getElementById('stream-status');
  status.textContent = '\u2B24 disconnected';
  status.style.color = 'var(--muted)';
}

// ---------------------------------------------------------------------------
// Restart
// ---------------------------------------------------------------------------

function confirmRestart()    { document.getElementById('confirm-overlay').classList.add('show'); }
function closeConfirm()      { document.getElementById('confirm-overlay').classList.remove('show'); }
function confirmRestartNow() { document.getElementById('confirm-now-overlay').classList.add('show'); }
function closeConfirmNow()   { document.getElementById('confirm-now-overlay').classList.remove('show'); }

function doRestart() {
  closeConfirm();
  apiFetch('/api/restart', { method: 'POST' })
    .then(r => r.json())
    .then(() => fetchStatus())
    .catch(() => {});
}

function doRestartNow() {
  closeConfirmNow();
  apiFetch('/api/restart-now', { method: 'POST' })
    .then(r => r.json())
    .then(() => fetchStatus())
    .catch(() => {});
}

// ---------------------------------------------------------------------------
// RCON command
// ---------------------------------------------------------------------------

function sendCommand() {
  const input = document.getElementById('cmd-input');
  const cmd   = input.value.trim();
  if (!cmd) return;
  const out = document.getElementById('cmd-output');
  out.textContent = 'sending~ \u2661';
  apiFetch('/api/command', { method: 'POST', body: JSON.stringify({ command: cmd }) })
    .then(r => r.json())
    .then(data => { out.textContent = data.output || '(no output)'; input.value = ''; })
    .catch(() => { out.textContent = '(T⌓T) something went wrong'; });
}

document.getElementById('cmd-input').addEventListener('keydown', e => {
  if (e.key === 'Enter') sendCommand();
});

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

function escHtml(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
