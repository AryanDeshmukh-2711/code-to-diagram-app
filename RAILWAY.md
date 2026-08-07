# Deploying a public demo on Railway

This is a manual runbook, not a committed Railway config file — deliberately.
This repo's own test suite (`shared/tests/test_no_hardcoded_models.py`)
scans every `.toml`/`.json`/`.yml`/`.yaml` file for hardcoded model
identifiers (C-2: the model name may only live inside `shared/llm/`), and a
committed `railway.toml`/`railway.json` with a real model default risks
tripping it. A plain Markdown runbook sidesteps that entirely — you click
through Railway's dashboard (or its CLI) yourself, following the steps below.

You need a Railway account and a payment method on file (Railway's free
trial credit runs out; the resource footprint here — 8 services, one with a
~1GB image — will exceed it for anything but a short-lived demo). Neither of
those is something an assistant can do on your behalf.

**Several details below are marked "unverified" — confirm them against
Railway's current dashboard/docs at setup time rather than trusting this
document blindly.** Railway's product surface changes; this was written
against the app's architecture, not a live Railway session.

## Why this shape

The app is local-first by design: normally it talks to your own Ollama
instance, so there's no cost to meter and nothing to protect from abuse.
Hosting it publicly reintroduces both problems. This deployment resolves
them the same way the app already decided to: **visitors bring their own
LLM API key** (see `shared/llm/gateway.py`'s `api_key_override` and
`web/src/lib/llmKey.ts`) — you configure *which* provider the demo uses,
visitors each supply their *own* key for it, so there's no shared bill and
no accounts system to build.

## Services (8)

| Service | Source | Notes |
|---|---|---|
| `postgres` | Railway managed Postgres plugin | |
| `redis` | Railway managed Redis plugin | |
| `plantuml` | public image `plantuml/plantuml-server:jetty` | no Dockerfile — same image `docker-compose.yml` uses |
| `kroki` | public image `yuzutech/kroki:latest` | renders the ER diagram (Mermaid engine) |
| `kroki-mermaid` | public image `yuzutech/kroki-mermaid:latest` | bundles headless Chromium, ~1GB — see cost note below |
| `api` | `api/Dockerfile.railway`, repo root context | FastAPI |
| `worker` | `worker/Dockerfile.railway`, repo root context | arq job worker, no public port |
| `web` | `web/Dockerfile.railway`, repo root context | Next.js, production build |

**Cost/tier decision, before you start**: `kroki`/`kroki-mermaid` exist so
the ER diagram works (PlantUML alone covers the other 7 diagram types, not
this one). They're the heaviest two services here by a wide margin. If 8
always-on services don't fit whatever Railway plan you're on, the fallback
is to drop `kroki`/`kroki-mermaid` and accept a degraded ER diagram — check
Railway's current plan limits before committing to either path.

## Order of operations

Railway services reference each other's variables, so build them in this
order:

1. **Add the Postgres and Redis plugins** to a new Railway project.
2. **Deploy `plantuml`, `kroki`, `kroki-mermaid`** from their public images
   (no repo connection needed for these three — Railway supports deploying
   a service straight from a Docker image).
3. **Deploy `api` and `worker`** from this repo: for each, set the
   Dockerfile path (`api/Dockerfile.railway` / `worker/Dockerfile.railway`)
   and leave the build context at the repo root (*unverified*: confirm
   Railway's current UI wording for this — it may be called "Root
   Directory" plus a separate "Dockerfile Path" field). Set the env vars
   below on both before first deploy.
4. **Note `api`'s public domain** once it deploys (Railway assigns one
   automatically, or you set a custom one).
5. **Deploy `web`**, Dockerfile path `web/Dockerfile.railway`, same repo
   root context. Set its build args (below) — `api`'s domain from step 4 is
   one of them, so `web` must come after `api`.
6. **Set `api`'s `CORS_ALLOWED_ORIGINS`** to `web`'s now-known public
   domain and redeploy `api`. *Before doing this manually*: check whether
   Railway lets you reference `web`'s domain as a variable (something like
   `${{web.RAILWAY_PUBLIC_DOMAIN}}`) so this resolves automatically instead
   — *unverified*, try it first, fall back to the manual redeploy if it
   doesn't work as expected.

## Environment variables

### `api` and `worker` (same values on both)

```
DATABASE_URL=postgresql+asyncpg://<user>:<password>@<host>:<port>/<database>
REDIS_URL=<Railway Redis plugin's connection string>
PLANTUML_SERVER_URL=http://plantuml.railway.internal:8080
MERMAID_RENDERER_URL=http://kroki.railway.internal:8000
LLM_PROVIDER=openai_compatible
LLM_OPENAI_BASE_URL=https://api.groq.com/openai/v1
LLM_MODEL=<a Groq-hosted model you choose>
# LLM_API_KEY intentionally left UNSET — strict bring-your-own-key, no
# shared fallback. Every visitor supplies their own via the app's UI.
ASA_SIGNING_SECRET=<generate with: python -c "import secrets; print(secrets.token_urlsafe(32))">
CORS_ALLOWED_ORIGINS=<web's public domain, set after step 4/6 above>
```

- `DATABASE_URL`: Railway's Postgres plugin exposes a standard
  `postgresql://` connection string via its own reference variables
  (typically individual fields plus a combined URL — *unverified exact
  field names*, check the plugin's "Connect" tab). This app needs the
  asyncpg driver scheme, so compose it as `postgresql+asyncpg://…` using
  Railway's variable-reference syntax against the Postgres service's
  individual host/port/user/password/database fields, rather than reusing
  its ready-made `DATABASE_URL` directly (that one will have the plain
  `postgresql://` scheme).
- `REDIS_URL`: same idea — reference the Redis plugin's connection string
  directly; no scheme translation needed here.
- `PLANTUML_SERVER_URL` / `MERMAID_RENDERER_URL`: Railway private
  networking gives each service a `<service-name>.railway.internal`
  hostname reachable from other services in the same project
  (*unverified*: confirm this is still the exact convention, and whether
  private networking needs enabling per-service). `kroki`'s own
  `KROKI_MERMAID_HOST` env var should point at `kroki-mermaid`'s equivalent
  internal hostname.
- `LLM_OPENAI_BASE_URL`/`LLM_MODEL`: Groq is the suggested default —
  generous free tier, OpenAI-compatible, fast. This is a one-line env var
  change if you'd rather use OpenRouter, Together, or anything else
  OpenAI-Chat-Completions-compatible; nothing in the code names a provider.
- `ASA_SIGNING_SECRET`: same secret this app already requires for local
  dev (`.env.example`), no default on purpose — signs artefact/export
  download links.

### `web`

Build args (baked into the JS bundle at `docker build` time — set these as
the service's **build-time** variables, not just runtime ones; confirm
Railway surfaces a distinct "available at build" toggle per variable,
*unverified*):

```
NEXT_PUBLIC_API_BASE_URL=<api's public domain>
NEXT_PUBLIC_LLM_KEY_REQUIRED=true
NEXT_PUBLIC_LLM_PROVIDER_LABEL=Groq
NEXT_PUBLIC_LLM_PROVIDER_SIGNUP_URL=https://console.groq.com/keys
```

`NEXT_PUBLIC_LLM_KEY_REQUIRED=true` is what makes the frontend's key control
(`web/src/components/LlmKeyControl.tsx`) present the field as required
rather than the optional/de-emphasized local-dev styling.

## Health checks

- `api`: point Railway's HTTP health check at `/health/live`
  (`api/app/routers/health.py`), not `/health` — `/health/live` is
  deliberately dependency-free, so a transient PlantUML/Kroki blip doesn't
  cause Railway to needlessly cycle an otherwise-healthy API container.
- `worker`: no HTTP surface to check. Rely on Railway's restart-on-exit
  policy instead of a health check.
- `plantuml` / `kroki` / `kroki-mermaid`: skip health checks unless you've
  confirmed a stable 200 endpoint on the specific image versions you're
  running.

## Known limitations of this setup (accepted, not fixed here)

- **No rate limiting anywhere in the stack.** Bring-your-own-key removes
  the LLM cost/abuse risk specifically, but a request flood still costs you
  Postgres and compute time regardless of whether any LLM call ever
  succeeds. Consider Railway's usage alerts, or a minimal reverse-proxy
  rate limit, if this becomes a real problem.
- **No length cap on pasted text.** `POST .../extract`'s `text` field has
  no size limit (only PDF uploads get one, via `probe_pdf`). Not exploited
  by anything in this app today, but worth knowing before linking this
  publicly.

## Verifying the deployment

Once everything above is live: open `web`'s public URL in a fresh browser
(no key stored). Confirm the key control shows the required/prominent
styling. Submit a description with no key entered — it should fail with a
clear provider-auth error, not hang silently. Paste a real Groq key, submit
again, confirm a CPM draft comes back and all 8 diagram types render —
specifically the ER diagram, since that's the one that depends on
`kroki`/`kroki-mermaid` actually being wired up correctly.
