"""
解析 data.gov.tw 「全國路名資料」(dataset/35321) 頁面，
抽出各年度的全國路名 CSV 下載連結，並依年度由新到舊排序輸出。

資料來源結構（從實際抓回的 HTML 觀察得到）：
  - <head> 內有一段 JSON-LD (schema.org/Dataset.distribution)，
    列出 10 個 CSV 的 contentUrl，順序與頁面「檔案下載」區塊一致。
  - 頁面 Vue 渲染資料中，每個 resource 都帶一個 "XXX全國路名資料" 的
    name 標籤，前 3 碼就是民國年度。
  - dataset 識別碼 E2EDC47D-... 是固定的，resource UUID 才是各年度檔案。

執行：
  python3 parse_road_csv.py            # 直接抓網路頁面解析
  python3 parse_road_csv.py page.html  # 解析已下載的本地 HTML
"""

import json
import re
import sys
import urllib.request
from html import unescape
from typing import List, Tuple

URL = "https://data.gov.tw/dataset/35321"
DATASET_ID = "E2EDC47D-2D3F-4EB1-878A-4DEB6160FD4C"
UUID_RE = re.compile(r"[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}")
NAME_RE = re.compile(r'"(\d{3})全國路名資料"')
BASE = f"https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/{DATASET_ID}/resource/"


def fetch_html(source: str) -> str:
    """從 URL 或本地路徑取得 HTML 內容。"""
    if source.startswith("http://") or source.startswith("https://"):
        req = urllib.request.Request(
            source,
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"},
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8", errors="replace")
    with open(source, "r", encoding="utf-8") as f:
        return f.read()


def parse_distribution(html_text: str) -> List[str]:
    """
    從 <script type="application/ld+json"> 內的 schema.org/Dataset JSON
    抽出 distribution[*].contentUrl 清單。
    """
    m = re.search(
        r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
        html_text,
        re.S,
    )
    if not m:
        raise RuntimeError("找不到 JSON-LD 區塊")
    payload = json.loads(unescape(m.group(1)))
    # 取第一個 Dataset 物件
    if isinstance(payload, list):
        dataset = next((x for x in payload if x.get("@type") == "Dataset"), payload[0])
    else:
        dataset = payload
    urls = [d["contentUrl"] for d in dataset.get("distribution", [])]
    return urls


def parse_year_map(html_text: str) -> dict:
    """
    把每個 resource UUID 對到它檔名上的民國年度。
    做法：在每個 `/resource/<UUID>/download` 出現處的 ±400 字元內，
    找最近的「XXX全國路名資料」字樣，XXX 即為民國年度。
    （Vue 把每個 resource 物件序列化在同一段，UUID 與 name 距離很近。）
    """
    pairs = {}
    for m in re.finditer(r"/resource/(" + UUID_RE.pattern + r")/download", html_text):
        u = m.group(1)
        near = html_text[max(0, m.start() - 400): m.end() + 400]
        nm = NAME_RE.search(near)
        if nm:
            pairs[u] = f"{nm.group(1)}全國路名資料"
    return pairs


def build_rows(html_text: str) -> List[Tuple[int, int, str, str]]:
    """
    組合 (西元年, 民國年, 顯示檔名, 下載URL) 清單，依西元年新→舊排序。
    """
    urls = parse_distribution(html_text)
    year_map = parse_year_map(html_text)

    rows = []
    for url in urls:
        m = re.search(r"/resource/(" + UUID_RE.pattern + r")/download", url)
        if not m:
            continue
        u = m.group(1)
        name = year_map.get(u, f"(未知年度){u[:8]}")
        roc = int(name[:3])
        ad = roc + 1911
        rows.append((ad, roc, name, url))
    rows.sort(key=lambda x: -x[0])
    return rows


def print_table(rows: List[Tuple[int, int, str, str]]) -> None:
    print("全國路名資料 — CSV 下載連結（依年度新→舊）")
    print("=" * 96)
    header = f"{'西元':>6}  {'民國':>4}  {'檔名':<14}  下載連結"
    print(header)
    print("-" * 96)
    for ad, roc, name, url in rows:
        print(f"{ad:>6}  {roc:>4}  {name:<14}  {url}")
    print("=" * 96)
    print(f"共 {len(rows)} 個檔案", flush=True)


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else URL
    print(f"[i] 來源: {src}")
    html_text = fetch_html(src)
    rows = build_rows(html_text)
    print_table(rows)


if __name__ == "__main__":
    main()
