import os
import sys
import re
from logger_util import logger
from download import run_download
from compare import run_compare
from compare_years import run_compare_years
from send_email import run_send_email
from parse_road_csv import fetch_html, build_rows

URL = "https://data.gov.tw/dataset/35321"
DATASET_ID = "E2EDC47D-2D3F-4EB1-878A-4DEB6160FD4C"
UUID_RE = re.compile(r"[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}")
NAME_RE = re.compile(r'"(\d{3})全國路名資料"')
BASE = f"https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/{DATASET_ID}/resource/"


def main() -> None:

    # 下載最新資料
    run_download()

    # 比對 CSV 差異
    result, new_rows = run_compare()

    logger.info(f"compare result={result}")

    # 解析年度列表並比對差異
    html_text = fetch_html(URL)
    year_rows = build_rows(html_text)
    year_status, _ = run_compare_years(year_rows)
    year_changed = year_status == "YEAR_CHANGED"

    logger.info(f"year status={year_status}")

    # 若 year 變動但 CSV 沒變,合併為 CHANGED 以觸發 workflow commit
    if year_changed and result == "NO_CHANGE":
        result = "CHANGED"
        logger.info("promote result to CHANGED due to year_rows change")

    # 輸出結果供 GitHub Actions GITHUB_OUTPUT 捕捉
    print(result)

    # 判斷是否寄信
    force_send = os.environ.get("FORCE_SEND", "false").lower() == "true"

    should_send = result == "CHANGED" or force_send

    if should_send:
        run_send_email(
            new_rows=new_rows,
            year_rows=year_rows,
            year_changed=year_changed,
        )
    else:
        logger.info("skip send email")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.exception(f"monitor failed: {e}")
        sys.exit(1)
