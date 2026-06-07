import os
import requests
from pathlib import Path

from logger_util import logger

# 114全國路名資料
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

        logger.info(
            f"download completed size={len(response.content)}"
        )

    except Exception as e:

        logger.exception(f"download failed: {e}")

        raise


if __name__ == "__main__":
    run_download()
