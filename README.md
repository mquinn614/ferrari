# The Long Wait — a Scuderia Ferrari data story

A single-page scrollytelling site about Ferrari's Formula 1 record and its
championship drought since 2007/2008. Live at GitHub Pages (from `main`) and
mirrored at `mqsandbox.com/ferrari` on Bluehost.

The page is fully static, but **self-updating**: championship facts, the wins
chart, and the headline totals are regenerated from the
[Jolpica-F1](https://api.jolpi.ca) (Ergast-compatible) API on a schedule and
committed back to this repo as `data/ferrari-titles.json`.

## How the pieces fit

| Piece | Trigger | What it does |
| --- | --- | --- |
| `.github/workflows/update-f1-data.yml` | Mondays 06:00 UTC + manual | Runs `scripts/update_titles.py`, commits `data/ferrari-titles.json` if changed |
| `scripts/update_titles.py` | (called by the above) | Verifies Ferrari's latest titles, aggregates per-season wins + totals, writes the JSON. **Only writes data that passes sanity guards**; otherwise preserves the last good values |
| `.github/workflows/deploy.yml` | Push to `main` | Stages `index.html` + `assets/` + `data/` and uploads to Bluehost over SSH (secrets: `SFTP_HOST/USERNAME/PASSWORD/REMOTE_PATH`) |
| Bluehost cPanel cron (`0 1 * * *`) | Daily 1 a.m. | `curl`s the raw `data/ferrari-titles.json` from `main` into the mirror's `data/` folder |
| `.github/workflows/keepalive.yml` | Monthly | Tiny commit so GitHub never auto-disables the scheduled workflows after 60 days of inactivity |
| `.github/dependabot.yml` | Monthly | PRs to keep the workflow actions current |

## ⚠️ Things that look redundant but aren't

- **The Bluehost cron is essential, not superseded by `deploy.yml`.** Commits
  made by the update workflow use the default `GITHUB_TOKEN`, and GitHub
  deliberately does not let those trigger other workflows — so a data commit
  never fires the deploy. The nightly cron is what keeps the mirror's data
  fresh. (GitHub Pages is unaffected; it rebuilds on every push to `main`.)
- **The page works with no data file at all.** `index.html` carries baked-in
  fallback values (mirroring the committed JSON) and falls back gracefully if
  the fetch fails, so neither host can break from a data problem.

## How the page consumes the data

On load, `index.html` fetches `data/ferrari-titles.json` (same-origin) and
renders from it: the drought counter, the footer "live-verified" line, the
wins chart (bars, title markers, drought band, "NO TITLES SINCE" label), the
record-book stat counters, and the headline totals. The site name flips
between **"The Long Wait"** and **"Finally"** based on the years since
`max(driversYear, constructorsYear)` (≥ 10 years → "The Long Wait").

If Ferrari wins a title, the facts update automatically — but the narrative
prose is drought-framed and deserves an editorial rewrite when that day comes.

## Numbers: trust Jolpica, not folklore

Jolpica's authoritative count (248 wins / 836 podiums through 2025) differs
from some commonly cited figures (249/841) — e.g. it credits 1956 with 5 wins,
not 6. The page intentionally shows what the data source says, and the
script's `BASELINE` floors exist only to reject truncated/garbage API
responses, not to enforce specific totals.

## Credits

Historical data: Ergast / Jolpica-F1 community database. Car and badge
artwork generated with [Ludo.ai](https://ludo.ai). Ferrari marks are
trademarks of Ferrari S.p.A., used editorially; this is an independent,
non-commercial project not affiliated with Ferrari or Formula 1.
