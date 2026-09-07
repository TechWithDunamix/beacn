/**
 * TS SDK tests — against a fake BEACN realtime server (the WS protocol subset),
 * so the client's state machine, subscribe flow, replay and reconnection are
 * exercised without the Python backend.
 */

import assert from "node:assert/strict";
import test from "node:test";
import { WebSocketServer, WebSocket as NodeWS } from "ws";
import { Beacn, type ConnectionState } from "../src/beacn.js";

interface FakeServer {
  port: number;
  close: () => Promise<void>;
  published: (topic: string, event: Record<string, unknown>) => void;
  drop: () => void;
  connections: number;
}

function startServer(opts: { rejectToken?: string } = {}): Promise<FakeServer> {
  return new Promise((resolve) => {
    const wss = new WebSocketServer({ port: 0 });
    const sockets = new Set<NodeWS>();
    const subs = new Map<NodeWS, Set<string>>();
    let connections = 0;

    wss.on("connection", (ws, req) => {
      connections += 1;
      sockets.add(ws);
      subs.set(ws, new Set());
      const url = new URL(req.url ?? "/", "http://x");
      const token = url.searchParams.get("token");
      if (opts.rejectToken && token === opts.rejectToken) {
        ws.send(JSON.stringify({ type: "error", code: "unauthenticated", message: "bad token" }));
        ws.close(1008, "bad token");
        return;
      }
      ws.send(JSON.stringify({ type: "welcome", connection_id: "con_test", heartbeat_ms: 20000 }));
      ws.on("message", (raw) => {
        const frame = JSON.parse(raw.toString());
        if (frame.type === "subscribe") {
          subs.get(ws)!.add(frame.topic);
          ws.send(JSON.stringify({ type: "subscribed", topic: frame.topic, ref: frame.ref }));
        } else if (frame.type === "unsubscribe") {
          subs.get(ws)!.delete(frame.topic);
          ws.send(JSON.stringify({ type: "unsubscribed", topic: frame.topic }));
        } else if (frame.type === "replay") {
          ws.send(JSON.stringify({
            type: "event", id: "evt_replayed", event: "replayed.evt",
            topic: frame.topic, kind: "event", timestamp: "2026-01-01T00:00:00Z", data: {},
          }));
          ws.send(JSON.stringify({
            type: "replay_done", topic: frame.topic, count: 1, truncated: false, next_since: null,
          }));
        } else if (frame.type === "ping") {
          ws.send(JSON.stringify({ type: "pong" }));
        }
      });
      ws.on("close", () => {
        sockets.delete(ws);
        subs.delete(ws);
      });
    });

    wss.on("listening", () => {
      const addr = wss.address();
      const port = typeof addr === "object" && addr ? addr.port : 0;
      resolve({
        port,
        get connections() {
          return connections;
        },
        close: () =>
          new Promise((r) => {
            for (const s of sockets) s.terminate();
            wss.close(() => r());
          }),
        published: (topic, event) => {
          const payload = JSON.stringify({ type: "event", topic, ...event });
          for (const [ws, topics] of subs) {
            if (topics.has(topic) && ws.readyState === 1) ws.send(payload);
          }
        },
        drop: () => {
          for (const s of sockets) s.terminate();
        },
      });
    });
  });
}

function client(server: FakeServer, extra: Record<string, unknown> = {}) {
  return new Beacn({
    url: `ws://127.0.0.1:${server.port}`,
    token: "good-token",
    WebSocketImpl: NodeWS as unknown as typeof WebSocket,
    reconnectBaseMs: 20,
    ...extra,
  });
}

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

test("connects and reports state transitions", async () => {
  const server = await startServer();
  const states: ConnectionState[] = [];
  const beacn = client(server);
  beacn.onStateChange((s) => states.push(s));
  await beacn.connect();
  assert.equal(beacn.state, "CONNECTED");
  assert.ok(states.includes("CONNECTING"));
  assert.ok(states.includes("CONNECTED"));
  assert.equal(beacn.connectionId, "con_test");
  beacn.disconnect();
  await server.close();
});

test("subscribe then receive matching events", async () => {
  const server = await startServer();
  const beacn = client(server);
  const got: string[] = [];
  const channel = beacn.channel("tasks");
  channel.on("task.completed", (e) => got.push(e.id));
  channel.onAny((e) => got.push("any:" + e.event));
  await channel.subscribe();
  server.published("tasks", { id: "evt_1", event: "task.completed", kind: "task", timestamp: "t", data: {} });
  server.published("tasks", { id: "evt_2", event: "task.started", kind: "task", timestamp: "t", data: {} });
  server.published("other", { id: "evt_3", event: "task.completed", kind: "task", timestamp: "t", data: {} });
  await wait(50);
  assert.deepEqual(got.sort(), ["any:task.completed", "any:task.started", "evt_1"].sort());
  beacn.disconnect();
  await server.close();
});

test("rejected token surfaces as an error", async () => {
  const server = await startServer({ rejectToken: "bad" });
  const beacn = client(server, { token: "bad" });
  await assert.rejects(() => beacn.connect(), /bad token|closed/);
  beacn.disconnect();
  await server.close();
});

test("reconnects after a drop and resubscribes + replays", async () => {
  const server = await startServer();
  const beacn = client(server);
  const events: string[] = [];
  const states: ConnectionState[] = [];
  beacn.onStateChange((s) => states.push(s));
  const channel = beacn.channel("stream");
  channel.onAny((e) => events.push(e.id));
  await channel.subscribe();

  server.published("stream", { id: "evt_live1", event: "x.y", kind: "event", timestamp: "t", data: {} });
  await wait(30);
  server.drop();
  await wait(200); // reconnect + resubscribe + replay
  assert.equal(beacn.state, "CONNECTED");
  assert.ok(states.includes("RECONNECTING"));
  assert.ok(events.includes("evt_replayed"), "replay after reconnect delivered");
  assert.ok(server.connections >= 2, "server saw a second connection");
  beacn.disconnect();
  await server.close();
});

test("maxReconnectAttempts leads to FAILED", async () => {
  const server = await startServer();
  const beacn = client(server, { maxReconnectAttempts: 1 });
  await beacn.connect();
  await server.close(); // kill it so reconnects fail
  await wait(300);
  assert.equal(beacn.state, "FAILED");
  beacn.disconnect();
});
