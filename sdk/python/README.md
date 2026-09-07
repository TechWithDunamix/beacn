# beacn — Python SDK

One file (`beacn.py`). The sync client, the SSE consumer and event history use
**only the standard library**. Async and WebSocket are optional extras.

```bash
pip install beacn                 # no dependencies
pip install "beacn[async]"        # + httpx      -> AsyncBeacn
pip install "beacn[websocket]"    # + websockets -> AsyncBeacn.subscribe over WS
```

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
pip install -e ".[dev]"
pytest tests -o testpaths=tests        # starts a real BEACN server
```
