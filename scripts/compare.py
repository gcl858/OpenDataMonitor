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
