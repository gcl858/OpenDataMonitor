# OpenData Monitor

政府 OpenData 自動監控系統，使用 GitHub Actions + Python + Gmail SMTP。

## 功能

- 每 6 小時自動下載 OpenData（114 全國路名資料）
- MD5 Hash 比對，偵測資料異動
- 資料有異動時自動 Git commit & push
- Gmail Email 通知
- 支援手動觸發與臨時 URL 測試

## 目錄結構

```
.github/workflows/monitor.yml   # GitHub Actions workflow
scripts/
  logger_util.py                # 共用 logger
  download.py                   # 下載 OpenData
  compare.py                    # MD5 比對
  send_email.py                 # Gmail 通知
data/
  latest.csv                    # 最新資料（由 Git 保存歷史）
  latest.hash                   # 上次 hash（自動產生）
logs/history/                   # 每日執行 log
requirements.txt
```

## 環境需求

```bash
pip install -r requirements.txt
```

## GitHub Secrets 設定

`Settings → Secrets and variables → Actions` 新增以下三個 Secret：

| Secret       | 說明                        |
| ------------ | --------------------------- |
| `EMAIL_USER` | Gmail 帳號（xxx@gmail.com） |
| `EMAIL_PASS` | Gmail App Password（16碼）  |
| `EMAIL_TO`   | 收件人 Email                |

### 取得 Gmail App Password

1. Google Account → Security → 2-Step Verification（啟用）
2. Google Account → Security → App Passwords
3. 建立名稱：`Mail / GitHub Actions`
4. 取得 16 碼密碼，填入 `EMAIL_PASS`

## 手動觸發

### GitHub UI

```
Actions → OpenData Monitor → Run workflow
```

| Input        | 說明                   |
| ------------ | ---------------------- |
| `force_send` | `true` 強制發送 Email  |
| `custom_url` | 臨時替換下載來源 URL   |

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
- 僅使用已釘定版本的 Actions（如 `@v4`），避免 supply-chain attack
