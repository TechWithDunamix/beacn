# @beacn/client

Official BEACN browser/client SDK — realtime events over WebSocket.

```bash
npm install @beacn/client
```

```typescript
import { Beacn } from "@beacn/client";

const beacn = new Beacn({ url: "wss://beacn.example.com", token });
const channel = beacn.channel("tasks");
channel.on("task.completed", (event) => console.log(event));
await channel.subscribe();
```

Full documentation: [`docs/SDK_TYPESCRIPT.md`](../../docs/SDK_TYPESCRIPT.md).

## Develop

```bash
npm install
npm run build      # -> dist/  (ESM + .d.ts)
npm test           # node --test against a fake realtime server
npm run typecheck
```
