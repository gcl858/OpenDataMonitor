"""
比對 parse_road_csv.build_rows() 產出的前 2 筆年度資料是否變動。

機制模仿 scripts/compare.py：將 top-2 (name, url) 清單 JSON 序列化後
計算 MD5，與 data/year_rows.hash 內的舊 hash 比對，差異時覆寫。

回傳值（與 compare.run_compare 對齊的 tuple 形狀）：
  - ("YEAR_FIRST_RUN", year_rows[:2])：首次執行，無前次資料
  - ("YEAR_CHANGED",   year_rows[:2])：與前次不同
  - ("YEAR_NO_CHANGE", None)         ：與前次相同
"""

import hashlib
import json
from pathlib import Path
from typing import List, Optional, Tuple

from logger_util import logger




def _normalize_top2(year_rows: List[Tuple[int, int, str, str]]) -> str:
    """取 year_rows 前 2 筆的 (name, url) 序列化為 JSON 後計算 MD5 hex。"""
    payload = [
        {"name": row[2], "url": row[3]}
        for row in year_rows[:2]
    ]
    serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(serialized.encode("utf-8")).hexdigest()


def run_compare_years(
    year_rows: List[Tuple[int, int, str, str]],
) -> tuple[str, Optional[List[Tuple[int, int, str, str]]]]:
    yearhash_file = Path("data/year_rows.hash")
    try:
        logger.info("start compare years")

        current_hash = _normalize_top2(year_rows)
        logger.info(f"current year hash={current_hash}")

        if not yearhash_file.exists():
            logger.info("first run (year_rows)")
            yearhash_file.parent.mkdir(parents=True, exist_ok=True)
            yearhash_file.write_text(current_hash, encoding="utf-8")
            return "YEAR_FIRST_RUN", year_rows[:2]

        old_hash = yearhash_file.read_text(encoding="utf-8").strip()
        logger.info(f"old year hash={old_hash}")

        if old_hash != current_hash:
            logger.info("year_rows changed")
            yearhash_file.write_text(current_hash, encoding="utf-8")
            return "YEAR_CHANGED", year_rows[:2]

        logger.info("year_rows no change")
        return "YEAR_NO_CHANGE", None

    except Exception as e:
        logger.exception(f"compare years failed: {e}")
        raise


if __name__ == "__main__":
    from parse_road_csv import build_rows, fetch_html, URL

    html_text = fetch_html(URL)
    rows = build_rows(html_text)
    status, prev = run_compare_years(rows)
    print(status)
    if prev:
        for r in prev:
            print(r)
