# The `beacn` CLI

Built on `sillo.console`. Two kinds of command:

- **Local** (`serve`, `migrate`, `doctor`, `user *`, `work`) — open the
  database or the process directly. The `user *` commands reuse
  `sillo.users.commands` (the framework's account operations) and add BEACN's
  role assignment; the rest are process/schema operations.
- **API** (everything else) — go over HTTP through `/api/control` and `/api/v1`,
  authenticated with the token from `beacn login`, subject to the *same* RBAC
  the dashboard enforces. The CLI is not a way around authorization.

```
beacn login <email>              sign in, store a token (0600, ~/.config/beacn)
beacn whoami                      show the operator and permissions
beacn logout

beacn serve [--host --port --reload]
beacn migrate                     create tables, seed the RBAC catalogue
beacn doctor [--json]             check config, database, event bus
beacn work [--json]               run maintenance jobs once (retention, counters, reaping)

# operator accounts (built on sillo.users.commands)
beacn user create <email> [--role Admin|Operator|Developer|ReadOnly] [--admin]
beacn user list [--limit] [--json]
beacn user show <email> [--json]
beacn user password <email>
beacn user role <email> <role>            replace an operator's role
beacn user disable <email>  /  beacn user enable <email>
#   password: hidden prompt, or $BEACN_PASSWORD ($SILLO_PASSWORD also honoured)
#   when there is no terminal (CI). --admin marks a superuser and runs the
#   framework password policy; the ordinary path still requires >= 10 chars.

beacn producer create <name> [--environment --description]
beacn producer list [--environment] [--json]
beacn key create <producer_id> [--name --scopes --expires-in-days]   # secret shown once
beacn key list [--environment] [--json]
beacn key revoke <key_id> [--reason]
beacn topic list [--environment] [--json]

beacn events publish <event> [--topic --data '<json>' --idempotency-key]   # uses $BEACN_API_KEY
beacn events inspect <event_id>
beacn events replay <topic> [--since --limit]
beacn events tail <topic> [--json]     # live SSE stream
```

## Environment

| var | used by | meaning |
|---|---|---|
| `BEACN_URL` | all | base URL (default `http://localhost:8000`) |
| `BEACN_TOKEN` | API commands | overrides the stored login token |
| `BEACN_API_KEY` | `events *` | a `bk_…` key for publishing / inspecting / tailing |
| `BEACN_HOME` | credential store | overrides `~/.config/beacn` |
| `BEACN_PASSWORD` | `user create` / `user password` | password to use when there is no terminal |

## Examples

```bash
# first run: schema, the bootstrap operator, then the server
beacn migrate
beacn user create you@example.com --role Admin --admin      # prompts for a password
beacn serve

# add teammates (also available in the dashboard under Operators)
beacn user create sre@example.com --role Operator
beacn user role sre@example.com Developer
beacn user disable leaver@example.com

export BEACN_URL=https://beacn.internal
beacn login sre@corp.example
beacn producer create "Orders API" --environment production
# -> prd_01J...
beacn key create prd_01J... --name "orders prod" --scopes "events:publish events:read"
# -> secret: bk_...   (store it now)

export BEACN_API_KEY=bk_...
beacn events publish order.created --topic orders --data '{"order_id":"o_9"}'
beacn events tail orders
```
