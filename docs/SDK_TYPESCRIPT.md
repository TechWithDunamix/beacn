# BEACN TypeScript / JavaScript SDK

Browser-first. Uses the global `WebSocket`; inject one for Node or tests.
`sdk/typescript/`, published as `@beacn/client`.

```bash
npm install @beacn/client
```

```typescript
import { Beacn } from "@beacn/client";

const beacn = new Beacn({
  url: "wss://beacn.example.com",   // https:// is also accepted
  token,                            // realtime JWT, or a bk_ API key
});

const channel = beacn.channel("tasks");

channel.on("task.completed", (event) => {
  console.log(event.id, event.data);
});
channel.onAny((event) => metrics.count(event.event));

await channel.subscribe();          // connects if needed, resolves on `subscribed`
```

## Connection state

```typescript
beacn.onStateChange((state) => {
  // CONNECTING | CONNECTED | RECONNECTING | DISCONNECTED | FAILED
});
beacn.state;           // current
beacn.connectionId;    // server-assigned con_… after `welcome`
```

`connect()` resolves on `welcome`. On an unexpected close the client
**reconnects** with full-jitter backoff (base `reconnectBaseMs`, capped 15s),
re-subscribes every channel, and **replays** each from the last event id it
delivered. After `maxReconnectAttempts` the state becomes `FAILED`.
`disconnect()` closes and does not reconnect.

## Options

| option | default | meaning |
|---|---|---|
| `url` | — | `wss://host` or `https://host` |
| `token` | — | realtime JWT or `bk_` API key |
| `getToken` | — | `() => string \| Promise<string>` called before every (re)connect; overrides `token` so an expiring JWT is refreshed |
| `maxReconnectAttempts` | `Infinity` | then `FAILED` |
| `reconnectBaseMs` | `500` | full-jitter, capped at 15000 |
| `heartbeat` | `true` | answer idle periods with `ping` |
| `WebSocketImpl` | `globalThis.WebSocket` | inject for Node (`ws`) |
| `logger` | no-op | `{ debug, warn }` |

## Channel

```typescript
const ch = beacn.channel("user:42");
ch.on("notification.created", handler);   // by event name
ch.onAny(handler);                        // every event on the topic
ch.off("notification.created", handler);
await ch.subscribe();
await ch.replay("evt_01J...");            // catch up from a known cursor
await ch.unsubscribe();
```

## Errors

`BeacnError` with a `code` (`unauthenticated`, `forbidden`, `timeout`,
`not_connected`, `closed`, …). A forbidden topic rejects that channel's
`subscribe()` without tearing down the connection. Handler exceptions are caught
so one bad handler never blocks delivery to the others.

## Typed events

```typescript
import type { BeacnEvent } from "@beacn/client";

interface PaymentCompleted extends BeacnEvent {
  event: "payment.completed";
  data: { payment_id: string; amount: number };
}
channel.on("payment.completed", (e) => {
  const p = e as PaymentCompleted;
  charge(p.data.payment_id);
});
```
