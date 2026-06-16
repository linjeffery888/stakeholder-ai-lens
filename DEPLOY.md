# Deploying the Lens dashboard (shareable URL, live extraction)

This hosts the dashboard at a public URL so someone else can open it, upload
their own interview files, and get real Claude extraction. Your API key lives in
the host's environment settings, never in the code or in git.

The app is a stdlib Python server, so any Python host works. Steps below use
**Render** (free tier, simplest). A **Railway** note follows.

---

## What is already wired for hosting

- `python app.py --host 0.0.0.0` binds for a host; `PORT` is read from the env.
- `ANTHROPIC_API_KEY` from the env turns on live mode automatically.
- Optional HTTP Basic Auth: set `LENS_BASIC_USER` and `LENS_BASIC_PASS` and the
  whole site requires that login. **Use this.** A public live URL with no auth
  lets anyone who finds it spend your API budget.
- Deploy configs in the repo: `render.yaml`, `Procfile`, `runtime.txt`,
  `requirements.txt`.

---

## Render (recommended)

1. **Push this repo to GitHub** (a private repo is fine). The `.env` file is
   git-ignored, so your key is not in what you push. Confirm with
   `git status` that `.env` is not listed.

2. Go to https://render.com -> **New + -> Blueprint** -> connect the repo.
   Render reads `render.yaml` and creates a web service.

3. Open the service -> **Environment** tab -> add:
   - `ANTHROPIC_API_KEY` = your key
   - `LENS_BASIC_USER` = a username you pick (e.g. `iovance`)
   - `LENS_BASIC_PASS` = a password you pick
   Save. Render redeploys.

4. When it goes live you get a URL like `https://lens-dashboard.onrender.com`.
   Share that URL plus the username/password with your interviewer.

That is it. They open the URL, log in, and use the **Upload transcripts** card
to add their own `.txt` / `.docx` / `.csv` files. Extraction runs live.

### Rotate when done
If you ever pasted the key anywhere public, rotate it at
https://console.anthropic.com . Changing the key only means updating the
`ANTHROPIC_API_KEY` env var in Render.

---

## Railway (alternative)

1. Push to GitHub. At https://railway.app -> **New Project -> Deploy from repo**.
2. Railway uses the `Procfile` automatically.
3. In the service **Variables**, add `ANTHROPIC_API_KEY`, `LENS_BASIC_USER`,
   `LENS_BASIC_PASS`.
4. Under **Settings -> Networking**, click **Generate Domain** for a public URL.

---

## Things to know

- **Cold start (free tier):** free instances sleep after ~15 min idle and take
  30-60s to wake on the next visit. Fine for a scheduled demo; pay for an
  always-on instance if you want instant loads.
- **Start the host LIGHT.** The deploy command does not preload the 100-file
  corpus on purpose. The hosted instance comes up with a few base interviews;
  your interviewer uploads their own files. Do NOT add `--transcripts
  transcripts/` to the host start command.
- **Upload size / time.** A portfolio recompute runs one Claude call per
  interview (extraction) PLUS one call per extracted pain point (dedup
  adjudication). A handful of interviews is a few minutes; it then caches and
  serves instantly until the next change. Large batches are slow: the full
  100-file corpus took ~45 min / ~550 calls. So keep live uploads modest (a few
  at a time) and do any bulk 100-file run locally.
- **Caching.** After each recompute the result is cached and written to
  `out/last_portfolio.json`; page loads serve the cache and only recompute when
  interviews or org settings change. Locally you can show the full pre-computed
  100-interview portfolio instantly with:
  `python app.py --transcripts transcripts/ --load-cache`
- **Shared session:** the demo keeps one in-memory session, so everyone hitting
  the URL sees the same uploaded set. Good for a 1:1 demo; not multi-tenant.
- **Cost:** every live upload spends API budget (Haiku, cheap). Basic Auth keeps
  it to people you invite. Consider a spend limit in the Anthropic console.

## Run it locally the same way

```bash
# live (reads .env or an exported key)
python app.py

# protect a local instance too, if you tunnel it
LENS_BASIC_USER=me LENS_BASIC_PASS=secret python app.py --host 0.0.0.0
```
