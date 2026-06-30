// ASTRA-IDE Collaboration Server
// ──────────────────────────────────────────────────────────────────────────
// Relays Yjs CRDT updates between connected Monaco editors and forwards
// awareness state (cursors, selections) to all peers in the same room.
//
// Each "room" maps 1:1 to a workspace (workspace.yjs_room field in the
// backend DB). The y-websocket utility handles sync + awareness; we add
// a thin transport layer + per-room access logging.
//
// Run:  npm start   (default port 1234)
// Env:  PORT, HOST, MAX_PAYLOAD_KB

const http = require('http');
const WebSocket = require('ws');
const { setupWSConnection, setPersistence } = require('y-websocket/bin/utils');

// Optional durable persistence (B7). When YPERSISTENCE_DIR is set, each room's Yjs
// document is kept on disk (LevelDB) so it survives collab-server restarts (point it
// at a mounted volume / PVC in production). Fully guarded: if the flag is unset or
// y-leveldb is not installed, the server runs in memory exactly as before.
if (process.env.YPERSISTENCE_DIR) {
  try {
    const Y = require('yjs');
    const { LeveldbPersistence } = require('y-leveldb');
    const ldb = new LeveldbPersistence(process.env.YPERSISTENCE_DIR);
    setPersistence({
      provider: ldb,
      bindState: async (docName, ydoc) => {
        const persisted = await ldb.getYDoc(docName);
        const current = Y.encodeStateAsUpdate(ydoc);
        await ldb.storeUpdate(docName, current);
        Y.applyUpdate(ydoc, Y.encodeStateAsUpdate(persisted));
        ydoc.on('update', (update) => { ldb.storeUpdate(docName, update); });
      },
      writeState: async () => {},
    });
    console.log(`[persistence] LevelDB enabled at ${process.env.YPERSISTENCE_DIR}`);
  } catch (e) {
    console.warn('[persistence] disabled (run npm install to add y-leveldb):', e.message);
  }
}

const PORT            = parseInt(process.env.PORT || '1234', 10);
const HOST            = process.env.HOST || '0.0.0.0';
const MAX_PAYLOAD_KB  = parseInt(process.env.MAX_PAYLOAD_KB || '512', 10);

// ── Per-room connection stats (for /stats endpoint and logging) ─────────────
const roomStats = new Map(); // roomName → { connections, lastActivity }

function touchRoom(roomName) {
  const existing = roomStats.get(roomName) || { connections: 0, lastActivity: Date.now() };
  existing.lastActivity = Date.now();
  roomStats.set(roomName, existing);
}

// ── HTTP server (health + stats endpoints) ─────────────────────────────────
const server = http.createServer((req, res) => {
  if (req.url === '/healthz') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ status: 'ok', service: 'astra-collab-server', rooms: roomStats.size }));
    return;
  }

  if (req.url === '/stats') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    const rooms = Array.from(roomStats.entries()).map(([name, s]) => ({
      room:          name,
      connections:   s.connections,
      last_activity: new Date(s.lastActivity).toISOString(),
    }));
    res.end(JSON.stringify({ total_rooms: rooms.length, rooms }, null, 2));
    return;
  }

  res.writeHead(404);
  res.end('Not Found');
});

// ── WebSocket server ────────────────────────────────────────────────────────
const wss = new WebSocket.Server({
  noServer: true,
  maxPayload: MAX_PAYLOAD_KB * 1024,
});

server.on('upgrade', (request, socket, head) => {
  // URL pattern:  /<roomName>
  const url = new URL(request.url, `http://${request.headers.host}`);
  const roomName = url.pathname.slice(1) || 'default';

  if (!/^[a-zA-Z0-9_-]{1,128}$/.test(roomName)) {
    socket.write('HTTP/1.1 400 Bad Request\r\n\r\n');
    socket.destroy();
    return;
  }

  wss.handleUpgrade(request, socket, head, (ws) => {
    const stats = roomStats.get(roomName) || { connections: 0, lastActivity: Date.now() };
    stats.connections += 1;
    roomStats.set(roomName, stats);
    touchRoom(roomName);

    console.log(`[+] room=${roomName} connections=${stats.connections}`);

    ws.on('close', () => {
      const s = roomStats.get(roomName);
      if (s) {
        s.connections = Math.max(0, s.connections - 1);
        touchRoom(roomName);
        console.log(`[-] room=${roomName} connections=${s.connections}`);
      }
    });

    // Delegate sync/awareness to y-websocket's utility (handles all CRDT logic)
    setupWSConnection(ws, request, {
      docName: roomName,
      gc: true,    // garbage-collect tombstones for old deletes
    });
  });
});

// ── Idle-room cleanup (every 5 min) ────────────────────────────────────────
const IDLE_MS = 30 * 60 * 1000;  // 30 minutes
setInterval(() => {
  const now = Date.now();
  for (const [name, s] of roomStats.entries()) {
    if (s.connections === 0 && now - s.lastActivity > IDLE_MS) {
      roomStats.delete(name);
      console.log(`[gc] removed idle room=${name}`);
    }
  }
}, 5 * 60 * 1000);

server.listen(PORT, HOST, () => {
  console.log(`ASTRA-IDE collab server listening on ws://${HOST}:${PORT}`);
  console.log(`  GET  http://${HOST}:${PORT}/healthz`);
  console.log(`  GET  http://${HOST}:${PORT}/stats`);
});
