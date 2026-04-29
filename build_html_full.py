# -*- coding: utf-8 -*-
"""
ICLR 2026 全量论文 · 两级目录静态网页渲染
=========================================
输入：ICLR2026_all_papers_CN.json（5352 篇 + 中文六维度分析）
输出：index.html（直接覆盖）

侧边栏：大类（ICLR primary_area）/ 小类（LLM 标）双层折叠树
主体：嵌套 section + 论文卡
保留：搜索 / 六维度展示 / 折叠完整摘要 / GoatCounter 访问统计
"""

import json
from collections import Counter, defaultdict
from html import escape
from pathlib import Path
from urllib.parse import quote

INPUT_JSON = "ICLR2026_all_papers.json"             # 主数据源：全 5352 篇
CN_OVERLAY_JSON = "ICLR2026_all_papers_CN.json"     # 可选：中文分析 overlay（部分翻译完也能渲染）
OUTPUT_HTML = "index.html"

# 6 个分析维度（与 translate_all_papers.py 输出对齐）
DIM_LABELS = [
    ("研究动机",     "🎯 研究动机"),
    ("解决问题",     "❓ 解决问题"),
    ("现象分析",     "🔍 现象分析"),
    ("主要方法",     "🛠️ 主要方法"),
    ("数据集与实验", "📊 数据与实验"),
    ("主要贡献",     "⭐ 主要贡献"),
]

# 兜底翻译（个别 primary_area 漏了中文）
PRIMARY_AREA_FALLBACK_ZH = {
    "learning on time series and dynamical systems": "时间序列与动力系统",
    "learning theory": "学习理论",
    "learning on graphs and other geometries & topologies": "图与几何拓扑学习",
    "causal reasoning": "因果推理",
}

def _norm_primary(p):
    p = (p or "").strip()
    if not p:
        return "(未填)"
    return PRIMARY_AREA_FALLBACK_ZH.get(p, p)


CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;background:#f6f8fa;color:#24292e;line-height:1.7}
.container{display:flex;min-height:100vh}
.sidebar{width:320px;background:#fff;border-right:1px solid #e1e4e8;padding:24px 18px;position:sticky;top:0;height:100vh;overflow-y:auto}
.sidebar h1{font-size:18px;margin-bottom:6px;color:#0366d6;line-height:1.3;font-weight:700}
.sidebar .sub{font-size:12px;color:#6a737d;margin-bottom:16px}
.sidebar input[type=search]{width:100%;padding:9px 12px;border:1px solid #d1d5da;border-radius:6px;margin-bottom:14px;font-size:13px;outline:none}
.sidebar input[type=search]:focus{border-color:#0366d6;box-shadow:0 0 0 2px rgba(3,102,214,.2)}
.stat-grid{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:16px}
.stat-box{background:#f6f8fa;padding:8px 10px;border-radius:6px;font-size:11px;color:#586069}
.stat-box b{color:#0366d6;font-size:14px;display:block}

/* 两级树状导航 */
.nav-tree{font-size:13px}
.nav-pri{margin-bottom:4px;border-radius:5px;overflow:hidden}
.nav-pri-head{display:flex;align-items:center;cursor:pointer;padding:7px 10px;background:#f6f8fa;border-radius:5px;font-weight:600;color:#24292e;user-select:none;transition:background .15s}
.nav-pri-head:hover{background:#e7f3ff}
.nav-pri-head .arrow{margin-right:6px;font-size:10px;color:#959da5;transition:transform .2s}
.nav-pri.expanded > .nav-pri-head .arrow{transform:rotate(90deg)}
.nav-pri-head .name{flex:1}
.nav-pri-head .count{color:#6a737d;font-size:11px;background:#eaecef;padding:2px 8px;border-radius:10px;font-weight:500}
.nav-sub-list{display:none;padding:4px 0 6px 24px}
.nav-pri.expanded > .nav-sub-list{display:block}
.nav-sub-list a{display:flex;align-items:center;padding:5px 8px;color:#586069;text-decoration:none;border-radius:4px;font-size:12.5px;margin-bottom:1px;transition:background .15s}
.nav-sub-list a:hover{background:#f1f4f7;color:#0366d6}
.nav-sub-list a .name{flex:1}
.nav-sub-list a .count{color:#959da5;font-size:11px;margin-left:6px}

.main{flex:1;padding:32px 44px;max-width:calc(100% - 320px)}
.main-header{margin-bottom:32px;padding-bottom:18px;border-bottom:1px solid #e1e4e8}
.main-header h1{font-size:28px;margin-bottom:10px}
.main-header p{color:#586069;font-size:14px}

h2.pri-title{font-size:24px;color:#0366d6;border-bottom:2px solid #0366d6;padding-bottom:8px;margin:40px 0 12px;scroll-margin-top:20px}
h2.pri-title small{font-size:13px;color:#6a737d;font-weight:400;margin-left:8px}
h3.sub-title{font-size:18px;color:#24292e;border-left:4px solid #0366d6;padding:4px 12px;margin:24px 0 14px;scroll-margin-top:20px;background:#f6f8fa;border-radius:0 4px 4px 0}
h3.sub-title small{font-size:12px;color:#6a737d;font-weight:400;margin-left:8px}

.paper{background:#fff;border:1px solid #e1e4e8;border-radius:8px;padding:18px 22px;margin-bottom:14px;box-shadow:0 1px 2px rgba(0,0,0,.04);transition:box-shadow .15s;position:relative}
.paper:hover{box-shadow:0 2px 8px rgba(0,0,0,.06)}
.paper.tier-Oral{border-left:4px solid #d4a017;background:linear-gradient(to right, #fffaeb 0, #fff 80px)}
.paper.tier-Spotlight{border-left:4px solid #5b8def}
.tier-badge{display:inline-block;font-weight:700;font-size:11px;padding:2px 9px;border-radius:10px;margin-right:6px;letter-spacing:.3px;vertical-align:middle}
.tier-badge.Oral{background:#fff4d4;color:#8a6500;border:1px solid #d4a017}
.tier-badge.Spotlight{background:#e7f0ff;color:#1f4dad;border:1px solid #5b8def}

/* 顶部档次摘要 */
.tier-summary{margin:18px 0;display:flex;gap:8px;flex-wrap:wrap}
.tier-chip{display:inline-flex;align-items:center;padding:5px 12px;border-radius:14px;font-size:12px;font-weight:600;cursor:pointer;user-select:none;border:1px solid transparent;transition:all .15s}
.tier-chip.all{background:#eaecef;color:#24292e}
.tier-chip.all.active{background:#0366d6;color:#fff}
.tier-chip.Oral{background:#fff4d4;color:#8a6500;border-color:#d4a017}
.tier-chip.Oral.active{background:#d4a017;color:#fff}
.tier-chip.Spotlight{background:#e7f0ff;color:#1f4dad;border-color:#5b8def}
.tier-chip.Spotlight.active{background:#5b8def;color:#fff}
.tier-chip:hover{transform:translateY(-1px)}
.paper-title{font-size:16px;font-weight:600;color:#24292e;margin-bottom:8px;line-height:1.45}
.paper-title a{color:inherit;text-decoration:none}
.paper-title a:hover{color:#0366d6;text-decoration:underline}
.paper-meta{font-size:12px;color:#586069;margin-bottom:10px}
.paper-meta .badge{display:inline-block;background:#e7f3ff;color:#0366d6;padding:2px 8px;border-radius:10px;margin-right:5px;font-size:11px;font-weight:500}
.paper-meta .badge.sub{background:#eaecef;color:#24292e}
.paper-meta .kw{color:#6a737d;margin-right:6px}
.paper-tldr{background:#fffbea;border-left:3px solid #f9c513;padding:9px 13px;font-size:13px;color:#735c0f;margin-bottom:11px;border-radius:0 4px 4px 0}
.paper-tldr b{color:#5a4500}
.dim{margin:8px 0;font-size:13.5px;display:flex;gap:10px;align-items:flex-start}
.dim-label{flex-shrink:0;font-weight:600;color:#0366d6;width:96px;font-size:12.5px;padding-top:1px}
.dim-content{flex:1;color:#24292e}
.toggle-abs{font-size:12px;color:#0366d6;cursor:pointer;margin-top:10px;display:inline-block;user-select:none;padding:3px 8px;border-radius:4px}
.toggle-abs:hover{background:#e7f3ff}
.full-abs{display:none;margin-top:10px;padding:11px 14px;background:#f6f8fa;border-radius:5px;font-size:12.5px;color:#444;line-height:1.65;border-left:3px solid #d1d5da}
.paper.expanded .full-abs{display:block}
.paper.expanded .toggle-abs::before{content:"▾ "}
.paper:not(.expanded) .toggle-abs::before{content:"▸ "}
.hidden{display:none !important}
.empty{text-align:center;color:#959da5;padding:40px;font-size:14px}
.no-cn{font-style:italic;color:#959da5}

@media(max-width:900px){
  .container{flex-direction:column}
  .sidebar{width:100%;height:auto;position:relative}
  .main{max-width:100%;padding:20px}
  .dim{flex-direction:column;gap:4px}
  .dim-label{width:auto}
}
"""


JS = """
const search=document.getElementById('search');
const papers=document.querySelectorAll('.paper');
const subSecs=document.querySelectorAll('section.sub-sec');
const priSecs=document.querySelectorAll('section.pri-sec');
const tierChips=document.querySelectorAll('.tier-chip');

let activeTier='__all__';

// 大类折叠/展开
document.querySelectorAll('.nav-pri-head').forEach(h=>{
  h.addEventListener('click', e=>{
    if(e.target.closest('.nav-sub-list')) return;
    h.parentElement.classList.toggle('expanded');
  });
});

function applyFilters(){
  const q=(search.value||'').trim().toLowerCase();
  papers.forEach(p=>{
    const t=p.dataset.search||'';
    const myTier=p.dataset.tier||'Poster';
    const matchSearch=!q || t.includes(q);
    const matchTier=(activeTier==='__all__') || (myTier===activeTier);
    p.classList.toggle('hidden', !(matchSearch && matchTier));
  });
  // 重新计数 + 隐藏空 section
  subSecs.forEach(s=>{
    const visible=s.querySelectorAll('.paper:not(.hidden)').length;
    s.classList.toggle('hidden', visible===0);
    const sublink=document.querySelector('.nav-sub-list a[href="#'+s.id+'"]');
    if(sublink){
      const cnt=sublink.querySelector('.count');
      if(cnt) cnt.textContent='('+visible+')';
      sublink.classList.toggle('hidden', visible===0);
    }
  });
  priSecs.forEach(s=>{
    const visible=s.querySelectorAll('.paper:not(.hidden)').length;
    s.classList.toggle('hidden', visible===0);
    const prinav=document.getElementById('nav-'+s.id);
    if(prinav){
      const cnt=prinav.querySelector('.nav-pri-head .count');
      if(cnt) cnt.textContent=visible;
      prinav.classList.toggle('hidden', visible===0);
      // 在有筛选条件时自动展开有结果的大类
      const filtering = q || activeTier!=='__all__';
      if(filtering && visible>0) prinav.classList.add('expanded');
      if(!filtering) prinav.classList.remove('expanded');
    }
  });
}

search.addEventListener('input', applyFilters);
tierChips.forEach(chip=>{
  chip.addEventListener('click', ()=>{
    activeTier = chip.dataset.tier;
    tierChips.forEach(c => c.classList.toggle('active', c===chip));
    applyFilters();
  });
});
"""


def build():
    data = json.loads(Path(INPUT_JSON).read_text(encoding="utf-8"))
    papers = data["papers"]

    # 叠加中文分析（如果 CN overlay 存在）
    cn_map = {}
    if Path(CN_OVERLAY_JSON).exists():
        cn_data = json.loads(Path(CN_OVERLAY_JSON).read_text(encoding="utf-8"))
        cn_map = {p["id"]: p.get("中文分析") for p in cn_data.get("papers", []) if p.get("中文分析")}
    n_with_cn = 0
    for p in papers:
        if p["id"] in cn_map:
            p["中文分析"] = cn_map[p["id"]]
            n_with_cn += 1

    # 兜底翻译
    for p in papers:
        p["primary_area"] = _norm_primary(p.get("primary_area"))
        p["category"] = (p.get("category") or "(未分类)").strip()

    # 按 primary_area → category 分组
    grouped = defaultdict(lambda: defaultdict(list))
    for p in papers:
        grouped[p["primary_area"]][p["category"]].append(p)

    # 大类排序：按论文数降序
    primary_order = [pa for pa, _ in Counter(p["primary_area"] for p in papers).most_common()]

    total = len(papers)
    n_pri = len(primary_order)
    n_sub_total = sum(len(subs) for subs in grouped.values())
    tier_cnt = Counter(p.get("tier") or "Poster" for p in papers)
    n_oral = tier_cnt.get("Oral", 0)
    n_spotlight = tier_cnt.get("Spotlight", 0)

    # ---- 侧边栏 ----
    nav_html = []
    for pa in primary_order:
        sub_dict = grouped[pa]
        # 小类排序：先按数量降序，"其他"放最后
        subs_sorted = sorted(
            sub_dict.items(),
            key=lambda kv: (kv[0] == "其他" or kv[0].startswith("其他"), -len(kv[1]), kv[0])
        )
        pa_anchor = "pri-" + quote(pa, safe="")
        pa_count = sum(len(v) for v in sub_dict.values())
        sub_links = []
        for sub, items in subs_sorted:
            sub_anchor = "sub-" + quote(pa, safe="") + "-" + quote(sub, safe="")
            sub_links.append(
                f'<a href="#{sub_anchor}"><span class="name">{escape(sub)}</span>'
                f'<span class="count">({len(items)})</span></a>'
            )
        nav_html.append(f"""
<div id="nav-{pa_anchor}" class="nav-pri">
  <div class="nav-pri-head">
    <span class="arrow">▶</span>
    <span class="name">{escape(pa)}</span>
    <span class="count">{pa_count}</span>
  </div>
  <div class="nav-sub-list">{''.join(sub_links)}</div>
</div>""")

    # ---- 正文 ----
    pri_secs_html = []
    for pa in primary_order:
        sub_dict = grouped[pa]
        subs_sorted = sorted(
            sub_dict.items(),
            key=lambda kv: (kv[0] == "其他" or kv[0].startswith("其他"), -len(kv[1]), kv[0])
        )
        pa_anchor = "pri-" + quote(pa, safe="")
        pa_count = sum(len(v) for v in sub_dict.values())

        sub_secs_html = []
        for sub, items in subs_sorted:
            sub_anchor = "sub-" + quote(pa, safe="") + "-" + quote(sub, safe="")
            cards = []
            for p in items:
                title = escape(p["title"])
                url = escape(p.get("url", "#"))
                primary_badge = escape(p.get("primary_area", "") or "")
                sub_badge = escape(p.get("category", "") or "")
                kws = p.get("keywords", []) or []
                kw_html = " ".join(f'<span class="kw">#{escape(k)}</span>' for k in kws)
                tldr = p.get("tldr") or ""
                tldr_html = (
                    f'<div class="paper-tldr"><b>TL;DR：</b>{escape(tldr)}</div>'
                    if tldr else ""
                )
                analysis = p.get("中文分析") or {}
                if analysis:
                    dims_html = []
                    for key, label in DIM_LABELS:
                        val = analysis.get(key, "") or ""
                        dims_html.append(
                            f'<div class="dim"><span class="dim-label">{label}</span>'
                            f'<div class="dim-content">{escape(val)}</div></div>'
                        )
                    dims_block = ''.join(dims_html)
                else:
                    dims_block = '<div class="dim no-cn">（中文六维度分析尚未生成）</div>'

                tier = (p.get("tier") or "Poster").strip()
                tier_badge_html = ""
                if tier == "Oral":
                    tier_badge_html = '<span class="tier-badge Oral">🎤 Oral</span>'
                elif tier == "Spotlight":
                    tier_badge_html = '<span class="tier-badge Spotlight">💡 Spotlight</span>'
                paper_class = f"paper tier-{escape(tier)}"
                search_blob = (
                    p["title"] + " " + " ".join(kws) + " " + (tldr or "") + " "
                    + p.get("primary_area", "") + " " + p.get("category", "") + " " + tier
                ).lower()
                cards.append(f"""
<article class="{paper_class}" data-search="{escape(search_blob)}" data-tier="{escape(tier)}">
  <div class="paper-title">{tier_badge_html}<a href="{url}" target="_blank">{title}</a></div>
  <div class="paper-meta">
    {f'<span class="badge">{primary_badge}</span>' if primary_badge else ''}
    {f'<span class="badge sub">{sub_badge}</span>' if sub_badge else ''}
    {kw_html}
  </div>
  {tldr_html}
  {dims_block}
  <span class="toggle-abs" onclick="this.parentElement.classList.toggle('expanded')">查看完整摘要 (Abstract)</span>
  <div class="full-abs">{escape(p.get('abstract','') or '')}</div>
</article>""")
            sub_secs_html.append(f"""
<section id="{sub_anchor}" class="sub-sec">
  <h3 class="sub-title">{escape(sub)}<small>{len(items)} 篇</small></h3>
  {''.join(cards)}
</section>""")

        pri_secs_html.append(f"""
<section id="{pa_anchor}" class="pri-sec">
  <h2 class="pri-title">{escape(pa)}<small>{pa_count} 篇 · {len(subs_sorted)} 个细分</small></h2>
  {''.join(sub_secs_html)}
</section>""")

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ICLR 2026 论文集 · 中文导读（{total} 篇）</title>
<style>{CSS}</style>
</head>
<body>
<div class="container">
  <aside class="sidebar">
    <h1>📚 ICLR 2026<br>全部论文中文导读</h1>
    <div class="sub">{total} 篇 · {n_pri} 个大类 · {n_sub_total} 个细分</div>
    <input type="search" id="search" placeholder="🔍 搜索标题 / 关键词…">
    <div class="stat-grid">
      <div class="stat-box"><b>{total}</b>论文总数</div>
      <div class="stat-box"><b>{n_pri}</b>大类</div>
    </div>
    <div style="font-size:12px;font-weight:600;color:#586069;margin-bottom:8px">📁 按 ICLR 官方研究方向 → 细分类别浏览</div>
    <div class="nav-tree">{''.join(nav_html)}</div>
    <div style="margin-top:24px;padding-top:16px;border-top:1px solid #eaecef;font-size:11px;color:#959da5;line-height:1.6">
      📊 数据来源：<br>OpenReview ICLR 2026<br>
      （5,352 篇接收论文全部收录）<br><br>
      💡 每篇论文的"六维度"由大语言模型基于 abstract 自动生成，仅供快速浏览，详见原文。<br><br>
      <span id="visit-stats" style="display:none">👁 总访问 <b id="gc-pv" style="color:#0366d6"></b> 次　·　访客 <b id="gc-uv" style="color:#0366d6"></b> 人</span>
    </div>
    <script data-goatcounter="https://jenniferzhao0531.goatcounter.com/count" async src="//gc.zgo.at/count.js"></script>
    <script>
    fetch('https://jenniferzhao0531.goatcounter.com/counter/TOTAL.json')
      .then(r => r.json()).then(d => {{
        document.getElementById('gc-pv').textContent = (d.count || '0').toString().replace(/\\B(?=(\\d{{3}})+(?!\\d))/g, ',');
        document.getElementById('gc-uv').textContent = (d.count_unique || '0').toString().replace(/\\B(?=(\\d{{3}})+(?!\\d))/g, ',');
        document.getElementById('visit-stats').style.display = 'inline';
      }}).catch(()=>{{}});
    </script>
  </aside>
  <main class="main">
    <div class="main-header">
      <h1>ICLR 2026 全部接收论文 · 中文导读</h1>
      <p>从 OpenReview 拉取 ICLR 2026 全部 <b>{total}</b> 篇接收论文，按 ICLR 官方一级研究方向（{n_pri} 个大类）+ LLM 二级细分（{n_sub_total} 个小类）整理。每篇论文给出"研究动机 / 解决问题 / 现象分析 / 主要方法 / 数据集与实验 / 主要贡献"六个维度的中文分析。中文内容由大语言模型基于英文 abstract 自动生成，仅供快速浏览参考，建议结合原文阅读。左侧导航点大类标题展开/收起子项；点击论文标题直达 OpenReview 原文。</p>
      <div class="tier-summary">
        <span class="tier-chip all active" data-tier="__all__">📚 全部 {total} 篇</span>
        {f'<span class="tier-chip Oral" data-tier="Oral">🎤 Oral {n_oral} 篇</span>' if n_oral > 0 else ''}
        {f'<span class="tier-chip Spotlight" data-tier="Spotlight">💡 Spotlight {n_spotlight} 篇</span>' if n_spotlight > 0 else ''}
      </div>
    </div>
    {''.join(pri_secs_html)}
  </main>
</div>
<script>{JS}</script>
</body>
</html>
"""

    Path(OUTPUT_HTML).write_text(html, encoding="utf-8")
    print(f"✅ 已生成 {OUTPUT_HTML}（{total} 篇 · {n_pri} 大类 · {n_sub_total} 细分 · {n_with_cn} 篇带中文分析）")
    if n_with_cn < total:
        print(f"   💡 还有 {total - n_with_cn} 篇没有中文六维度分析，等 translate_all_papers.py 跑完后再重新 build。")


if __name__ == "__main__":
    build()
