import hashlib
import shutil
from pathlib import Path
from typing import Optional

import pandas as pd

from logger_util import logger

latest_file = Path("data/latest.csv")

hash_file = Path("data/latest.hash")

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
