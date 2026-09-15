# Debug FastAPI with TraceLoom

TraceLoom's FastAPI middleware captures incoming HTTP requests to your FastAPI application: the request path, headers, body, response, and timing. Combined with the automatic outgoing HTTP capture, you get a complete view of what your API endpoint received and what external calls it made to handle it.

## Setup

```bash
uv sync --frozen
traceloom-server  # start the dashboard
```

Add the TraceLoom middleware to your FastAPI app:

```python
from fastapi import FastAPI
from traceloom.integrations.fastapi import TraceLoomMiddleware

app = FastAPI()
app.add_middleware(TraceLoomMiddleware)
```

Then run your server with `traceloom run`:

```bash
traceloom run uvicorn app:app
```

Incoming request capture is the one integration that requires a code change: adding the middleware line. Outgoing HTTP, exceptions, and logs are all captured automatically by `traceloom run`.

> **Example scripts**: [`fastapi_server.py`](../../examples/python/fastapi_server.py), [`hierarchy_demo.py`](../../examples/python/hierarchy_demo.py)

The hierarchy demo uses only local endpoints. Run it with:

```bash
traceloom run --capture-logs --log-level INFO -- \
  uvicorn examples.python.hierarchy_demo:app --port 8001
```

Call `POST /checkout` for a successful outgoing child operation, then call
`POST /checkout/provider-down` for a failed child followed by an incoming-request
exception. Choose **Remote host** in TraceLoom to group each outgoing child by destination.

## Scenario: debugging a 500 error on a checkout endpoint

Your `/api/checkout` endpoint returns 500 intermittently. The logs say "internal server error" but don't show what went wrong. What did the client send? What external calls did your handler make?

```python
@app.post("/api/checkout")
async def checkout(order: OrderRequest):
    customer = await stripe_client.get_customer(order.customer_id)
    charge = await stripe_client.create_charge(customer, order.amount)
    await send_confirmation_email(customer.email, charge.id)
    return {"charge_id": charge.id}
```

### Debug in the dashboard

Open the TraceLoom dashboard. You'll see the incoming request and all the outgoing calls it triggered:

![TraceLoom dashboard showing captured FastAPI requests](assets/debug-fastapi-dashboard.png)

- **Incoming request**: the full `POST /api/checkout` with the request body, headers, and the 500 response. Check the request body to see if the client sent valid data.
- **Outgoing calls**: the Stripe API call and the email service call appear in the timeline right after the incoming request. Did the Stripe call succeed but the email call fail?
- **Exception capture**: if the 500 was caused by an unhandled exception, TraceLoom captures the full traceback. You'll see the exception type, message, and stack frames in the dashboard.
- **Duration**: the incoming request shows total duration. Compare it with the outgoing call durations to understand where time was spent.

The incoming request is always the parent operation. Outgoing calls appear as children,
while logs and exceptions annotate the operation that emitted them. **Remote host** adds
a navigation group around each adjacent run of outgoing children without changing those
runtime relationships.

### Debug with an AI agent

If you use [Claude Code](https://claude.ai/code) or another AI coding tool, the `/traceloom` skill can query captured events and cross-reference them with your source code. Install it once:

```bash
Copy `skills/traceloom/SKILL.md` into your agent's skills directory.
```

Then ask your agent:

```
/traceloom
Why is /api/checkout returning 500?
```

![Claude Code session using traceloom to diagnose a FastAPI 500 error](assets/debug-fastapi-claude.png)

The skill is also invoked automatically when your agent recognizes a debugging question, but calling `/traceloom` explicitly gives the best results. See [AI Agent Skills](../ai-skills.md) for compatible tools.

## Tips

- **Exception visibility**: The FastAPI middleware captures exceptions that propagate through your handlers. These appear as exception events in the dashboard with full tracebacks, linked to the incoming request that triggered them.
- **Route matching**: The captured incoming request shows the matched route pattern (e.g., `/api/users/{user_id}`) alongside the actual URL. This helps when debugging path parameter issues.
- **Middleware order**: Add `TraceLoomMiddleware` before other middleware that might modify the request or response. TraceLoom captures what it sees, so putting it first gives you the raw client request.
- **Filtering**: Use the event type filter in the dashboard to focus on incoming requests only, or use the timeline view to see incoming and outgoing requests interleaved.
- **Hierarchy views**: Runtime parenthood is always visible. Remote host inserts destination groups around outgoing children, and group counts cover the records currently loaded in the browser.
- **Health checks**: If your app has health check endpoints that generate noise, use `ignore_paths` in the middleware configuration to exclude them.

--8<-- "includes/guide-next-steps.md"
