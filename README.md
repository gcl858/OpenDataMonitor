# OpenData Monitor

政府 OpenData 自動監控系統，使用 GitHub Actions + Python + Gmail SMTP。

## 功能

- 排程自動下載 OpenData（114 全國路名資料）
- MD5 Hash 比對 normalize 後的 CSV，偵測資料異動
- 資料有異動時自動 Git commit & push，並寄送含有「新增列」清單的 Email
- 首次執行（沒有 hash 檔）時直接 commit
- 支援手動觸發、強制寄信、臨時替換下載 URL
- 額外提供「年度清單」workflow，從 [data.gov.tw/dataset/35321](https://data.gov.tw/dataset/35321) 解析歷年 CSV 下載連結

## 目錄結構

```
.github/workflows/
  monitor.yml                    # 監控主流程（排程 + 手動觸發）
  yearlist.yml                   # 列出 dataset/35321 歷年 CSV 連結（手動觸發）
scripts/
  logger_util.py                 # 共用 logger
  main.py                        # 編排器（monitor workflow 唯一入口）
  download.py                    # 下載 OpenData
  compare.py                     # MD5 比對 + 找出新增列
  send_email.py                  # Gmail 通知
  parse_road_csv.py              # 解析 data.gov.tw 年度清單（stdlib only）
  auto_issue.py                  # 失敗時自動建 GitHub ISSUE（auto-heal 機制）
  __pycache__/                   # Python 自動產生（.gitignore 已涵蓋）
data/
  latest.csv                     # 最新資料（Git 保存歷史）
  latest.hash                    # 上次 normalize 後的 MD5
  previous.csv                   # 上次下載的原始副本（供 diff 用）
logs/
  history/<YYYY-MM-DD>.log       # 每日執行 log
requirements.txt
```

## 架構

### monitor workflow（資料監控）

`scripts/main.py` 是 monitor workflow 的唯一入口，依序呼叫各模組的 `run_*` 函式：

```
main.py
  ├─ download.run_download()              → data/latest.csv
  ├─ compare.run_compare()                → 列印 FIRST_RUN | CHANGED | NO_CHANGE
  ├─ parse_road_csv.fetch_html/build_rows → 取得年度清單（用於信件內文）
  └─ send_email.run_send_email()          → 僅在 CHANGED 或 FORCE_SEND=true 時寄信
```

`compare` 在 `CHANGED` 時會比對 `data/previous.csv`（上一次的本機副本）與新的
`data/latest.csv`，以 `merge(..., indicator=True)` 找出新增列，傳給 `send_email`
嵌入信件內文。`send_email` 會把 `year_rows` 的前 3 筆（西元年 / 民國年 / 檔名 / URL）
附加在信件最前面，方便對照。

### yearlist workflow（年度清單）

`scripts/parse_road_csv.py` 抓取 [data.gov.tw/dataset/35321](https://data.gov.tw/dataset/35321) 頁面：
1. 解析 `<script type="application/ld+json">` 內的 `schema.org/Dataset.distribution[*].contentUrl`
2. 對映到每個 resource 的「XXX全國路名資料」檔名（XXX 為民國年度）
3. 依西元年由新到舊排序輸出

僅使用 Python 標準庫（`urllib`、`re`、`json`、`html.unescape`），無需額外相依套件。

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
> `scripts/__pycache__/` 在第一次執行後會自動生成，已被根目錄的
> `.gitignore` 規則 `__pycache__/` 涵蓋，不會出現在 `git status`。

## 環境變數

| 變數          | 必要？       | 說明                                                                  |
| ------------- | ------------ | --------------------------------------------------------------------- |
| `EMAIL_USER`  | 寄信時必填    | Gmail 帳號（`xxx@gmail.com`）                                        |
| `EMAIL_PASS`  | 寄信時必填    | Gmail **App Password**（16 碼），不是帳號密碼。需先啟用兩步驟驗證。   |
| `EMAIL_TO`    | 寄信時必填    | 收件人 Email，可多個以逗號區隔（例：`a@x.com,b@x.com`）                |
| `CUSTOM_URL` | 選填         | 覆蓋 OpenData 下載 URL（也可從 workflow_dispatch 的 `custom_url` 輸入） |
| `FORCE_SEND` | 選填         | `"true"` 即使無異動也寄信。`main.py` 預設 `"false"`，workflow 預設 `"true"`（但 monitor.yml 內另有 `export FORCE_SEND=true` 強制覆寫，詳見「行為細節」）。 |
| `GITHUB_TOKEN` | 自動       | 由 Actions 自動注入；`auto_issue.py` 透過此 token 用 `gh` CLI 開 ISSUE。本機測試可改用 `HEALER_TOKEN`。 |
| `TARGET_REPO` | 選填       | `auto_issue.py` 使用的 `owner/repo`（預設 `gcl858/OpenDataMonitor`），workflow 自動設成 `github.repository`。 |
| `AUTO_HEAL_LABEL` | 選填   | 自訂 auto-heal ISSUE label 名稱，預設 `auto-heal`。 |

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
列序的雜訊不會誤觸變更通知。`CHANGED` 時還會逐列 log 新增的 row。

## 行為細節

### 排程實際為每日一次

`monitor.yml` 內的 cron 是 `15 0 * * *`（每日 UTC 00:15），
不是 README 過去寫的「每 6 小時」。如需更密集排程，請同步更新 workflow 與文件。

### `FORCE_SEND` 在 workflow 內被強制覆寫

`monitor.yml` 的 `Run Monitor` 步驟含有：

```yaml
run: |
  export FORCE_SEND=true
  RESULT=$(python ./scripts/main.py)
```

這行 `export FORCE_SEND=true` 會覆蓋掉來自 `workflow_dispatch.inputs.force_send` 的值，
因此 `force_send` 輸入參數實際上是**無作用**的，workflow 永遠會在
`NO_CHANGE` 時也寄出「無異動」通知。如要恢復 `force_send` 輸入的控制權，
請把這行 `export` 拿掉。

### `email_to` 多收件人

`EMAIL_TO` 以逗號區隔多個收件人；`send_email.py` 會 split + strip 後逐一帶入 SMTP，
避免字串中含逗號導致 Gmail 視為單一無效地址。

## 手動觸發

### GitHub UI

```
Actions → OpenData Monitor → Run workflow
```

| Input        | 預設     | 說明                                         | 備註 |
| ------------ | -------- | -------------------------------------------- | ---- |
| `force_send` | `true`   | 強制寄送 Email（即使無異動）                 | ⚠ workflow 另有 `export FORCE_SEND=true` 覆寫，此輸入目前不生效 |
| `custom_url` | `""`     | 臨時替換下載來源 URL                         | —    |

> `force_send` 在 `main.py` 內的預設是 `"false"`，但 workflow YAML 的
> `workflow_dispatch` 預設是 `"true"`，且 `Run Monitor` 步驟還有
> `export FORCE_SEND=true` 強制覆寫；目前後者勝出。如要讓 `force_send`
> 輸入真的可控制，請拿掉該 `export` 行。

### GitHub CLI

```bash
# 一般觸發
gh workflow run monitor.yml

# 強制發信（注意：仍會被 workflow 內的 export 覆寫為 true）
gh workflow run monitor.yml -f force_send=true

# 使用自訂 URL
gh workflow run monitor.yml -f custom_url=https://example.gov/data.csv
```

## 年度清單 workflow

```
Actions → Year List CSV → Run workflow
```

僅 `workflow_dispatch` 觸發（無排程），用於列出
[dataset/35321](https://data.gov.tw/dataset/35321) 頁面上所有年度的全國路名 CSV
下載連結。執行時不需要 Secrets，僅相依 Python 標準庫。

## 自動修復機制 (auto-heal)

當 monitor 抓取失敗（`download` / `compare` / `parse_road_csv` 任一步拋例外，
或在最外層遇到未預期例外）時，會呼叫 `scripts/auto_issue.py` 自動建立帶
`auto-heal` label 的 GitHub ISSUE。

### 行為

- 用 `gh` CLI 建立 ISSUE，body 包含 traceback + 最近 log + 修復建議
- 同標題的 ISSUE 已存在時只補 comment，不重複開
- `_ensure_label()` 先 idempotent 建立 `auto-heal` label；
  若 token 缺 `issues: write` scope，降級為只建 issue 不掛 label，流程不中斷
- 任何 gh 失敗一律降級為 log，絕不影響 monitor 主流程

### 需要的 Workflow 改動

| 項目 | 值 |
| --- | --- |
| Permissions（`monitor.yml` `jobs.monitor.permissions`） | 新增 `issues: write` |
| Env（`Run Monitor` step） | 新增 `GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}` + `TARGET_REPO: ${{ github.repository }}` |

> 不需要任何新 Secret：`GITHUB_TOKEN` 由 GitHub Actions 自動注入，
> `TARGET_REPO` 由 workflow expression 帶入。

### 觸發點（`scripts/main.py`）

1. `year_error` 區塊 catch → `_record_failure("YearParseError", e)`
2. `if __name__ == "__main__"` 頂層 except → `_record_failure(type(e).__name__, e)`

ISSUE 修復端是另一個 repo `OpenDataMonitor-Healer`，由 oh-my-pi AI Agent
接手開 PR，merge 仍由人工 review。

## 安全注意事項

- 不要將 `.env`、`*.key`、`secrets.json` commit 進 repository
- 不要在 workflow 中 `echo` secrets
- 僅使用已釘定主要版本的 Actions（如 `@v4`、`@v5`），避免 supply-chain attack
- Actions 權限需 `contents: write`(commit) + `issues: write`(auto-heal 自動建 ISSUE)
