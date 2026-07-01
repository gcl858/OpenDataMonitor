"""
自動建立修復 ISSUE。
當 download / compare / parse_road_csv 失敗時,由 scripts/main.py 呼叫。

設計重點:
- 用 `gh` CLI 開 ISSUE(GitHub Actions 內建可用,免額外依賴)
- 開 ISSUE 前先 idempotent 建立 `auto-heal` label(已存在則吞掉)
- 同標題去重,避免一小時內狂開 N 個 ISSUE
- 失敗時不應當拋例外影響主流程,錯誤一律降級為 log
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from logger_util import logger

REPO = os.environ.get("TARGET_REPO", "gcl858/OpenDataMonitor")
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("HEALER_TOKEN")
ISSUE_LABEL = os.environ.get("AUTO_HEAL_LABEL", "auto-heal")
LABEL_COLOR = os.environ.get("AUTO_HEAL_COLOR", "d93f0b")
LABEL_DESCRIPTION = "Auto-detected failure awaiting AI heal"

log = logger  # 沿用專案既有的 module-level logger(寫入 logs/history/<UTC-date>.log)


def _run(cmd: list[str]) -> tuple[int, str, str]:
    p = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return p.returncode, p.stdout, p.stderr


def _label_exists() -> bool:
    """檢查 auto-heal label 是否存在於 repo。"""
    rc, _, _ = _run(["gh", "label", "view", ISSUE_LABEL, "--repo", REPO])
    return rc == 0


def _ensure_label() -> bool:
    """Idempotent 建立 auto-heal label;若 token 無權限,只回報狀態不中斷流程。

    Returns
    -------
    bool
        True 表示 label 可供 `gh issue --label` 使用;
        False 表示 token 無權限或 label 不存在,呼叫端應跳過 --label,
        改用單純的 issue 建立(不會因此中斷主流程)。
    """
    rc, _, err = _run([
        "gh", "label", "create", ISSUE_LABEL,
        "--repo", REPO,
        "--color", LABEL_COLOR,
        "--description", LABEL_DESCRIPTION,
    ])
    if rc == 0:
        log.info("label created: %s", ISSUE_LABEL)
        return True
    msg = (err or "").lower()
    if "already exists" in msg:
        log.info("label already exists: %s", ISSUE_LABEL)
        return True
    log.warning("label create returned %d (will probe existence): %s",
                rc, (err or "").strip())
    if _label_exists():
        log.info("label exists despite create failure: %s", ISSUE_LABEL)
        return True
    log.warning("label NOT present; downstream issue commands will omit --label")
    return False


def _find_existing_open_issue(title: str) -> Optional[int]:
    """以精確標題找 open issue,避免重複開 ISSUE(label filter 已移除,
    因為 label 在某些 token 範圍下不存在;以標題比對仍足夠精準)。"""
    rc, out, err = _run([
        "gh", "issue", "list",
        "--repo", REPO,
        "--state", "open",
        "--search", f'"{title}" in:title',
        "--json", "number,title",
        "--limit", "10",
    ])
    if rc != 0:
        log.warning("gh issue list failed: %s", err)
        return None
    try:
        items = json.loads(out or "[]")
    except json.JSONDecodeError:
        return None
    for it in items:
        if it.get("title") == title:
            return it.get("number")
    return None


def open_issue(
    error_type: str,
    error_message: str,
    traceback_text: str,
    log_excerpt: str,
) -> Optional[int]:
    """
    建立(或沿用)一個 auto-heal ISSUE,並回傳 issue number。

    Parameters
    ----------
    error_type : str
        例:"DownloadError"、"YearParseError"
    error_message : str
        一行可讀的錯誤摘要
    traceback_text : str
        完整 traceback
    log_excerpt : str
        最近 N 行 log(呼叫端負責 trim)
    """
    if not TOKEN:
        log.error("GITHUB_TOKEN/HEALER_TOKEN not set; cannot open issue")
        return None

    use_label = _ensure_label()

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    title = f"[auto-heal] {error_type}: {error_message[:80]}"
    body = f"""## 自動偵測到的失敗

- **時間**: {now}
- **類型**: `{error_type}`
- **錯誤訊息**: {error_message}

## Traceback
```python
{traceback_text}
```

## 最近的 Log(最後 200 行)
```text
{log_excerpt}
```

## 建議修復方向(給 AI Agent)

1. 讀 `scripts/download.py` 與 `scripts/parse_road_csv.py`,找出對應 `{error_type}` 的程式碼路徑
2. 對照 `data.gov.tw/dataset/35321` 目前的 HTML 結構,確認 selector 是否過期
3. 必要時改用更穩定的 selector(如 `data-*` 屬性、`aria-label`、regex)
4. 補上對應的 unit test 到 `scripts/tests/`
5. 修改後跑 `python scripts/main.py` 驗證
6. 確認 `data/latest.csv` 內容正確後 commit + push + 開 PR

> 由 oh-my-pi AI Agent 自動接手處理。
> 完成後此 ISSUE 將被自動關閉,並附上 PR 連結。
"""

    existing = _find_existing_open_issue(title)
    if existing is not None:
        log.info("duplicate issue already open: #%d", existing)
        _run([
            "gh", "issue", "comment", str(existing),
            "--repo", REPO,
            "--body", f"⚠️ 同樣的失敗又在 {now} 出現了一次。\n\n```\n{error_message}\n```",
        ])
        return existing

    create_args = [
        "gh", "issue", "create",
        "--repo", REPO,
        "--title", title,
        "--body", body,
    ]
    if use_label:
        create_args += ["--label", ISSUE_LABEL]
    rc, out, err = _run(create_args)
    if rc != 0:
        log.error("gh issue create failed: %s", err)
        return None
    # gh 會印出 issue URL,例如 https://github.com/.../issues/42
    issue_url = (out or "").strip().splitlines()[-1] if out else ""
    log.info("issue created: %s", issue_url)
    try:
        return int(issue_url.rstrip("/").split("/")[-1])
    except ValueError:
        return None


def main() -> int:
    """CLI 入口,供本地手動測試:
        python scripts/auto_issue.py <error_type> <error_message> <log_file>
    """
    if len(sys.argv) < 4:
        print("usage: auto_issue.py <error_type> <error_message> <log_file>",
              file=sys.stderr)
        return 2
    error_type = sys.argv[1]
    error_message = sys.argv[2]
    log_file = Path(sys.argv[3])
    log_excerpt = ""
    if log_file.exists():
        lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
        log_excerpt = "\n".join(lines[-200:])
    tb = traceback.format_exc() or "(no traceback)"
    issue_no = open_issue(error_type, error_message, tb, log_excerpt)
    return 0 if issue_no else 1


if __name__ == "__main__":
    sys.exit(main())
