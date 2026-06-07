import os
import sys

from logger_util import logger
from download import run_download
from compare import run_compare
from send_email import run_send_email


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

    if should_send:
        run_send_email(new_rows=new_rows)
    else:
        logger.info("skip send email")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.exception(f"monitor failed: {e}")
        sys.exit(1)
