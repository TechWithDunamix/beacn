/**
 * BEACN — official TypeScript / JavaScript client SDK.
 *
 * Browser-first: uses the global `WebSocket` and `fetch`. For Node or tests,
 * pass `WebSocketImpl` / `fetchImpl` in the options.
 *
 *   const beacn = new Beacn({ url: "wss://beacn.example.com", token });
 *   const channel = beacn.channel("tasks");
 *   channel.on("task.completed", (event) => console.log(event));
 *   await channel.subscribe();
 */

export type ConnectionState =
  | "CONNECTING"
  | "CONNECTED"
  | "RECONNECTING"
  | "DISCONNECTED"
  | "FAILED";

export interface BeacnEvent {
  id: string;
  event: string;
  topic: string;
  kind: "event" | "task" | "notification" | "message";
  producer?: string;
  environment?: string;
  timestamp: string;
  severity?: string;
  schema_version?: string;
  data: Record<string, unknown>;
  seq?: number;
  correlation_id?: string;
  [key: string]: unknown;
}

export interface BeacnOptions {
  /** `wss://host` for realtime, or `https://host` — both are accepted. */
  url: string;
  /** A realtime JWT (from POST /api/v1/realtime/tokens) or a `bk_` API key. */
  token: string;
  /** Called to obtain a fresh token before each (re)connect. Overrides `token`. */
  getToken?: () => string | Promise<string>;
  /** Max reconnect attempts before the state becomes FAILED. Default: Infinity. */
  maxReconnectAttempts?: number;
  /** Base backoff in ms (full-jitter, capped at 15s). Default: 500. */
  reconnectBaseMs?: number;
  /** Answer server heartbeats with a ping when idle. Default: true. */
  heartbeat?: boolean;
  /** Inject a WebSocket implementation (Node/tests). Default: globalThis.WebSocket. */
  WebSocketImpl?: typeof WebSocket;
  /** Inject fetch (Node < 18 / tests). Default: globalThis.fetch. */
  fetchImpl?: typeof fetch;
  /** console-like logger. Default: no-op. */
  logger?: { debug: (...a: unknown[]) => void; warn: (...a: unknown[]) => void };
}

type Handler = (event: BeacnEvent) => void;
type StateHandler = (state: ConnectionState) => void;

interface Pending {
  resolve: () => void;
  reject: (e: Error) => void;
}

const noopLogger = { debug: () => {}, warn: () => {} };

export class BeacnError extends Error {
  code: string;
  constructor(message: string, code = "error") {
    super(message);
    this.name = "BeacnError";
    this.code = code;
  }
}

/**
 * A subscription to one topic. Register handlers with `.on(name, fn)` or
 * `.onAny(fn)`, then `await channel.subscribe()`.
 */
export class Channel {
  readonly topic: string;
  private beacn: Beacn;
  private handlers = new Map<string, Set<Handler>>();
  private anyHandlers = new Set<Handler>();
  subscribed = false;

  constructor(beacn: Beacn, topic: string) {
    this.beacn = beacn;
    this.topic = topic;
  }

  on(eventName: string, handler: Handler): this {
    let set = this.handlers.get(eventName);
    if (!set) {
      set = new Set();
      this.handlers.set(eventName, set);
    }
    set.add(handler);
    return this;
  }

  onAny(handler: Handler): this {
    this.anyHandlers.add(handler);
    return this;
  }

  off(eventName: string, handler: Handler): this {
    this.handlers.get(eventName)?.delete(handler);
    return this;
  }

  /** @internal */
  _dispatch(event: BeacnEvent): void {
    for (const h of this.anyHandlers) safe(h, event);
    const set = this.handlers.get(event.event);
    if (set) for (const h of set) safe(h, event);
  }

  async subscribe(): Promise<void> {
    await this.beacn._subscribe(this.topic);
    this.subscribed = true;
  }

  async unsubscribe(): Promise<void> {
    await this.beacn._unsubscribe(this.topic);
    this.subscribed = false;
  }

  /** Ask the server to replay persisted events on this topic since `sinceId`. */
  async replay(sinceId?: string): Promise<void> {
    await this.beacn._replay(this.topic, sinceId);
  }
}

export class Beacn {
  private opts: Required<Pick<BeacnOptions, "maxReconnectAttempts" | "reconnectBaseMs" | "heartbeat">> &
    BeacnOptions;
  private ws?: WebSocket;
  private WS: typeof WebSocket;
  private _state: ConnectionState = "DISCONNECTED";
  private channels = new Map<string, Channel>();
  private stateHandlers = new Set<StateHandler>();
  private pending = new Map<string, Pending>();
  private lastEventId = new Map<string, string>();
  private attempts = 0;
  private closedByUser = false;
  private heartbeatTimer?: ReturnType<typeof setInterval>;
  private log: NonNullable<BeacnOptions["logger"]>;
  connectionId?: string;

  constructor(options: BeacnOptions) {
    const WS = options.WebSocketImpl ?? (globalThis as { WebSocket?: typeof WebSocket }).WebSocket;
    if (!WS) throw new BeacnError("no WebSocket implementation available", "no_websocket");
    this.WS = WS;
    this.log = options.logger ?? noopLogger;
    this.opts = {
      maxReconnectAttempts: options.maxReconnectAttempts ?? Infinity,
      reconnectBaseMs: options.reconnectBaseMs ?? 500,
      heartbeat: options.heartbeat ?? true,
      ...options,
    };
  }

  get state(): ConnectionState {
    return this._state;
  }

  onStateChange(handler: StateHandler): () => void {
    this.stateHandlers.add(handler);
    return () => this.stateHandlers.delete(handler);
  }

  channel(topic: string): Channel {
    let ch = this.channels.get(topic);
    if (!ch) {
      ch = new Channel(this, topic);
      this.channels.set(topic, ch);
    }
    return ch;
  }

  /** Open the connection. Resolves once the server sends `welcome`. */
  connect(): Promise<void> {
    this.closedByUser = false;
    return this._open();
  }

  /** Close and do not reconnect. */
  disconnect(): void {
    this.closedByUser = true;
    this._stopHeartbeat();
    this.ws?.close(1000, "client disconnect");
    this._setState("DISCONNECTED");
  }

  private async _resolveToken(): Promise<string> {
    if (this.opts.getToken) return await this.opts.getToken();
    return this.opts.token;
  }

  private _wsUrl(token: string): string {
    let base = this.opts.url.replace(/\/$/, "");
    if (base.startsWith("https://")) base = "wss://" + base.slice(8);
    else if (base.startsWith("http://")) base = "ws://" + base.slice(7);
    return `${base}/realtime?token=${encodeURIComponent(token)}`;
  }

  private _setState(s: ConnectionState): void {
    if (this._state === s) return;
    this._state = s;
    for (const h of this.stateHandlers) safe(h, s);
  }

  private async _open(): Promise<void> {
    this._setState(this.attempts === 0 ? "CONNECTING" : "RECONNECTING");
    let token: string;
    try {
      token = await this._resolveToken();
    } catch (e) {
      this._setState("FAILED");
      throw new BeacnError(`token acquisition failed: ${(e as Error).message}`, "token");
    }

    return new Promise<void>((resolve, reject) => {
      const ws = new this.WS(this._wsUrl(token));
      this.ws = ws;
      let welcomed = false;

      ws.onopen = () => {
        this.log.debug("beacn: socket open");
      };

      ws.onmessage = (ev: MessageEvent) => {
        let frame: Record<string, unknown>;
        try {
          frame = JSON.parse(typeof ev.data === "string" ? ev.data : String(ev.data));
        } catch {
          return;
        }
        const type = frame.type as string;

        if (type === "welcome") {
          welcomed = true;
          this.attempts = 0;
          this.connectionId = frame.connection_id as string;
          this._setState("CONNECTED");
          this._startHeartbeat((frame.heartbeat_ms as number) || 25000);
          void this._resubscribeAll();
          resolve();
          return;
        }
        if (type === "subscribed" || type === "unsubscribed") {
          this._settle(`${type === "subscribed" ? "sub" : "unsub"}:${frame.topic}`);
          return;
        }
        if (type === "replay_done") {
          this._settle(`replay:${frame.topic}`);
          return;
        }
        if (type === "pong") return;
        if (type === "error") {
          const err = new BeacnError((frame.message as string) || "error", (frame.code as string) || "error");
          if (frame.topic) {
            this._reject(`sub:${frame.topic}`, err);
            this._reject(`replay:${frame.topic}`, err);
          } else if (!welcomed) {
            reject(err);
          }
          this.log.warn("beacn: server error", err.code, err.message);
          return;
        }
        if (type === "event") {
          const event = frame as unknown as BeacnEvent;
          if (event.id) this.lastEventId.set(event.topic, event.id);
          this.channels.get(event.topic)?._dispatch(event);
          return;
        }
      };

      ws.onclose = () => {
        this._stopHeartbeat();
        for (const [, p] of this.pending) p.reject(new BeacnError("connection closed", "closed"));
        this.pending.clear();
        if (this.closedByUser) {
          this._setState("DISCONNECTED");
          return;
        }
        if (!welcomed) reject(new BeacnError("connection closed before welcome", "closed"));
        this._scheduleReconnect();
      };

      ws.onerror = () => {
        // `onclose` follows and drives reconnect; nothing to do here.
      };
    });
  }

  private _scheduleReconnect(): void {
    this.attempts += 1;
    if (this.attempts > this.opts.maxReconnectAttempts) {
      this._setState("FAILED");
      return;
    }
    this._setState("RECONNECTING");
    const cap = 15000;
    const raw = Math.min(cap, this.opts.reconnectBaseMs * 2 ** (this.attempts - 1));
    const delay = Math.random() * raw;
    this.log.debug(`beacn: reconnect #${this.attempts} in ${Math.round(delay)}ms`);
    setTimeout(() => {
      if (!this.closedByUser) void this._open().catch(() => this._scheduleReconnect());
    }, delay);
  }

  private async _resubscribeAll(): Promise<void> {
    for (const [topic, ch] of this.channels) {
      if (!ch.subscribed) continue;
      try {
        await this._subscribe(topic);
        const since = this.lastEventId.get(topic);
        if (since) await this._replay(topic, since);
      } catch (e) {
        this.log.warn("beacn: resubscribe failed", topic, (e as Error).message);
      }
    }
  }

  private _startHeartbeat(intervalMs: number): void {
    if (!this.opts.heartbeat) return;
    this._stopHeartbeat();
    this.heartbeatTimer = setInterval(() => {
      if (this.ws && this.ws.readyState === 1) this.ws.send(JSON.stringify({ type: "ping" }));
    }, Math.max(5000, intervalMs));
  }

  private _stopHeartbeat(): void {
    if (this.heartbeatTimer) clearInterval(this.heartbeatTimer);
    this.heartbeatTimer = undefined;
  }

  private _send(frame: Record<string, unknown>): void {
    if (!this.ws || this.ws.readyState !== 1) {
      throw new BeacnError("not connected", "not_connected");
    }
    this.ws.send(JSON.stringify(frame));
  }

  private _await(key: string, send: () => void): Promise<void> {
    return new Promise<void>((resolve, reject) => {
      this.pending.set(key, { resolve, reject });
      try {
        send();
      } catch (e) {
        this.pending.delete(key);
        reject(e as Error);
        return;
      }
      setTimeout(() => {
        if (this.pending.has(key)) {
          this.pending.delete(key);
          reject(new BeacnError(`timed out waiting for ${key}`, "timeout"));
        }
      }, 10000);
    });
  }

  private _settle(key: string): void {
    const p = this.pending.get(key);
    if (p) {
      this.pending.delete(key);
      p.resolve();
    }
  }

  private _reject(key: string, err: Error): void {
    const p = this.pending.get(key);
    if (p) {
      this.pending.delete(key);
      p.reject(err);
    }
  }

  /** @internal */
  async _subscribe(topic: string): Promise<void> {
    if (this._state !== "CONNECTED") await this.connect();
    await this._await(`sub:${topic}`, () =>
      this._send({ type: "subscribe", topic, ref: topic }),
    );
  }

  /** @internal */
  async _unsubscribe(topic: string): Promise<void> {
    await this._await(`unsub:${topic}`, () => this._send({ type: "unsubscribe", topic }));
  }

  /** @internal */
  async _replay(topic: string, since?: string): Promise<void> {
    await this._await(`replay:${topic}`, () =>
      this._send({ type: "replay", topic, since: since ?? null }),
    );
  }

  /** Acknowledge processing of an event id (server-side bookkeeping). */
  ack(eventId: string): void {
    this._send({ type: "ack", id: eventId });
  }
}

function safe<T>(fn: (arg: T) => void, arg: T): void {
  try {
    fn(arg);
  } catch (e) {
    // A handler that throws must not break delivery to the others.
    // eslint-disable-next-line no-console
    if (typeof console !== "undefined") console.error("beacn handler error", e);
  }
}
