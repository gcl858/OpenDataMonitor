# OpenData Monitor

政府 OpenData 自動監控系統，使用 GitHub Actions + Python + Gmail SMTP。

## 功能

- 每 6 小時自動下載 OpenData（114 全國路名資料）
- MD5 Hash 比對 normalize 後的 CSV，偵測資料異動
- 資料有異動時自動 Git commit & push，並寄送含有「新增列」清單的 Email
- 首次執行（沒有 hash 檔）時直接 commit
- 支援手動觸發、強制寄信、臨時替換下載 URL

## 目錄結構

```
.github/workflows/monitor.yml   # GitHub Actions workflow
scripts/
  logger_util.py                # 共用 logger
  main.py                       # 編排器（workflow 唯一入口）
  download.py                   # 下載 OpenData
  compare.py                    # MD5 比對 + 找出新增列
  send_email.py                 # Gmail 通知
  __pycache__/                  # Python 自動產生（未追蹤）
data/
  latest.csv                    # 最新資料（Git 保存歷史）
  latest.hash                   # 上次 normalize 後的 MD5
  previous.csv                  # 上次下載的原始副本（供 diff 用）
logs/
  history/<YYYY-MM-DD>.log      # 每日執行 log
requirements.txt
```

## 架構

`scripts/main.py` 是唯一入口，依序呼叫各模組的 `run_*` 函式：

```
main.py
  ├─ download.run_download()       → data/latest.csv
  ├─ compare.run_compare()         → 列印 FIRST_RUN | CHANGED | NO_CHANGE
  └─ send_email.run_send_email()   → 僅在 CHANGED 或 FORCE_SEND=true 時寄信
```

`compare` 在 `CHANGED` 時會比對 `data/previous.csv`（上一次的本機副本）與新的
`data/latest.csv`，以 `merge(..., indicator=True)` 找出新增列，傳給 `send_email`
嵌入信件內文。

## 環境需求

```bash
pip install -r requirements.txt
```

## 本地執行

```bash
cd /repo/root
python scripts/main.py
```

> **CWD 注意事項**：`scripts/` 內所有路徑都是 `Path("data/...")`、
> `Path("logs/...")`，相對於 CWD。必須從 repo 根目錄執行，不能從
> `scripts/` 內執行。
>
> `scripts/__pycache__/` 在第一次執行後會自動生成，未列入 `.gitignore`，
> 會出現在 `git status` 視為 untracked。可視需要加入 `.gitignore`。

## 環境變數

| 變數          | 必要？       | 說明                                                                  |
| ------------- | ------------ | --------------------------------------------------------------------- |
| `EMAIL_USER`  | 寄信時必填    | Gmail 帳號（`xxx@gmail.com`）                                        |
| `EMAIL_PASS`  | 寄信時必填    | Gmail **App Password**（16 碼），不是帳號密碼。需先啟用兩步驟驗證。   |
| `EMAIL_TO`    | 寄信時必填    | 收件人 Email，可多個以逗號區隔（例：`a@x.com,b@x.com`）                |
| `CUSTOM_URL`  | 選填         | 覆蓋 OpenData 下載 URL（也可從 workflow_dispatch 的 `custom_url` 輸入） |
| `FORCE_SEND`  | 選填         | `"true"` 即使無異動也寄信。`main.py` 預設 `"false"`，workflow 預設 `"true"`。 |

## GitHub Secrets 設定

`Settings → Secrets and variables → Actions` 新增以下三個 Secret：

| Secret       | 說明                        |
| ------------ | --------------------------- |
| `EMAIL_USER` | Gmail 帳號（xxx@gmail.com） |
| `EMAIL_PASS` | Gmail App Password（16碼）  |
| `EMAIL_TO`   | 收件人 Email（可逗號區隔多個） |

### 取得 Gmail App Password

1. Google Account → Security → 2-Step Verification（啟用）
2. Google Account → Security → App Passwords
3. 建立名稱：`Mail / GitHub Actions`
4. 取得 16 碼密碼，填入 `EMAIL_PASS`

## 比對輸出合約

`main.py` 會在 stdout 列印恰好一行，被 workflow 擷取為 `$RESULT` 並寫入
`$GITHUB_OUTPUT`：

| 輸出        | 意義                                                | Workflow 動作   |
| ----------- | --------------------------------------------------- | --------------- |
| `FIRST_RUN` | 沒有 `data/latest.hash`（首次執行）                 | Commit          |
| `CHANGED`   | normalize 後的 MD5 與上次不同                      | Commit + Email  |
| `NO_CHANGE` | MD5 相同                                            | 略過            |

`compare.py` 會先把 CSV 對欄位、行做排序後再算 MD5，因此來源端欄位順序或
列序的雜訊不會誤觸變更通知。

## 手動觸發

### GitHub UI

```
Actions → OpenData Monitor → Run workflow
```

| Input        | 預設     | 說明                                         |
| ------------ | -------- | -------------------------------------------- |
| `force_send` | `true`   | 強制寄送 Email（即使無異動）                 |
| `custom_url` | `""`     | 臨時替換下載來源 URL                         |

> `force_send` 在 `main.py` 內的預設是 `"false"`，但 workflow YAML 的
> `workflow_dispatch` 預設是 `"true"`。手動觸發時兩者都會傳到 `FORCE_SEND`
> 環境變數，最後一個被 GitHub Actions 設定的值才是有效值（手動觸發時以
> workflow 為準）。

### GitHub CLI

```bash
# 一般觸發
gh workflow run monitor.yml

# 強制發信
gh workflow run monitor.yml -f force_send=true

# 使用自訂 URL
gh workflow run monitor.yml -f custom_url=https://example.gov/data.csv
```

## 安全注意事項

- 不要將 `.env`、`*.key`、`secrets.json` commit 進 repository
- 不要在 workflow 中 `echo` secrets
- 僅使用已釘定主要版本的 Actions（如 `@v4`、`@v5`），避免 supply-chain attack
- Actions 權限僅需 `contents: write`
