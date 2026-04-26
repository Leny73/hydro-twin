# 🌐 Vercel Deployment — Frontend

> Covers **LD-4** (frontend on Vercel).
> Status: ✅ Live at https://hydrotwin.vercel.app

---

## 🆔 Project inventory

| Resource | Value |
|---|---|
| **Public URL** | https://hydrotwin.vercel.app |
| **Direct deploy URL** | https://hydrotwin-f8a9or5ec-demetrios-projects-24fffdd4.vercel.app |
| **Vercel project slug** | `demetrios-projects-24fffdd4/hydrotwin` |
| **Vercel scope (account)** | `dimitriosv2002-9727` |
| **Latest deployment ID** | `dpl_F3N7b8QaXPszJe7REJgrL3Shx2Bh` |
| **Inspector URL** | https://vercel.com/demetrios-projects-24fffdd4/hydrotwin |
| **Local link file** | `frontend/.vercel/project.json` (gitignored by Vercel CLI) |

---

## 🛠️ Build configuration

Auto-detected by Vercel — no `vercel.json` needed.

| Setting | Value |
|---|---|
| Framework preset | Vite |
| Root directory | `frontend/` (set during `vercel link`) |
| Build command | `npm run build` (default) |
| Output directory | `dist/` (Vite default) |
| Install command | `npm install` (default) |
| Node version | Vercel default (currently Node 22) |
| Build duration | `~28 s` |

---

## 🔑 Environment variables

Set per-environment. **All values encrypted in Vercel** — `vercel env ls` shows `Encrypted` placeholder.

| Variable | Production | Preview | Development | Notes |
|---|:-:|:-:|:-:|---|
| `VITE_API_ENDPOINT` | ✅ | ❌ | ✅ | Lambda URL — see `01-aws-deployment.md` |
| `VITE_MAPBOX_TOKEN` | ✅ | ❌ | ✅ | Mapbox public `pk.` token, scoped `styles:read,tiles:read` |

> ⚠️ Preview env vars not set — branch deploys won't render the map. Run `vercel env add VITE_MAPBOX_TOKEN preview` + same for `VITE_API_ENDPOINT` if branch previews are needed.

> 🔒 Vite inlines `VITE_*` env vars at **build time** — they end up in the public JS bundle. Mapbox token is by-design public; rotate it in Mapbox dashboard if compromised.

---

## ✅ Build verification (post-deploy smoke)

| Check | Result |
|---|---|
| `GET https://hydrotwin.vercel.app/` | HTTP 200 in 0.56s, 1394 bytes |
| Main JS chunk reachable | `/assets/index-BWW3v9Oa.js` (172 KB) |
| `VITE_API_ENDPOINT` baked into bundle | ✅ (`sdnatb43dl.execute-api` substring found) |
| `VITE_MAPBOX_TOKEN` baked into bundle | ✅ (`pk.eyJ` substring found) |
| Mapbox-gl chunk | Separate `mapbox-gl-*.js` chunk (~1.7 MB, ~488 KB gzipped) |
| Cross-origin fetch from Vercel → Lambda | ✅ (CORS allows `*`) |

### Manual checks (browser-only)

⚠️ The following require real browser testing — couldn't be automated:

- [ ] Mapbox tiles render (need real Mapbox network call from browser)
- [ ] All 5 region markers visible
- [ ] Click region → AlertPanel opens with status badge + reasoning
- [ ] Mobile view (< 640 px): panel as bottom sheet
- [ ] Desktop view (≥ 640 px): panel as right sidebar
- [ ] Touch targets ≥ 44×44 px on phone
- [ ] LAN URL works on phone via Vite dev (separate from Vercel)

---

## 🔁 Redeploy quick-ref

```bash
# From repo root, with VERCEL_TOKEN exported
cd frontend
npx vercel deploy --prod --yes --token "$VERCEL_TOKEN"
# → outputs new deploy URL, automatically aliased to hydrotwin.vercel.app
```

### To update env vars

```bash
# Add or update an env var (stdin avoids echoing the value)
printf '%s' "$NEW_VALUE" | npx vercel env add VITE_API_ENDPOINT production --token "$VERCEL_TOKEN"
# Then redeploy to bake new value into bundle
npx vercel deploy --prod --yes --token "$VERCEL_TOKEN"
```

### To revoke the deploy token

If the `vcp_*` deploy token was exposed:

1. Open https://vercel.com/account/tokens
2. Find `hydrotwin-deploy` → click trash icon → confirm
3. Create a new token, store securely

---

## 🧱 Repo state effects of deploying

The `vercel link` command auto-modified:

- ✅ Created `frontend/.vercel/project.json` (project ID + org ID — safe to commit but auto-gitignored by Vercel CLI)
- ✅ Created `frontend/.vercel/README.txt` (boilerplate)
- ✅ Added `.vercel` to `frontend/.gitignore` (Vercel CLI did this)

`frontend/.env.local` (Mapbox + API URL for local dev) is gitignored via root `.gitignore` `**/.env.local`.

---

## 📊 Bundle size (post-build, gzipped)

| File | Size | Gzipped |
|---|---:|---:|
| `dist/index.html` | 1.4 KB | 0.74 KB |
| `dist/assets/index-*.css` | 57.6 KB | 9.2 KB |
| `dist/assets/index-*.js` | 171.9 KB | 56.0 KB |
| `dist/assets/mapbox-gl-*.js` | 1,774.1 KB | 488.5 KB |

Mapbox-gl is the bulk — unavoidable for a satellite map view. No code-splitting wins worth chasing for a hackathon demo.
