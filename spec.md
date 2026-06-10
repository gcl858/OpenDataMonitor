# GitHub Actions + Python 政府 OpenData 自動監控系統

# 系統目標

建立一套：

* 完全免費
* 不需伺服器
* 使用 GitHub Actions
* 使用 Python
* 使用 Gmail SMTP

的 OpenData 自動監控平台。

系統功能：

1. 定時下載政府 OpenData
2. 保存最新資料
3. 比對資料差異（normalize 後 MD5）
4. 計算新增列（merge + indicator）
5. 記錄完整執行 Log
6. 寄送含新增列的 Email 通知
7. 支援手動觸發 Workflow、強制寄信、臨時替換 URL

---

# 系統架構

```text
GitHub Actions
    ├─ monitor workflow (cron 15 0 * * * + workflow_dispatch)
    │       ↓
    │   scripts/main.py            ← monitor workflow 唯一入口
    │       ↓
    │       ├─ download.run_download()        → data/latest.csv
    │       ├─ compare.run_compare()          → 列印 FIRST_RUN | CHANGED | NO_CHANGE
    │       ├─ parse_road_csv.fetch_html()    → 取得 dataset/35321 HTML
    │       ├─ parse_road_csv.build_rows()    → (西元,民國,檔名,URL) 清單
    │       └─ send_email.run_send_email()    → 僅在 CHANGED 或 FORCE_SEND=true 時寄信
    │
    └─ yearlist workflow (workflow_dispatch only)
            ↓
        scripts/parse_road_csv.py   ← 單獨執行，列出歷年 CSV 下載連結
```

`monitor` workflow 對 stdout 的結果合約（`$RESULT`）：

| 輸出        | 動作               |
| ----------- | ------------------ |
| `FIRST_RUN` | Commit             |
| `CHANGED`   | Commit + Email     |
| `NO_CHANGE` | 略過               |

---

# 專案目錄結構

```text
OpenDataMonitor/
│
├── .github/
│   └── workflows/
│       ├── monitor.yml          ← 監控主流程（排程 + 手動）
│       └── yearlist.yml         ← 年度清單（僅手動）
│
├── data/
│   ├── latest.csv               ← 最新下載的原始 CSV（Git 保存歷史）
│   ├── latest.hash              ← normalize 後的 MD5
│   └── previous.csv             ← 上次下載的原始副本（供 diff 用，本機 untracked）
│
├── logs/
│   └── history/
│       ├── 2026-05-28.log
│       ├── 2026-06-07.log
│       └── ...
│
├── scripts/
│   ├── main.py                  ← monitor 編排器
│   ├── download.py              ← 下載 OpenData
│   ├── compare.py               ← MD5 比對 + 新增列
│   ├── send_email.py            ← Gmail 通知（多收件人 + 年度清單內文）
│   ├── parse_road_csv.py        ← 解析 dataset/35321 頁面（stdlib only）
│   ├── logger_util.py           ← 共用 logger
│   └── __pycache__/             ← Python 自動產生（被 .gitignore 涵蓋）
│
├── requirements.txt
├── README.md
└── spec.md
```

---

# 設計原則

## 編排器模式

`scripts/main.py` 是 workflow 唯一入口，內部依序呼叫各模組的
`run_*` 函式。各模組既可被 main.py 呼叫，也可單獨
`python scripts/<module>.py` 執行（每個模組都有 `if __name__ == "__main__"` 段落）。

## 比對策略

* 用 `pandas` 讀入 CSV
* 對欄位、行做排序（消除欄位/列序雜訊）
* 序列化後算 MD5
* 比對 `data/latest.hash` 內的舊 MD5

MD5 變化代表資料本體改變，但「改了什麼」需要進一步 diff。

## 新增列偵測

`compare.py` 內 `_find_added_rows()` 會：

1. 讀入 `data/previous.csv`（上次下載的原始副本）
2. 與新 `data/latest.csv` 對欄位排序後做 `merge(how="left", indicator=True)`
3. 篩出 `_merge == "left_only"` 的列
4. 傳給 `send_email.run_send_email(new_rows=...)` 嵌入信件內文

## 為什麼保留 `previous.csv`

原本設計宣稱「只留 `latest.csv`、靠 Git 追歷史」，但實務上需要本機的
「上一次原始副本」才能計算新增列。`data/previous.csv` 是不可變的本地
shadow：

```text
Git 負責 latest.csv 完整版本歷史
previous.csv 負責「上一次 → 這一次」的差異計算
Log 負責每次執行的紀錄
```

`previous.csv` 是 untracked 檔案（Git 透過 `data/latest.csv` 的歷史已能還原
任意時間點），可視需要加入 `.gitignore`。

---

# Python 套件

```txt
pandas
requests
deepdiff        # 目前未使用，保留供未來擴充
python-dotenv   # 目前未使用，保留供未來擴充
```

安裝：

```bash
pip install -r requirements.txt
```

---

# Logger 設計

`scripts/logger_util.py` 建立共用 logger。

```python
import logging
from pathlib import Path
from datetime import datetime

log_dir = Path("logs/history")
log_dir.mkdir(parents=True, exist_ok=True)

log_file = log_dir / f"{datetime.now():%Y-%m-%d}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("opendata-monitor")
```

> 同一個 process 內多次 import 不會重複新增 handler；handler 由
> `basicConfig` 在第一次 import 時安裝。

---

# main.py（編排器）

`scripts/main.py` 是 monitor workflow 唯一呼叫的腳本，串接下載 → 比對 → 解析年度清單 → 寄信。

```python
import os
import sys

from logger_util import logger
from download import run_download
from compare import run_compare
from send_email import run_send_email
from parse_road_csv import fetch_html, build_rows

URL = "https://data.gov.tw/dataset/35321"


def main() -> None:
    # 下載最新資料
    run_download()

    # 比對差異
    result, new_rows = run_compare()
    logger.info(f"compare result={result}")

    # 輸出結果供 GitHub Actions GITHUB_OUTPUT 捕捉
    print(result)

    # 判斷是否寄信
    force_send = os.environ.get("FORCE_SEND", "false").lower() == "true"
    should_send = result == "CHANGED" or force_send

    # 取得年度清單（信件內文抬頭用）
    html_text = fetch_html(URL)
    year_rows = build_rows(html_text)

    if should_send:
        run_send_email(new_rows=new_rows, year_rows=year_rows)
    else:
        logger.info("skip send email")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.exception(f"monitor failed: {e}")
        sys.exit(1)
```

`main.py` 對 stdout 的輸出合約：

| 輸出        | 觸發條件                                | Workflow 動作    |
| ----------- | --------------------------------------- | ---------------- |
| `FIRST_RUN` | `data/latest.hash` 不存在               | Commit           |
| `CHANGED`   | normalize 後 MD5 與上次不同              | Commit + Email   |
| `NO_CHANGE` | MD5 相同                                | 略過             |

---

# download.py

用途：

* 下載 OpenData 到 `data/latest.csv`
* 支援 `CUSTOM_URL` 環境變數覆寫下載來源
* 記錄下載 Log

```python
import os
import requests
from pathlib import Path

from logger_util import logger

# 114 全國路名資料
DEFAULT_URL = (
    "https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset"
    "/E2EDC47D-2D3F-4EB1-878A-4DEB6160FD4C/resource"
    "/6E8E059B-9E8E-403F-B3B7-BC6B95074C18/download"
)

output = Path("data/latest.csv")


def run_download(url: str = None) -> None:
    target_url = url or os.environ.get("CUSTOM_URL") or DEFAULT_URL
    try:
        logger.info("start download")
        logger.info(f"url={target_url}")
        response = requests.get(target_url, timeout=60)
        response.raise_for_status()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(response.content)
        logger.info(f"download completed size={len(response.content)}")
    except Exception as e:
        logger.exception(f"download failed: {e}")
        raise


if __name__ == "__main__":
    run_download()
```

優先序：`run_download(url=...)` 參數 > `CUSTOM_URL` 環境變數 > `DEFAULT_URL`。

---

# compare.py

用途：

* 對 CSV 做 normalize（排序欄位、列）
* 算 MD5 並比對 `data/latest.hash`
* 在變更時，計算 `previous.csv` → `latest.csv` 的新增列
* 逐列 log 新增的 row（便於人工追查）
* 列印 `FIRST_RUN` / `CHANGED` / `NO_CHANGE`

```python
import hashlib
import shutil
from pathlib import Path
from typing import Optional

import pandas as pd

from logger_util import logger

latest_file   = Path("data/latest.csv")
hash_file     = Path("data/latest.hash")
previous_file = Path("data/previous.csv")


def _find_added_rows() -> Optional[pd.DataFrame]:
    """回傳新 CSV 中有、舊 CSV 中沒有的資料列。"""
    if not previous_file.exists():
        return None
    try:
        old_df = pd.read_csv(previous_file).sort_index(axis=1)
        new_df = pd.read_csv(latest_file).sort_index(axis=1)

        # 以 left merge + indicator 找出新增列
        merged = new_df.merge(old_df, how="left", indicator=True)
        added = (
            merged[merged["_merge"] == "left_only"]
            .drop(columns=["_merge"])
            .reset_index(drop=True)
        )
        count = len(added)
        logger.info(f"added rows count={count}")
        for _, row in added.iterrows():
            logger.info(f"added row: {row.to_dict()}")
        return added if count > 0 else None
    except Exception as e:
        logger.exception(f"find added rows failed: {e}")
        return None


def run_compare() -> tuple[str, Optional[pd.DataFrame]]:
    try:
        logger.info("start compare")
        df = pd.read_csv(latest_file)
        df = df.sort_index(axis=1)
        df = df.sort_values(by=df.columns.tolist()).reset_index(drop=True)
        csv_string = df.to_csv(index=False)
        current_hash = hashlib.md5(csv_string.encode()).hexdigest()
        logger.info(f"current hash={current_hash}")

        if not hash_file.exists():
            logger.info("first run")
            hash_file.write_text(current_hash)
            shutil.copy2(latest_file, previous_file)
            return "FIRST_RUN", None
        else:
            old_hash = hash_file.read_text().strip()
            logger.info(f"old hash={old_hash}")
            if old_hash != current_hash:
                logger.info("data changed")
                added_rows = _find_added_rows()
                hash_file.write_text(current_hash)
                shutil.copy2(latest_file, previous_file)
                return "CHANGED", added_rows
            else:
                logger.info("no change")
                return "NO_CHANGE", None
    except Exception as e:
        logger.exception(f"compare failed: {e}")
        raise


if __name__ == "__main__":
    result, added = run_compare()
    print(result)
    if added is not None:
        print(added.to_string())
```

每次成功比對後都會 `shutil.copy2(latest_file, previous_file)`，
確保下一次執行有可比較的 baseline。

---

# send_email.py

用途：

* 透過 Gmail SMTP 寄送通知
* `EMAIL_TO` 以逗號區隔多收件人，逐一帶入 SMTP
* 內文抬頭嵌入 `year_rows` 前 3 筆（西元年/民國年/檔名/下載 URL）
* 若有新增列，再嵌入 `city / site_id / road` 表格
* 依是否異動切換主旨
* 使用 `email.policy.default` 確保 UTF-8 主旨正確編碼

```python
import os
import smtplib
import email.policy
from email.mime.text import MIMEText

import pandas as pd

from logger_util import logger


def run_send_email(new_rows=None, year_rows=None) -> None:
    try:
        logger.info("start send email")

        recipients = [
            addr.strip()
            for addr in os.environ["EMAIL_TO"].split(",")
            if addr.strip()
        ]
        if not recipients:
            raise ValueError("EMAIL_TO 解析後沒有有效收件人")
        logger.info(f"recipients count={len(recipients)}")

        body = ""
        # 只取 year_rows 前 3 筆，避免輸出過長
        for ad, roc, name, url in year_rows[:3]:
            body += f"{ad}年 ({roc}年) - {name} {url}\n"

        if new_rows is not None and len(new_rows) > 0:
            body += f"\n\n新增資料筆數：{len(new_rows)} 筆\n\n"
            body += new_rows[["city", "site_id", "road"]].to_csv(index=False)
            subject = f"[全國路名監控通知][有異動]新增筆數:{len(new_rows)}"
            logger.info(f"email body includes {len(new_rows)} added rows")
        else:
            body += "本次比對無異動。"
            subject = "[全國路名監控通知][無異動]"
            logger.info("email body indicates no changes")

        msg = MIMEText(body, _charset="utf-8", policy=email.policy.default)
        msg["Subject"] = subject
        msg["From"]    = os.environ["EMAIL_USER"]
        msg["To"]      = ", ".join(recipients)

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(os.environ["EMAIL_USER"], os.environ["EMAIL_PASS"])
            smtp.send_message(msg, to_addrs=recipients)

        logger.info("email sent")

    except Exception as e:
        logger.exception(f"email failed: {e}")
        raise
```

---

# parse_road_csv.py

用途：

* 抓取 [data.gov.tw/dataset/35321](https://data.gov.tw/dataset/35321) 頁面
* 從 `<script type="application/ld+json">` 內的 `schema.org/Dataset.distribution[*].contentUrl`
  抽出所有年度的全國路名 CSV 下載連結
* 對映到「XXX全國路名資料」檔名以取得民國年度
* 依西元年由新到舊排序，輸出 `(西元年, 民國年, 檔名, URL)` 清單
* **僅使用 Python 標準庫**（`urllib`、`re`、`json`、`html.unescape`、`typing`），
  不需安裝 `pandas` / `requests`

```python
import json
import re
import sys
import urllib.request
from html import unescape
from typing import List, Tuple

URL = "https://data.gov.tw/dataset/35321"
DATASET_ID = "E2EDC47D-2D3F-4EB1-878A-4DEB6160FD4C"
UUID_RE = re.compile(r"[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}")
NAME_RE = re.compile(r'"(\d{3})全國路名資料"')
BASE = f"https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/{DATASET_ID}/resource/"


def fetch_html(source: str) -> str:
    """從 URL 或本地路徑取得 HTML 內容。"""
    if source.startswith("http://") or source.startswith("https://"):
        req = urllib.request.Request(
            source,
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"},
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8", errors="replace")
    with open(source, "r", encoding="utf-8") as f:
        return f.read()


def parse_distribution(html_text: str) -> List[str]:
    """從 JSON-LD 抽出 distribution[*].contentUrl。"""
    m = re.search(
        r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
        html_text,
        re.S,
    )
    if not m:
        raise RuntimeError("找不到 JSON-LD 區塊")
    payload = json.loads(unescape(m.group(1)))
    if isinstance(payload, list):
        dataset = next((x for x in payload if x.get("@type") == "Dataset"), payload[0])
    else:
        dataset = payload
    return [d["contentUrl"] for d in dataset.get("distribution", [])]


def parse_year_map(html_text: str) -> dict:
    """把每個 resource UUID 對到「XXX全國路名資料」檔名（XXX 為民國年度）。"""
    pairs = {}
    for m in re.finditer(r"/resource/(" + UUID_RE.pattern + r")/download", html_text):
        u = m.group(1)
        near = html_text[max(0, m.start() - 400): m.end() + 400]
        nm = NAME_RE.search(near)
        if nm:
            pairs[u] = f"{nm.group(1)}全國路名資料"
    return pairs


def build_rows(html_text: str) -> List[Tuple[int, int, str, str]]:
    """組合 (西元年, 民國年, 檔名, 下載URL) 清單，依西元年新→舊排序。"""
    urls = parse_distribution(html_text)
    year_map = parse_year_map(html_text)
    rows = []
    for url in urls:
        m = re.search(r"/resource/(" + UUID_RE.pattern + r")/download", url)
        if not m:
            continue
        u = m.group(1)
        name = year_map.get(u, f"(未知年度){u[:8]}")
        roc = int(name[:3])
        ad = roc + 1911
        rows.append((ad, roc, name, url))
    rows.sort(key=lambda x: -x[0])
    return rows
```

被呼叫方式：

* `scripts/main.py` 內 `from parse_road_csv import fetch_html, build_rows`，
  把前 3 筆嵌入 `send_email` 內文
* `yearlist.yml` workflow 直接 `python -u ./scripts/parse_road_csv.py` 執行

---

# Gmail 設定

## 啟用兩步驟驗證

Google Account：

```text
Security
→ 2-Step Verification
```

## 建立 App Password

Google：

```text
Security
→ App Passwords
```

建立：

```text
Mail
GitHub Actions
```

取得 16 碼密碼 → 填入 `EMAIL_PASS` Secret。

---

# 環境變數

| 變數          | 必要？       | 說明                                                                |
| ------------- | ------------ | ------------------------------------------------------------------- |
| `EMAIL_USER`  | 寄信時必填    | Gmail 帳號                                                          |
| `EMAIL_PASS`  | 寄信時必填    | Gmail App Password（16 碼）                                        |
| `EMAIL_TO`    | 寄信時必填    | 收件人 Email；以逗號區隔多個（例：`a@x.com,b@x.com`），`send_email.py` 會 split + strip |
| `CUSTOM_URL`  | 選填         | 覆蓋 OpenData 下載 URL（`download.run_download()` 內 `os.environ.get("CUSTOM_URL")` 讀取） |
| `FORCE_SEND`  | 選填         | `"true"` 強制寄信（即使 `NO_CHANGE`）。`main.py` 預設 `"false"`；workflow_dispatch 預設 `"true"`。⚠ `monitor.yml` 內另有 `export FORCE_SEND=true` 強制覆寫（見下方「行為細節」） |

---

# GitHub Secrets

Repository：

```text
Settings
→ Secrets and variables
→ Actions
```

新增：

| Secret     | 用途                 |
| ---------- | ------------------ |
| EMAIL_USER | Gmail 帳號           |
| EMAIL_PASS | Gmail App Password |
| EMAIL_TO   | 收件人 Email（可逗號區隔多個） |

GitHub 官方提供 encrypted secrets。

---

# GitHub Actions Workflow

專案有兩個 workflow：

| Workflow        | 觸發                | 入口                     | 用途                                   |
| --------------- | ------------------- | ------------------------ | -------------------------------------- |
| `monitor.yml`   | cron + 手動          | `scripts/main.py`        | 下載、比對、寄信、auto-commit          |
| `yearlist.yml`  | 僅手動              | `scripts/parse_road_csv.py` | 列出 dataset/35321 歷年 CSV 下載連結 |

## 完整 monitor workflow（與 `monitor.yml` 同步）

```yaml
name: OpenData Monitor

on:
  # 排程執行 - cron: '15 */6 * * *'   ← 註解標示原始意圖
  schedule:
    - cron: '15 0 * * *'             # 實際值：每日 UTC 00:15

  workflow_dispatch:
    inputs:
      force_send:
        description: '強制寄送 Email'
        required: false
        default: 'true'
      custom_url:
        description: '自訂 OpenData URL'
        required: false
        default: ''

jobs:
  monitor:
    runs-on: ubuntu-latest
    permissions:
      contents: write

    steps:
      - name: Checkout Repository
        uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install Packages
        run: pip install -r requirements.txt

      - name: Run Monitor
        id: monitor
        env:
          CUSTOM_URL: ${{ github.event.inputs.custom_url }}
          FORCE_SEND: ${{ github.event.inputs.force_send }}
          EMAIL_USER: ${{ secrets.EMAIL_USER }}
          EMAIL_PASS: ${{ secrets.EMAIL_PASS }}
          EMAIL_TO:   ${{ secrets.EMAIL_TO }}
        run: |
          export FORCE_SEND=true          # ⚠ 覆寫 workflow_dispatch 輸入
          RESULT=$(python ./scripts/main.py)
          echo "result=$RESULT" >> $GITHUB_OUTPUT

      - name: Commit Files
        if: |
          steps.monitor.outputs.result == 'CHANGED' ||
          steps.monitor.outputs.result == 'FIRST_RUN'
        run: |
          git config user.name  github-actions
          git config user.email github-actions@github.com
          git add data/
          git add logs/
          git commit -m "update opendata $(date -u +%Y-%m-%dT%H:%M:%SZ)"
          git push
```

## 完整 yearlist workflow（與 `yearlist.yml` 同步）

```yaml
name: Year List CSV

on:
  workflow_dispatch:                  # 僅手動觸發（cron 已註解）

jobs:
  monitor:
    runs-on: ubuntu-latest
    permissions:
      contents: write

    steps:
      - name: Checkout Repository
        uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Run YearList
        id: yearlist
        env:
          PYTHONUNBUFFERED: 1
        run: python -u ./scripts/parse_road_csv.py
```

此 workflow 不安裝套件（`parse_road_csv.py` 僅用 stdlib），也不寫入 `data/`、
不發送 Email、不 commit。

## CWD 約定

workflow 在 `Run Monitor` 步驟**不**做 `cd scripts`，而是直接
`python ./scripts/main.py`，CWD 維持在 repo 根目錄。
這與 `scripts/` 內所有 `Path("data/...")`、`Path("logs/...")` 相對路徑一致，
也與 `git add data/`、`git add logs/` 的相對路徑一致。

> 早期版本曾有 `cd scripts`，會把資料寫入 `scripts/data/`，並讓
> `git add data/` 抓不到變更；此問題已在目前 workflow 修正。

## 排程觸發

```yaml
schedule:
  - cron: '15 0 * * *'
```

代表：

```text
每日 UTC 00:15 執行一次
```

> 註解 `# 排程執行 - cron: '15 */6 * * *'` 是早期意圖的紀錄，
> 實際排程為每日一次。如要恢復每 6 小時執行，請把 cron 改回 `15 */6 * * *` 並同步文件。

### 為什麼避免整點

GitHub Actions 在：

```text
00 分
30 分
```

容易排隊 delay。`15` 是常見的偏移分鐘，能降低排隊機率。

## 手動觸發

GitHub 官方提供 `workflow_dispatch`，可從：

* GitHub UI
* GitHub CLI
* REST API

手動執行 workflow。

### GitHub UI 手動執行

```text
Actions
→ OpenData Monitor
→ Run workflow
```

即可執行。

### workflow_dispatch Inputs

| Input      | 預設    | 功能           | 備註 |
| ---------- | ------ | ------------ | ---- |
| force_send | `true` | 即使無變更也寄信 | ⚠ `Run Monitor` 步驟有 `export FORCE_SEND=true` 覆寫，目前輸入實際無作用 |
| custom_url | `""`   | 臨時測試資料源   | 直接傳入 `CUSTOM_URL` env，會被 `download.run_download()` 讀取 |

### GitHub CLI 手動執行

```bash
gh workflow run monitor.yml
gh workflow run monitor.yml -f force_send=true
gh workflow run monitor.yml -f custom_url=https://example.gov/data.csv
```

---

# 行為細節

## Commit 條件

* `FIRST_RUN` 與 `CHANGED` 都會 commit
* `NO_CHANGE` 略過
* 提交內容包含 `data/` 與 `logs/` 的變更
* Commit 訊息格式：`update opendata <UTC ISO8601>`（例：`update opendata 2026-06-07T02:15:00Z`）
* Git 身份：`github-actions <github-actions@github.com>`

## Email 寄信條件

* `CHANGED`：一定寄
* `NO_CHANGE` + `FORCE_SEND=true`：寄（信件標記「無異動」、內文「本次比對無異動。」）
* `NO_CHANGE` + `FORCE_SEND` 未設定或為 `false`：不寄

> ⚠ **現實**：monitor workflow 內 `Run Monitor` 步驟含有 `export FORCE_SEND=true`，
> 會覆蓋掉來自 `workflow_dispatch.inputs.force_send` 的值。
> 因此 `force_send` 輸入目前是無作用的；`NO_CHANGE` 時 workflow 仍會寄出「無異動」通知。
> 若要恢復輸入控制權，請移除 `export FORCE_SEND=true` 那一行。

## 信件內文組成

`run_send_email(new_rows, year_rows)` 會把內文組裝成：

1. **抬頭**：`year_rows` 前 3 筆，每行格式 `<西元年>年 (<民國年>年) - <檔名> <URL>`
2. **差異段**（僅 `new_rows` 非空時）：
   * `新增資料筆數：<N> 筆`
   * 內嵌 `city,site_id,road` 三欄的 CSV
3. **無異動段**（`new_rows` 為空時）：`本次比對無異動。`

主旨：

* 有異動：`[全國路名監控通知][有異動]新增筆數:<N>`
* 無異動：`[全國路名監控通知][無異動]`

## 新增列格式

信件內文會以 CSV 形式列出 `city,site_id,road` 三欄，例：

```csv
city,site_id,road
新北市,63000100,新興路
新北市,63000200,中山路
```

---

# Log 範例

## 首次執行

```text
2026-05-28 08:00:01 [INFO] start download
2026-05-28 08:00:01 [INFO] url=https://opdadm.moi.gov.tw/...
2026-05-28 08:00:03 [INFO] download completed size=1456765
2026-05-28 08:00:03 [INFO] start compare
2026-05-28 08:00:03 [INFO] current hash=abcd1234...
2026-05-28 08:00:03 [INFO] first run
2026-05-28 08:00:03 [INFO] compare result=FIRST_RUN
2026-05-28 08:00:03 [INFO] skip send email
```

## 有異動

```text
2026-06-07 02:15:01 [INFO] start download
2026-06-07 02:15:01 [INFO] url=https://opdadm.moi.gov.tw/...
2026-06-07 02:15:03 [INFO] download completed size=1458000
2026-06-07 02:15:03 [INFO] start compare
2026-06-07 02:15:03 [INFO] current hash=1111aaaa
2026-06-07 02:15:03 [INFO] old hash=2222bbbb
2026-06-07 02:15:03 [INFO] data changed
2026-06-07 02:15:03 [INFO] added rows count=2
2026-06-07 02:15:03 [INFO] added row: {'city': '澎湖縣', 'road': '鼎灣', 'site_id': '澎湖縣湖西鄉'}
2026-06-07 02:15:03 [INFO] added row: {'city': '澎湖縣', 'road': '潭邊', 'site_id': '澎湖縣湖西鄉'}
2026-06-07 02:15:03 [INFO] compare result=CHANGED
2026-06-07 02:15:03 [INFO] start send email
2026-06-07 02:15:03 [INFO] recipients count=1
2026-06-07 02:15:03 [INFO] email body includes 2 added rows
2026-06-07 02:15:05 [INFO] email sent
```

## 無異動

```text
2026-06-07 08:15:01 [INFO] start compare
2026-06-07 08:15:01 [INFO] current hash=1111aaaa
2026-06-07 08:15:01 [INFO] old hash=1111aaaa
2026-06-07 08:15:01 [INFO] no change
2026-06-07 08:15:01 [INFO] compare result=NO_CHANGE
2026-06-07 08:15:01 [INFO] skip send email
```

## 錯誤

```text
2026-05-28 08:00:01 [INFO] start download
2026-05-28 08:00:31 [ERROR] download failed
TimeoutError
```

---

# Git 的角色

Git 保存：

* `data/latest.csv` 完整歷史
* `logs/history/<日期>.log` 執行紀錄
* commit 訊息（內含 UTC 時間戳）
* diff

因此 `data/previous.csv` 不需要進 Git（Git 隨時可從 `latest.csv` 的
歷史還原任意時間點的內容）。`previous.csv` 屬於 untracked。

---

# 安全建議

## 不要 commit secrets

`.gitignore` 應至少包含：

```gitignore
.env
*.key
secrets.json
```

目前 repo 的 `.gitignore`：

```gitignore
.env
*.key
secrets.json

# Python
__pycache__/
*.pyc

# Runtime files
scripts/logs/
scripts/data/
```

* `__pycache__/` 已涵蓋 — 不需要再加 `scripts/__pycache__/`
* `scripts/logs/`、`scripts/data/` 規則目前無作用（CWD-relative 路徑實際寫到
  repo 根目錄的 `data/`、`logs/`，不是 `scripts/data/`、`scripts/logs/`）
* `data/previous.csv` 未被忽略（untracked 仍會出現在 `git status`）；
  如希望本機 `git status` 更乾淨，可手動加入 `data/previous.csv`

## 不要 print secrets

避免：

```yaml
run: echo $EMAIL_PASS
```

## 不要使用不可信 Action

建議：

```yaml
uses: actions/checkout@v4
uses: actions/setup-python@v5
```

不要：

```yaml
@main
@master
```

GitHub Actions supply-chain attack 是真實風險，請固定釘在主要版本。

---

# 結論

本架構具備：

* 完全免費
* GitHub 原生 CI/CD
* 自動排程
* 手動觸發（可強制寄信、自訂 URL）
* Gmail SMTP 通知（含新增列明細）
* 完整 Log（每日檔案）
* Git 版本控制（每次異動自動 commit）
* 不需伺服器
* 不需 Docker
* 不需資料庫

非常適合：

* 政府 OpenData 監控
* 法規更新監控
* 公開 API 監控
* CSV/JSON 資料同步
* 定期資料檢查
