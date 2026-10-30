# beacn — Python SDK

One file (`beacn.py`). The sync client, the SSE consumer and event history use
**only the standard library**. Async and WebSocket are optional extras.

From the repository root, run a consumer with the module on the import path:

```sh
PYTHONPATH=sdk/python python your_consumer.py
```

For a separate consumer virtual environment, install the SDK from this checkout
with `pip install ./sdk/python` (run from the repository root), or use
`pip install './sdk/python[all]'` for optional transports. The server and SDK
currently share the distribution name `beacn`; keep them in separate virtual
environments to avoid replacing one with the other.

The server distribution in the root `pyproject.toml` does not package this SDK
module. Async REST additionally needs `httpx`; WebSocket subscription needs
`websockets` in your consumer environment.

```python
from beacn import Beacn

beacn = Beacn(url="https://beacn.internal", api_key="bk_...")
beacn.publish("payment.completed", topic="payments", data={"payment_id": "pay_1"})

for event in beacn.subscribe("payments"):
    print(event.event, event.data)
```

Full documentation: [`docs/SDK_PYTHON.md`](../../docs/SDK_PYTHON.md).
Compatibility: Python 3.8+.

## Develop

```bash
# Run from the repository root with its development dependencies installed.
pytest sdk/python/tests -o testpaths=sdk/python/tests        # starts a real BEACN server
```
