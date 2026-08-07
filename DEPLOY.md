# Deploying a public demo: Vercel + Cloud Run + Neon + Upstash

This replaces an earlier Railway-based plan. Railway's free trial is a
one-time credit, not a recurring free tier — once it's spent, the app stops
without a card on file. Every provider below instead has a **monthly free
quota that resets forever**, not a countdown, which is what "available
anytime, no subscription" actually requires.

This is a manual runbook, not a committed platform config file — deliberately.
This repo's own test suite (`shared/tests/test_no_hardcoded_models.py`) scans
every `.toml`/`.json`/`.yml`/`.yaml` file for hardcoded model identifiers
(C-2: the model name may only live inside `shared/llm/`). Sticking to a plain
Markdown runbook sidesteps that entirely.

You need accounts on four providers (Vercel, Google Cloud, Neon, Upstash) —
none of that is something an assistant can do on your behalf. Google Cloud
asks for a card on signup even though nothing here should be billed if you
stay inside the free quotas described below.

**Several details below are marked "unverified" — confirm them against each
provider's current dashboard/docs at setup time.** The one piece I could
verify locally (arq's `--burst` flag, load-bearing for the worker's design
below) I checked directly: `docker compose run --rm --no-deps worker arq
--help` confirms `--burst / --no-burst: Batch mode: exit once no jobs are
found in any queue.`

## Why this shape

The app is local-first by design: normally it talks to your own Ollama
instance, so there's no cost to meter and nothing to protect from abuse.
Hosting it publicly reintroduces both problems, resolved the same way the
app already decided to: **visitors bring their own LLM API key** (see
`shared/llm/gateway.py`'s `api_key_override` and `web/src/lib/llmKey.ts`).
None of that changes here — this document is only about *where the
containers run*, not how the LLM key flows.

## The one real architecture wrinkle: the worker

Every other piece of this app is naturally request-driven (an HTTP call in,
a response out), which is exactly what serverless platforms are built for.
The **worker is not** — `arq worker.main.WorkerSettings` is designed to sit
connected to Redis and pick up jobs the instant they're queued, forever.
Cloud Run's free tier has no way to keep a container alive for that
indefinitely; keeping one instance always warm (`min-instances=1`) is
billed continuously and would blow through the free monthly compute
allowance in days, not months.

The fix: run the worker as a **Cloud Run Job**, not a Cloud Run *service*,
triggered on a short interval (e.g. every minute) by **Cloud Scheduler**,
with its command overridden to add `--burst` — arq's built-in "drain
whatever's queued, then exit" mode (verified above). Each invocation spins
up, processes anything waiting, and exits — cumulative compute time for a
low-traffic demo stays a tiny fraction of the free quota. The real cost of
this design: a submitted extraction or chat edit can wait up to the
scheduler's interval (a minute, if set that way) before it even starts,
on top of however long the model call itself takes. That's a fine trade for
a portfolio demo; it would not be for anything latency-sensitive.

This doesn't touch the code at all — the same `worker/Dockerfile.prod`
image runs both ways, `--burst` is a command-line flag, and the read-once
Redis handoff for a visitor's API key (600s TTL, see `shared/llm/gateway.py`)
already tolerates the job not being picked up instantly.

## Services

| Service | Provider | Source |
|---|---|---|
| `web` | Vercel | this repo, Root Directory `web/` — no Dockerfile, Vercel builds Next.js natively |
| `api` | Google Cloud Run (service) | `api/Dockerfile.prod`, repo root build context |
| `worker` | Google Cloud Run (**Job**, not service) | `worker/Dockerfile.prod`, same image, command overridden with `--burst` |
| `plantuml` | Google Cloud Run (service) | public image `plantuml/plantuml-server:jetty` |
| `kroki` | Google Cloud Run (service) | public image `yuzutech/kroki:latest` |
| `kroki-mermaid` | Google Cloud Run (service) | public image `yuzutech/kroki-mermaid:latest` — bundles headless Chromium, ~1GB; slower cold start after scale-to-zero, otherwise fine |
| Postgres | Neon | managed, free tier |
| Redis | Upstash | managed, free tier — see the REST-vs-TCP note below |

`plantuml`/`kroki`/`kroki-mermaid` are genuinely request-driven HTTP
services (render a diagram, return it) — completely ordinary Cloud Run
scale-to-zero services, no worker-style rework needed. `kroki`/`kroki-mermaid`
are included by default so the ER diagram works (PlantUML alone covers the
other 7 diagram types, not this one).

## Order of operations

1. **Neon**: create a project, get the connection string. Note the fix
   below before using it as `DATABASE_URL`.
2. **Upstash**: create a Redis database. Use its **TCP/RESP endpoint**
   (`rediss://...upstash.io:...`), not its REST API URL — arq and this
   app's redis client both speak the raw Redis protocol, not Upstash's
   HTTP REST interface. The database's "Connect" tab should show both;
   pick the one labelled for redis-cli / ioredis / standard clients.
3. **Deploy `plantuml`, `kroki`, `kroki-mermaid`** to Cloud Run straight
   from their public images (`gcloud run deploy plantuml
   --image=docker.io/plantuml/plantuml-server:jetty ...` — *unverified*:
   confirm `gcloud run deploy --image` can pull directly from Docker Hub
   without first mirroring into Artifact Registry; if not, mirror once).
4. **Deploy `api`** to Cloud Run from `api/Dockerfile.prod` (repo root
   build context — `gcloud run deploy api --source=. ` with the Dockerfile
   path, or build+push then `--image`). Set its env vars (below). Note its
   public URL.
5. **Create the `worker` Cloud Run Job** from the same repo/Dockerfile
   (`worker/Dockerfile.prod`), but as a Job resource, not a service —
   *unverified exact gcloud command*, expect something like `gcloud run
   jobs create worker --source=. --command=arq
   --args=worker.main.WorkerSettings,--burst`. Set the same env vars as
   `api` (below). Attach a **Cloud Scheduler** trigger on a short interval
   (e.g. every 1 minute) that invokes the job.
6. **Deploy `web` to Vercel**: import this repo, set Root Directory to
   `web/`. Unlike a Docker build, Vercel clones the whole repository, so
   the `prebuild` script's `../schemas/cpm.schema.json` reference resolves
   correctly — `npm run build` runs as-is, no need to bypass it the way
   `web/Dockerfile.railway` (the now-removed Railway variant) had to. Set
   its env vars (below), using `api`'s Cloud Run URL from step 4.
7. **Update `api`'s `CORS_ALLOWED_ORIGINS`** to Vercel's assigned domain
   and redeploy `api`.

## Environment variables

### `api` (Cloud Run service) and the `worker` Cloud Run Job — same values

```
DATABASE_URL=postgresql+asyncpg://<user>:<password>@<neon-host>/<database>?ssl=require
REDIS_URL=<Upstash's rediss:// TCP connection string>
PLANTUML_SERVER_URL=<plantuml Cloud Run service's URL>
MERMAID_RENDERER_URL=<kroki Cloud Run service's URL>
LLM_PROVIDER=openai_compatible
LLM_OPENAI_BASE_URL=https://api.groq.com/openai/v1
LLM_MODEL=<a Groq-hosted model you choose>
# LLM_API_KEY intentionally left UNSET — strict bring-your-own-key.
ASA_SIGNING_SECRET=<generate with: python -c "import secrets; print(secrets.token_urlsafe(32))">
CORS_ALLOWED_ORIGINS=<Vercel's domain, set after step 7 above>
```

- **Neon's `DATABASE_URL` needs a scheme AND a param fix, not just a copy-paste.**
  Neon gives you a `postgresql://...?sslmode=require` string (the libpq/psycopg
  convention). Two changes: swap the scheme to `postgresql+asyncpg://` (this
  app uses the asyncpg driver), and swap `sslmode=require` for `ssl=require`
  — asyncpg's SQLAlchemy dialect uses a different query parameter name than
  libpq does, and `sslmode` is silently ignored by asyncpg rather than
  erroring, so a copy-pasted Neon string can *look* fine and fail at
  connection time. If `?ssl=require` doesn't work as a URL query param
  against your installed SQLAlchemy/asyncpg versions, the fallback is
  passing `connect_args={"ssl": "require"}` to `create_async_engine` in
  `shared/store/session.py` instead — *unverified which of the two your
  exact dependency versions need*, try the URL param first.
- `PLANTUML_SERVER_URL` / `MERMAID_RENDERER_URL`: each Cloud Run service's
  own HTTPS URL (Cloud Run services get a public URL by default, unlike
  Railway's private internal networking — *unverified*: check whether you
  want these three internal-only via Cloud Run's VPC/ingress settings
  rather than public, since they don't need to be reachable from outside
  the project).
- `LLM_OPENAI_BASE_URL`/`LLM_MODEL`: Groq is the suggested default — free
  tier, OpenAI-compatible, fast. One env var away from any other
  OpenAI-Chat-Completions-compatible provider.

### `web` (Vercel)

```
NEXT_PUBLIC_API_BASE_URL=<api's Cloud Run URL>
NEXT_PUBLIC_LLM_KEY_REQUIRED=true
NEXT_PUBLIC_LLM_PROVIDER_LABEL=Groq
NEXT_PUBLIC_LLM_PROVIDER_SIGNUP_URL=https://console.groq.com/keys
```

Set these as Vercel project environment variables (Production scope) before
the first deploy — Next.js inlines `NEXT_PUBLIC_*` at build time, so a value
added after a build won't appear until the next one.

## Health / readiness

- `api`: Cloud Run's own health checking is based on whether the container
  responds on `$PORT` at all; there's no separate health-check URL field
  the way Railway has, so nothing extra to configure. `/health/live`
  (`api/app/routers/health.py`) remains available if you want to point an
  external uptime monitor at something dependency-free.
- `worker`: a Cloud Run Job has no health check concept — Cloud Scheduler's
  own execution-history log is how you'd notice it stopped running.
- `plantuml`/`kroki`/`kroki-mermaid`: ordinary Cloud Run services, same as
  `api` — no separate check needed.

## Known limitations (accepted, not fixed here)

- **Job pickup latency.** As covered above, a submitted extraction/chat
  edit waits for the next Cloud Scheduler tick before the worker even
  starts on it. Set the schedule as tight as the free tier comfortably
  allows if this bothers you.
- **No rate limiting anywhere in the stack.** Bring-your-own-key removes
  the LLM cost/abuse risk specifically, but a request flood still costs
  Cloud Run invocations and Neon/Upstash usage regardless of whether any
  LLM call ever succeeds.
- **No length cap on pasted text**, same as before — only PDF uploads get
  one, via `probe_pdf`.

## Verifying the deployment

Open Vercel's URL in a fresh browser (no key stored). Confirm the key
control shows the required/prominent styling. Submit a description with no
key entered — it should fail with a clear provider-auth error, not hang
silently (allow for the scheduler's pickup delay before deciding it's
actually stuck). Paste a real Groq key, submit again, confirm a CPM draft
comes back and all 8 diagram types render — specifically the ER diagram,
since that's the one depending on `kroki`/`kroki-mermaid`.
