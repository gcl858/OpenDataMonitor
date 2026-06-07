# AGENTS.md

## What this is

GitHub Actions + Python system that polls a Taiwan government OpenData CSV
(114 全國路名資料), MD5-compares it against the last seen copy, and emails +
auto-commits on change. No server, no DB. Free-tier only.

## Trust the workflow, not spec.md / README

`spec.md` and `README.md` are partially stale. The real entrypoint is
`scripts/main.py` (orchestrator), which calls `download.py`, `compare.py`,
`send_email.py`. Each module exposes a `run_*` function. The workflow already
invokes `main.py` directly — it does **not** call the individual scripts
(despite what README claims).

## Run it locally

```bash
pip install -r requirements.txt
cd /repo/root
python scripts/main.py
```

- All file paths in `scripts/` are `Path("data/...")`, `Path("logs/...")`
  (CWD-relative). Must run from the repo root, not from inside `scripts/`.
- `scripts/__pycache__/` is created on first run. It is **not** in
  `.gitignore` and will show as untracked. Safe to add to `.gitignore`.
- No tests, no linter, no typecheck, no formatter. Nothing to run besides
  `pip install -r requirements.txt`.

### CWD gotcha in the workflow

`.github/workflows/monitor.yml` does `cd scripts` before `python main.py`.
That makes CWD `scripts/`, so `Path("data/latest.csv")` resolves to
`scripts/data/latest.csv`, **not** `data/latest.csv` at the repo root.
The current data files live at the repo root (from a prior local run).
This means the workflow as written likely writes to the wrong place and
the `git add data/` step wouldn't pick up the change. If you're touching
the workflow, run from the repo root and drop the `cd scripts` line.

## Environment variables

| Var          | Required? | Notes                                            |
| ------------ | --------- | ------------------------------------------------ |
| `EMAIL_USER` | yes, to send mail | Gmail address (xxx@gmail.com)            |
| `EMAIL_PASS` | yes, to send mail | Gmail **App Password** (16 chars), not the account password. Requires 2-Step Verification enabled. |
| `EMAIL_TO`   | yes, to send mail | Recipient address                          |
| `CUSTOM_URL` | no        | Override the OpenData download URL (also exposed as the `custom_url` workflow_dispatch input) |
| `FORCE_SEND` | no        | `"true"` to email even with no change. Default in the script is `"false"`; default in the `workflow_dispatch` UI is `"true"`. |

`deepdiff` and `python-dotenv` are in `requirements.txt` but unused by
current code. Don't add new deps without checking whether they're already
imported elsewhere.

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
`send_email.py` to embed in the body. `data/previous.csv` is the local
shadow of the last-seen file used for that diff — also untracked, safe
to add to `.gitignore`.

## GitHub Actions setup

- Three repo secrets: `EMAIL_USER`, `EMAIL_PASS`, `EMAIL_TO`. Nothing else.
- Cron: `15 */6 * * *` — offset to minute 15 to avoid GitHub's known
  schedule delays near :00 and :30.
- Job identity for commits: `github-actions <github-actions@github.com>`.
- Commit message format: `update opendata <UTC ISO8601>`.
- Manual trigger inputs: `force_send` (default `"true"` in YAML,
  default `"false"` in `main.py` — see table above), `custom_url`.
- Required Actions permission: `contents: write` (already set).

## Security notes worth preserving

- All Actions are pinned to major versions (`actions/checkout@v4`,
  `actions/setup-python@v5`). Do not float to `@main`/`@master`.
- Never `echo $EMAIL_PASS` in workflow logs.
- `.gitignore` covers `.env`, `*.key`, `secrets.json`. Add
  `data/previous.csv` and `scripts/__pycache__/` if you want a clean
  `git status` for local devs.
