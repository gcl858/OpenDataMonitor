import os
import sys
import re
import traceback
from datetime import datetime
from pathlib import Path

from logger_util import logger
from download import run_download
from compare import run_compare
from compare_years import run_compare_years
from send_email import run_send_email
from parse_road_csv import fetch_html, build_rows

try:
    from auto_issue import open_issue  # type: ignore
except ImportError:                          # 本地開發沒有 auto_issue 時不擋
    open_issue = None                        # type: ignore

# 對應 logger_util.log_file 的路徑規律 (logs/history/<UTC-date>.log)
TODAY_LOG = Path(f"logs/history/{datetime.utcnow():%Y-%m-%d}.log")


def _record_failure(error_type: str, exc: BaseException) -> None:
    """把失敗打包交給 auto_issue.open_issue 建 ISSUE。錯誤一律降級為 log。"""
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    log_excerpt = (
        TODAY_LOG.read_text(encoding="utf-8", errors="replace")
        if TODAY_LOG.exists() else ""
    )
    if open_issue is not None:
        try:
            open_issue(error_type, str(exc), tb, log_excerpt)
        except Exception as ie:               # noqa: BLE001
            logger.error("auto_issue 自己也炸了: %s", ie)
    else:
        logger.warning("auto_issue 模組沒載入,跳過 ISSUE 通知")


URL = "https://data.gov.tw/dataset/35321"
DATASET_ID = "E2EDC47D-2D3F-4EB1-878A-4DEB6160FD4C"
UUID_RE = re.compile(r"[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}")
NAME_RE = re.compile(r'"(\d{3})全國路名資料"')
BASE = f"https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/{DATASET_ID}/resource/"


def main() -> None:

    # 解析年度列表並比對差異
    # 任何例外都要攔下,容存入 year_error 供 email 內文使用,避免主流程中斷
    year_rows: list | None = None
    year_changed = False
    year_error: str | None = None
    year_status = "YEAR_SKIPPED"
    try:
        html_text = fetch_html(URL)
        year_rows = build_rows(html_text)
        year_status, _ = run_compare_years(year_rows)
        year_changed = year_status == "YEAR_CHANGED"
        logger.info(f"year status={year_status}")
    except Exception as e:
        year_error = traceback.format_exc()
        logger.exception(f"year parse/compare failed: {e}")
        _record_failure("YearParseError", e)

    # 取出最新年度的下載網址,未來可自動帶入 run_download 以免手動更新
    # build_rows() 回傳 List[Tuple[int, int, str, str]] = (西元年, 民國年, 檔名, URL)
    last_year_csv_url = year_rows[0][3] if year_rows else None
    logger.info(f"last year csv url={last_year_csv_url}")

    # 下載最新資料
    run_download()
    # 比對 CSV 差異
    result, new_rows = run_compare()
    logger.info(f"compare result={result}")


    # 若 year 變動但 CSV 沒變,合併為 CHANGED 以觸發 workflow commit
    if year_changed or result == "CHANGED":
        result = "CHANGED"
        logger.info("promote result to CHANGED due to year_rows change")
    elif year_status=="YEAR_FIRST_RUN" or result == "FIRST_RUN":
        result = "FIRST_RUN"
        logger.info("first run detected")        
    
    # 輸出結果供 GitHub Actions GITHUB_OUTPUT 捕捉
    print(result)

    # 判斷是否寄信
    force_send = os.environ.get("FORCE_SEND", "false").lower() == "true"

    should_send = result == "CHANGED" or force_send or year_error is not None
    logger.info(f"should_send={should_send} (result={result}, force_send={force_send}, year_error={year_error is not None})")

    if should_send:
        run_send_email(
            new_rows=new_rows,
            year_rows=year_rows,
            year_changed=year_changed,
            year_error=year_error,
        )
    else:
        logger.info("skip send email")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.exception(f"monitor failed: {e}")
        _record_failure(type(e).__name__, e)
        sys.exit(1)
