"""
解析 data.gov.tw 「全國路名資料」(dataset/35321) 頁面，
抽出各年度的全國路名 CSV 下載連結，並依年度由新到舊排序輸出。

資料來源結構（從實際抓回的 HTML 觀察得到）：
  - <head> 內有一段 JSON-LD (schema.org/Dataset.distribution)，
    列出 11 個 resource 的 contentUrl（10 個 opdadm.moi.gov.tw 的 CSV
    + 1 個外部 ris.gov.tw 的 JSON）。
  - 頁面 Vue 渲染時，每個 resource 都是一個 <li class="resource-item">，
    裡面同時含 <a href=".../resource/<UUID>/download"> 與
    <span>XXX全國路名資料</span>。把兩者放在同一個 li 區塊內配對，
    比「±N 字元內找最近字串」穩健很多。
  - 舊版頁面會把 resource name 序列化成 JSON 字串（雙引號包裹），
    新版改成直接 DOM 文字節點渲染，導致原本 r'"(\d{3})全國路名資料"'
    全部 miss → name 落入 default → int("(未知") 爆炸。
    解法：放棄字串層比對，改從 DOM 結構解析。

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
ITEM_RE = re.compile(r'<li class="resource-item"[^>]*>(.*?)</li>', re.S)
NAME_IN_ITEM_RE = re.compile(r'>(\d{3})全國路名資料<')
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
    抽出 distribution[*].contentUrl 清單（依頁面顯示順序）。
    """
    m = re.search(
        r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
        html_text,
        re.S,
    )
    if not m:
        raise RuntimeError("找不到 JSON-LD 區塊")
    payload = json.loads(unescape(m.group(1)))
    if isinstance(payload, list):
        dataset = next((x for x in payload if x.get("@type") == "Dataset"), payload[0])
    else:
        dataset = payload
    urls = [d["contentUrl"] for d in dataset.get("distribution", [])]
    return urls


def parse_year_map(html_text: str) -> dict:
    """
    把每個 resource UUID 對到它的民國年度。

    做法：以 <li class="resource-item"> 為單位切塊，每個 li 同時含
    UUID（href 內）與 name（<span>XXX全國路名資料</span>）。
    比「±N 字元內找最近字串」穩，因為 DOM 結構上 UUID 跟 name
    物理上就在同一個 li 內。
    舊版頁面用 JSON 序列化的雙引號字串比對，新版改成直接 DOM 文字
    節點，所以這裡也跟著換。
    """
    pairs = {}
    for m in ITEM_RE.finditer(html_text):
        block = m.group(1)
        u = re.search(r"/resource/(" + UUID_RE.pattern + r")/download", block)
        n = NAME_IN_ITEM_RE.search(block)
        if u and n:
            pairs[u.group(1)] = f"{n.group(1)}全國路名資料"
    return pairs


def build_rows(html_text: str) -> List[Tuple[int, int, str, str]]:
    """
    組合 (西元年, 民國年, 顯示檔名, 下載URL) 清單，依西元年新→舊排序。
    distribution 裡偶爾會夾帶非 opdadm 的外部連結（如 ris.gov.tw），
    沒有 UUID 的直接略過；UUID 對不到 name 的也略過。
    """
    urls = parse_distribution(html_text)
    year_map = parse_year_map(html_text)

    rows = []
    for url in urls:
        m = re.search(r"/resource/(" + UUID_RE.pattern + r")/download", url)
        if not m:
            # 外部連結（如 ris.gov.tw），沒有 UUID → 略過
            continue
        u = m.group(1)
        name = year_map.get(u)
        if name is None:
            # UUID 沒對到年份（版型改變），略過而非讓程式爆炸
            continue
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
    # 只取前 3 筆，避免輸出過長
    for ad, roc, name, url in rows[:3]:
        print(f"{ad:>6}  {roc:>4}  {name:<14}  {url}")
    print("=" * 96)
    print(f"共 {len(rows)} 個檔案", flush=True)


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else URL
    print(f"[i] 來源: {src}")
    html_text = fetch_html(src)
    rows = build_rows(html_text)
    print_table(rows)
    sys.stdout.flush()


if __name__ == "__main__":
    main()