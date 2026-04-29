# -*- coding: utf-8 -*-
"""
ICLR 2026 论文 venue 信息补丁脚本
=================================

从 OpenReview 重新拉一次 venue / venueid 字段（不调 LLM，纯数据补充），
判断每篇论文是 Oral / Spotlight / Poster，写回到本地 JSON 文件里：
  - ICLR2026_all_papers.json
  - ICLR2026_all_papers_CN.json

只读不写网络一次，处理 5352 篇约 1-3 分钟。安全可重复运行。
"""

import json
import os
from pathlib import Path

# .env 不一定要用，但保持一致
def _load_dotenv():
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ[k.strip()] = v.strip().strip("'\"")

_load_dotenv()

VENUE_ID = "ICLR.cc/2026/Conference"
OPENREVIEW_API = "https://api2.openreview.net"

JSON_FILES = [
    "ICLR2026_all_papers.json",
    "ICLR2026_all_papers_CN.json",
]


def _v(field):
    if isinstance(field, dict) and "value" in field:
        return field["value"]
    return field


def determine_tier(venue, venueid):
    """根据 venue 和 venueid 字段判断论文档次。
    OpenReview 的常见格式：
      venue:    "ICLR 2026 oral" / "ICLR 2026 spotlight" / "ICLR 2026 poster"
      venueid:  "ICLR.cc/2026/Conference"  或  "ICLR.cc/2026/Conference/Oral"
    """
    v = (venue or "").lower()
    vid = (venueid or "")
    if "oral" in v or "/oral" in vid.lower():
        return "Oral"
    if "spotlight" in v or "/spotlight" in vid.lower():
        return "Spotlight"
    return "Poster"


def fetch_venue_map():
    try:
        import openreview
    except ImportError:
        raise SystemExit("❌ 未安装 openreview-py：pip install openreview-py")

    print(f"[1/2] 从 OpenReview 拉取 venue 信息...")
    client = openreview.api.OpenReviewClient(baseurl=OPENREVIEW_API)
    notes = client.get_all_notes(content={"venueid": VENUE_ID})
    print(f"  共拉到 {len(notes)} 篇接收论文。")

    venue_map = {}
    for n in notes:
        content = n.content or {}
        venue = (_v(content.get("venue", "")) or "").strip()
        venueid = (_v(content.get("venueid", "")) or "").strip()
        venue_map[n.id] = {
            "venue": venue,
            "venueid": venueid,
            "tier": determine_tier(venue, venueid),
        }
    return venue_map


def main():
    vmap = fetch_venue_map()

    # 统计档次分布
    from collections import Counter
    tiers = Counter(info["tier"] for info in vmap.values())
    print("\n  档次分布:")
    for t in ["Oral", "Spotlight", "Poster"]:
        print(f"    {t}: {tiers.get(t, 0)}")

    # 抽样几个看 venue 字段长啥样
    print("\n  几个 venue 字段样本：")
    seen = {"Oral": False, "Spotlight": False, "Poster": False}
    for pid, info in vmap.items():
        if not seen[info["tier"]]:
            print(f"    [{info['tier']}]  venue={info['venue']!r}, venueid={info['venueid']!r}")
            seen[info["tier"]] = True
        if all(seen.values()):
            break

    # 把 tier / venue 写进所有 JSON 文件
    print(f"\n[2/2] 把 venue 信息合并到本地 JSON 文件...")
    for fp in JSON_FILES:
        path = Path(fp)
        if not path.exists():
            print(f"  跳过 {fp}（不存在）")
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        n_updated = 0
        for p in data.get("papers", []):
            info = vmap.get(p["id"])
            if info:
                p["venue"] = info["venue"]
                p["tier"] = info["tier"]
                n_updated += 1
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  ✅ {fp}: 更新了 {n_updated}/{len(data.get('papers', []))} 篇")

    print("\n✅ 完成。下一步：python3 build_html_full.py 重新渲染网页。")


if __name__ == "__main__":
    main()
