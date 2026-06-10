# AGENTS.md

## What this is

GitHub Actions + Python system that polls a Taiwan government OpenData CSV
(114 全國路名資料), MD5-compares it against the last seen copy, and emails +
auto-commits on change. No server, no DB. Free-tier only.

There is also a second workflow (`yearlist.yml`) that runs
`scripts/parse_road_csv.py` to list all historical CSV download links for
[dataset/35321](https://data.gov.tw/dataset/35321). It is manual-only,
uses only the Python stdlib, and is independent of the monitor pipeline.

## Source of truth

- **`.github/workflows/*.yml`** is the authoritative source for the
  runtime contract (cron, env, steps, commit behavior).
- **`scripts/main.py`** is the orchestrator called by the monitor workflow.
  It calls `download.py`, `compare.py`, `parse_road_csv.fetch_html/build_rows`,
  and `send_email.py`. Each module exposes a `run_*` function. The workflow
  invokes `main.py` directly — it does **not** call the individual scripts.
- **`spec.md` / `README.md`** are kept in sync with the code but stay
  prose-level. When in doubt, read the workflow + the source.

## Run it locally

```bash
pip install -r requirements.txt
cd /repo/root
python scripts/main.py
```

- All file paths in `scripts/` are `Path("data/...")`, `Path("logs/...")`
  (CWD-relative). Must run from the repo root, not from inside `scripts/`.
- `scripts/__pycache__/` is created on first run. It is **already covered**
  by the root-level `__pycache__/` rule in `.gitignore` and will not show
  as untracked. No need to add a `scripts/__pycache__/` entry.
- No tests, no linter, no typecheck, no formatter. Nothing to run besides
  `pip install -r requirements.txt`.

### CWD in the workflow (already fixed)

The previous version of `.github/workflows/monitor.yml` did `cd scripts`
before `python main.py`, which made `Path("data/latest.csv")` resolve to
`scripts/data/latest.csv` and broke the subsequent `git add data/` step.
The current workflow runs `python ./scripts/main.py` directly from the
repo root, so paths line up with the `git add data/` / `git add logs/`
steps. **Do not reintroduce `cd scripts`.**

## Environment variables

| Var          | Required? | Notes                                            |
| ------------ | --------- | ------------------------------------------------ |
| `EMAIL_USER` | yes, to send mail | Gmail address (xxx@gmail.com)            |
| `EMAIL_PASS` | yes, to send mail | Gmail **App Password** (16 chars), not the account password. Requires 2-Step Verification enabled. |
| `EMAIL_TO`   | yes, to send mail | Recipient address. `send_email.py` splits on `,` and strips whitespace, so multiple recipients can be passed comma-separated. |
| `CUSTOM_URL` | no        | Override the OpenData download URL (also exposed as the `custom_url` workflow_dispatch input) |
| `FORCE_SEND` | no        | `"true"` to email even with no change. Default in the script is `"false"`; default in the `workflow_dispatch` UI is `"true"`. **The monitor workflow also has `export FORCE_SEND=true` in its `Run Monitor` step, which overrides the input and makes the `force_send` UI toggle a no-op.** Remove that line if you want the input to actually do something. |

`deepdiff` and `python-dotenv` are in `requirements.txt` but unused by
current code. `pandas` and `requests` are used by `download.py` /
`compare.py`; `parse_road_csv.py` only uses the stdlib.
Don't add new deps without checking whether they're already imported
elsewhere.

## The compare contract

`scripts/main.py` prints exactly one line to stdout, captured by the
workflow as `$RESULT` and written to `$GITHUB_OUTPUT`:

- `FIRST_RUN` — no `data/latest.hash` existed. Workflow commits.
- `CHANGED`   — MD5 of normalized CSV differs. Workflow commits + emails.
- `NO_CHANGE` — MD5 matches. Workflow does nothing.

`compare.py` normalizes the CSV by sorting columns + rows before hashing,
so row-order or column-order noise in the source does not trigger
false positives. On `CHANGED`, it also computes added rows via
`new_df.merge(old_df, how="left", indicator=True)` and passes them to
`send_email.py` to embed in the body. Each added row is also logged
individually (`added row: {...}`) for human review.
`data/previous.csv` is the local shadow of the last-seen file used for
that diff — also untracked, safe to add to `.gitignore` if you want a
clean `git status` locally.

When `send_email` is called, `main.py` also passes `year_rows` (top 3
from `parse_road_csv.build_rows()`) which is prepended to the email body
as a year-list header.

## GitHub Actions setup

- Three repo secrets: `EMAIL_USER`, `EMAIL_PASS`, `EMAIL_TO`. Nothing else.
- Cron: `15 0 * * *` — **daily** at 00:15 UTC. The inline `# cron: '15 */6 * * *'`
  comment in the workflow is a leftover from the original every-6-hours
  intent; the actual value is daily. If you change it, sync this file.
  The minute offset to `:15` avoids GitHub's known schedule delays near `:00`
  and `:30`.
- Job identity for commits: `github-actions <github-actions@github.com>`.
- Commit message format: `update opendata <UTC ISO8601>`.
- Manual trigger inputs: `force_send` (default `"true"` in YAML,
  default `"false"` in `main.py` — see table above), `custom_url`.
  `force_send` is **effectively ignored** because the workflow hardcodes
  `export FORCE_SEND=true` after reading the input.
- Required Actions permission: `contents: write` (already set).
- Second workflow `yearlist.yml` is manual-only, takes no inputs, has no
  secrets, and does not commit. It just prints the historical CSV list.

## Security notes worth preserving

- All Actions are pinned to major versions (`actions/checkout@v4`,
  `actions/setup-python@v5`). Do not float to `@main`/`@master`.
- Never `echo $EMAIL_PASS` in workflow logs.
- `.gitignore` covers `.env`, `*.key`, `secrets.json`, root-level
  `__pycache__/`, `*.pyc`, plus the unused `scripts/logs/` and
  `scripts/data/` rules. The `scripts/__pycache__/` and `data/previous.csv`
  lines that this file used to recommend adding are no longer needed:
  `__pycache__/` is already covered by the root rule, and
  `data/previous.csv` is genuinely transient (Git already retains full
  history of `data/latest.csv` so the diff is reproducible from history).

## 禁止用終端機讀檔

- 禁止使用 `run_in_terminal` / `send_to_terminal` 來讀取檔案內容。
- 讀檔一律使用 `read_file` / `grep_search` / `semantic_search` / `list_dir` / `file_search`。
- 終端機只允許用於:執行專案命令(如 `python scripts/main.py`)、安裝套件、
  `git` 操作、`pip`、`mkdir`/`mv` 等真正需要 shell 的工作。
- 違規時,應主動說明並改用正確工具。