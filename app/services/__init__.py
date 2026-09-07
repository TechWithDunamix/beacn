"""Application services — the layer between HTTP/CLI and the ORM.

Each module is a small, testable unit with an explicit interface:

* `ingest`   — validate → dedupe → persist → fan out
* `history`  — cursor-paginated reads of the event store
* `replay`   — bounded catch-up from the durable store, retention-aware
* `ratelimit`— per-key token bucket for publish traffic
* `stats`    — the numbers the dashboard reads
* `retention`— the prune job
* `audit`    — control-plane audit trail
"""
