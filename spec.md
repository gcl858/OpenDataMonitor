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
3. 比對資料差異
4. 記錄完整執行 Log
5. 發送 Email 通知
6. 支援手動觸發 Workflow

---

# 系統架構

```text id="ggc8n9"
GitHub Actions
    ├─ 排程觸發
    └─ 手動觸發
            ↓
Python Scripts
    ↓
下載 OpenData
    ↓
Normalize 資料
    ↓
比對差異
    ↓
寫入 Log
    ↓
有變更
    ├─ Git Commit
    ├─ Push Repository
    └─ Gmail 通知
```

---

# 專案目錄結構

```text id="i4j9xp"
my-opendata-monitor/
│
├── .github/
│   └── workflows/
│       └── monitor.yml
│
├── data/
│   └── latest.csv
│
├── logs/
│   └── history/
│       ├── 2026-05-28.log
│       ├── 2026-05-29.log
│       └── ...
│
├── scripts/
│   ├── download.py
│   ├── compare.py
│   ├── send_email.py
│   └── logger_util.py
│
├── requirements.txt
└── README.md
```

---

# 設計原則

---

# 為什麼不保存舊 CSV

原本設計：

```text id="t7jpkf"
history/previous.csv
```

有幾個問題：

* 重複保存大量資料
* Git 本身已經有版本控制
* CSV 歷史容易爆容量
* Git diff 已經能追蹤檔案差異

因此：

```text id="by6w5y"
Git 負責版本歷史
Log 負責執行紀錄
```

才是較合理架構。

---

# Git 的角色

Git 自動保存：

* 每次變更
* 差異內容
* commit 時間
* 修改紀錄

因此：

```text id="zyhhvc"
latest.csv 即可
```

---

# Log 的角色

logs/history/ 保存：

* 執行時間
* workflow 狀態
* 差異摘要
* 錯誤訊息
* Email 發送結果

---

# Python 套件

---

# requirements.txt

```txt id="b6b5l2"
pandas
requests
deepdiff
python-dotenv
```

安裝：

```bash id="p0nt9w"
pip install -r requirements.txt
```

---

# Logger 設計

---

# logger_util.py

建立共用 logger。

```python id="8s5syv"
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

---

# download.py

用途：

* 下載 OpenData
* 保存 latest.csv
* 記錄下載 Log

```python id="63s1g6"
import requests
from pathlib import Path

from logger_util import logger
//114全國路名資料
URL = "https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/E2EDC47D-2D3F-4EB1-878A-4DEB6160FD4C/resource/6E8E059B-9E8E-403F-B3B7-BC6B95074C18/download"

output = Path("data/latest.csv")

try:

    logger.info("start download")

    response = requests.get(URL, timeout=60)

    response.raise_for_status()

    output.parent.mkdir(parents=True, exist_ok=True)

    output.write_bytes(response.content)

    logger.info(
        f"download completed size={len(response.content)}"
    )

except Exception as e:

    logger.exception(f"download failed: {e}")

    raise
```

---

# compare.py

用途：

* 比對新舊資料
* 記錄差異資訊
* 寫入 log

---

# 差異策略

使用：

```text id="v31kgl"
MD5 Hash
```

比對 normalize 後的 CSV。

---

# compare.py

```python id="5quu9l"
import hashlib
from pathlib import Path

import pandas as pd

from logger_util import logger

latest_file = Path("data/latest.csv")

hash_file = Path("data/latest.hash")

try:

    logger.info("start compare")

    df = pd.read_csv(latest_file)

    df = df.sort_index(axis=1)

    df = df.sort_values(
        by=df.columns.tolist()
    ).reset_index(drop=True)

    csv_string = df.to_csv(index=False)

    current_hash = hashlib.md5(
        csv_string.encode()
    ).hexdigest()

    logger.info(f"current hash={current_hash}")

    if not hash_file.exists():

        logger.info("first run")

        hash_file.write_text(current_hash)

        print("FIRST_RUN")

    else:

        old_hash = hash_file.read_text().strip()

        logger.info(f"old hash={old_hash}")

        if old_hash != current_hash:

            logger.info("data changed")

            hash_file.write_text(current_hash)

            print("CHANGED")

        else:

            logger.info("no change")

            print("NO_CHANGE")

except Exception as e:

    logger.exception(f"compare failed: {e}")

    raise
```

---

# send_email.py

用途：

* Gmail SMTP 發送通知
* 記錄 Email Log

```python id="bq6cdd"
import os
import smtplib

from email.mime.text import MIMEText

from logger_util import logger

try:

    logger.info("start send email")

    msg = MIMEText(
        "政府 OpenData 已更新"
    )

    msg["Subject"] = "OpenData Changed"

    msg["From"] = os.environ["EMAIL_USER"]

    msg["To"] = os.environ["EMAIL_TO"]

    with smtplib.SMTP_SSL(
        "smtp.gmail.com",
        465
    ) as smtp:

        smtp.login(
            os.environ["EMAIL_USER"],
            os.environ["EMAIL_PASS"]
        )

        smtp.send_message(msg)

    logger.info("email sent")

except Exception as e:

    logger.exception(f"email failed: {e}")

    raise
```

---

# Gmail 設定

---

# 啟用兩步驟驗證

Google Account：

```text id="uqt4oz"
Security
→ 2-Step Verification
```

---

# 建立 App Password

Google：

```text id="vfq42g"
Security
→ App Passwords
```

建立：

```text id="rjz2t9"
Mail
GitHub Actions
```

取得：

```text id="mgm9p2"
16位數密碼
```

---

# GitHub Secrets

Repository：

```text id="crjdbx"
Settings
→ Secrets and variables
→ Actions
```

新增：

| Secret     | 用途                 |
| ---------- | ------------------ |
| EMAIL_USER | Gmail 帳號           |
| EMAIL_PASS | Gmail App Password |
| EMAIL_TO   | 收件人 Email          |

GitHub 官方提供 encrypted secrets。

---

# GitHub Actions Workflow

---

# monitor.yml

位置：

```text id="pmb1mp"
.github/workflows/monitor.yml
```

---

# 完整 Workflow

```yaml id="44zn5l"
name: OpenData Monitor

on:

  # 排程執行
  schedule:
    - cron: '15 */6 * * *'

  # 手動執行
  workflow_dispatch:

    inputs:

      force_send:
        description: '強制寄送 Email'
        required: false
        default: 'false'

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
        run: |
          pip install -r requirements.txt

      - name: Run Download
        run: |
          python scripts/download.py

      - name: Run Compare
        id: compare
        run: |

          RESULT=$(python scripts/compare.py)

          echo "result=$RESULT" >> $GITHUB_OUTPUT

      - name: Commit Files
        if: |
          steps.compare.outputs.result == 'CHANGED'

        run: |

          git config user.name github-actions
          git config user.email github-actions@github.com

          git add data/
          git add logs/

          git commit -m "update opendata"

          git push

      - name: Send Email
        if: |
          steps.compare.outputs.result == 'CHANGED' ||
          github.event.inputs.force_send == 'true'

        env:
          EMAIL_USER: ${{ secrets.EMAIL_USER }}
          EMAIL_PASS: ${{ secrets.EMAIL_PASS }}
          EMAIL_TO: ${{ secrets.EMAIL_TO }}

        run: |
          python scripts/send_email.py
```

---

# 排程觸發

---

# cron

```yaml id="4ns6xh"
schedule:
  - cron: '15 */6 * * *'
```

代表：

```text id="n8svu7"
每 6 小時執行一次
於第 15 分開始
```

---

# 為什麼避免整點

GitHub Actions 在：

```text id="2hcvkg"
00分
30分
```

容易排隊 delay。

Reddit 上也有大量使用者遇到 schedule delay。

建議：

```text id="s3nlr4"
15
23
37
```

等偏移分鐘。

---

# 手動觸發

GitHub 官方提供：

```yaml id="gkh8n9"
workflow_dispatch
```

可從：

* GitHub UI
* GitHub CLI
* REST API

手動執行 workflow。

---

# GitHub UI 手動執行

```text id="mbt14z"
Actions
→ OpenData Monitor
→ Run workflow
```

即可執行。

---

# workflow_dispatch Inputs

本系統支援：

| Input      | 功能       |
| ---------- | -------- |
| force_send | 即使無變更也寄信 |
| custom_url | 臨時測試資料源  |

GitHub 官方支援 workflow_dispatch inputs。

---

# GitHub CLI 手動執行

安裝：

```bash id="l0sqw7"
gh
```

執行：

```bash id="8wmv13"
gh workflow run monitor.yml
```

帶參數：

```bash id="ot7g7v"
gh workflow run monitor.yml \
  -f force_send=true
```

---

# Log 範例

---

# 成功執行

```text id="9mjlwm"
2026-05-28 08:00:01 [INFO] start download
2026-05-28 08:00:03 [INFO] download completed size=23511
2026-05-28 08:00:03 [INFO] start compare
2026-05-28 08:00:03 [INFO] current hash=xxxx
2026-05-28 08:00:03 [INFO] old hash=yyyy
2026-05-28 08:00:03 [INFO] data changed
2026-05-28 08:00:04 [INFO] start send email
2026-05-28 08:00:05 [INFO] email sent
```

---

# 錯誤執行

```text id="w9s9np"
2026-05-28 08:00:01 [INFO] start download
2026-05-28 08:00:31 [ERROR] download failed
TimeoutError
```

---

# Git 的角色

Git 保存：

* latest.csv 歷史版本
* logs/history/
* commit 記錄
* diff

因此：

```text id="j49d6v"
不需要保存 previous.csv
```

---

# 安全建議

---

# 不要 commit secrets

加入：

## .gitignore

```gitignore id="0iy4ho"
.env
*.key
secrets.json
```

---

# 不要 print secrets

避免：

```yaml id="jlwmtt"
run: echo $EMAIL_PASS
```

---

# 不要使用不可信 Action

建議：

```yaml id="5s8z85"
uses: actions/checkout@v4
```

不要：

```yaml id="fnhd7i"
@main
```

GitHub Actions supply-chain attack 是真實風險。

---

# 結論

本架構具備：

* 完全免費
* GitHub 原生 CI/CD
* 自動排程
* 手動觸發
* Gmail 通知
* 完整 Log
* Git 版本控制
* 不需伺服器
* 不需 Docker
* 不需資料庫

非常適合：

* 政府 OpenData 監控
* 法規更新監控
* 公開 API 監控
* CSV/JSON 資料同步
* 定期資料檢查
