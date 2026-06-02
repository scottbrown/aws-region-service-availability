# AWS Service Availability by Region

An interactive, static map of which AWS services are available in which AWS
regions — **with per-endpoint-type granularity**, so sub-features (e.g. Amazon
SES *inbound/SMTP* vs. its API) are distinguished from a service's overall
presence in a region.

> **Unofficial.** This project is not affiliated with, sponsored by, or endorsed
> by Amazon Web Services. It is derived from public AWS documentation and is
> provided for convenience without any guarantee of accuracy. Always consult the
> [official AWS docs](https://docs.aws.amazon.com/general/latest/gr/aws-service-information.html)
> for authoritative information.

## The map

- **Service × region** matrix grouped by continent.
- **Three-state cells**:
  - **● full** — every endpoint type for that service is offered in the region
  - **◐ partial** — only *some* endpoint types are (e.g. SES has its API in
    `ca-west-1` but not SMTP or Email-Receiving)
  - **· none** — service not offered in that region
- **Click a service** for a drawer breaking down each endpoint type (API, SMTP,
  Inbound, DKIM, …) with its exact region list, including regions excluded by a
  documentation note.
- Live search and continent / region filters.

## How it works

A fully deterministic pipeline (no API keys, no external services beyond the
public AWS docs):

| Step | Script | What it does |
|------|--------|--------------|
| 1. Discover | `scripts/discover.sh` | Pulls the service page list from the docs section TOC. |
| 2. Fetch + extract | `scripts/fetch_and_extract.sh` + `scripts/extract_endpoints.py` | Downloads each service endpoint page and extracts its endpoint-type tables + notes (regex-based, layout-independent). |
| 3. Normalize + build | `scripts/normalize_build.py` | Produces `site/aws-availability.json`: per service, per endpoint type, with `full`/`partial`/`none` region status. Reconciles name-based exclusion notes and folds FIPS/continuation tables into their parent type. |
| 4. Render | `site/index.html` | Static page that `fetch()`es the JSON. |

## Build locally

Requires `bash`, `curl`, `jq`, and `python3` (stdlib only).

```bash
make build          # runs steps 1–3, writes site/aws-availability.json
make serve          # serve site/ at http://127.0.0.1:8000
```

Or run the steps directly:

```bash
bash scripts/discover.sh
bash scripts/fetch_and_extract.sh
python3 scripts/normalize_build.py
python3 -m http.server -d site 8000
```

Intermediate files land in `build/` (git-ignored). The committed dataset is
`site/aws-availability.json`.

## Automated monthly refresh

`.github/workflows/refresh.yml` rebuilds the dataset on the 1st of each month
(and on demand via *Run workflow*), commits `site/aws-availability.json` if it
changed, and deploys `site/` to GitHub Pages.

**One-time setup:** in repo **Settings → Pages**, set *Source* to
**GitHub Actions**.

## Data & attribution

All availability facts are derived from the public AWS service endpoint pages at
`docs.aws.amazon.com/general/latest/gr/<service>.html`. Region metadata (names,
continents) lives in `scripts/region-meta.json`.

Notes:
- China (`cn-*`) and isolated (ISO / GovCloud-secret) partitions are not present
  in these public pages and are therefore excluded.
- A handful of global/console services have no regional endpoint table and are
  marked `scope: "unknown"`.

## License

Code is released under the [MIT License](LICENSE). The underlying availability
data is © Amazon Web Services and is used here as factual reference only.
