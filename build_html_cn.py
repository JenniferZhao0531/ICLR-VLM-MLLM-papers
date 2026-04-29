# -*- coding: utf-8 -*-
"""
将 ICLR2026_VLM_MLLM_papers_CN.json (含 GPT-5 六维度中文分析)
渲染成静态 HTML 页面，复用旧版 ICLR2026_VLM_MLLM_中文版.html 的样式与布局。
"""
import json
from html import escape
from pathlib import Path
from urllib.parse import quote

INPUT_JSON = "ICLR2026_VLM_MLLM_papers_CN.json"
OUTPUT_HTML = "ICLR2026_VLM_MLLM_中文版.html"

# 子领域显示顺序（与旧版一致）
CATEGORY_ORDER = [
    "评测基准与评估",
    "视频理解 VLM",
    "3D 与空间理解",
    "具身智能与 Agent",
    "医学多模态",
    "安全 / 对齐 / 鲁棒性",
    "推理与强化学习",
    "训练 / 微调 / 对齐方法",
    "效率与推理加速",
    "多模态生成",
    "视觉定位与分割",
    "音频-视觉多模态",
    "OCR / 文档 / 图表理解",
    "可解释性与表征分析",
    "数据与预训练",
    "检索与 RAG",
    "架构创新",
    "其他",
]

DIM_LABELS = [
    ("研究动机",     "🎯 研究动机"),
    ("解决问题",     "❓ 解决问题"),
    ("现象分析",     "🔍 现象分析"),
    ("主要方法",     "🛠️ 主要方法"),
    ("数据集与实验", "📊 数据与实验"),
    ("主要贡献",     "⭐ 主要贡献"),
]

# 兜底翻译：数据生成时漏掉的 primary_area 英文项
PRIMARY_AREA_FALLBACK_ZH = {
    "learning on time series and dynamical systems": "时间序列与动力系统学习",
    "learning theory": "学习理论",
    "learning on graphs and other geometries & topologies": "图与几何拓扑学习",
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
.sidebar{width:300px;background:#fff;border-right:1px solid #e1e4e8;padding:24px 20px;position:sticky;top:0;height:100vh;overflow-y:auto}
.sidebar h1{font-size:18px;margin-bottom:6px;color:#0366d6;line-height:1.3;font-weight:700}
.sidebar .sub{font-size:12px;color:#6a737d;margin-bottom:16px}
.sidebar input[type=search]{width:100%;padding:9px 12px;border:1px solid #d1d5da;border-radius:6px;margin-bottom:10px;font-size:13px;outline:none}
.sidebar input[type=search]:focus{border-color:#0366d6;box-shadow:0 0 0 2px rgba(3,102,214,.2)}
.sidebar .filter-label{font-size:11px;color:#586069;margin-bottom:4px;font-weight:600}
.sidebar select{width:100%;padding:8px 10px;border:1px solid #d1d5da;border-radius:6px;margin-bottom:14px;font-size:12.5px;outline:none;background:#fff;color:#24292e;cursor:pointer}
.sidebar select:focus{border-color:#0366d6;box-shadow:0 0 0 2px rgba(3,102,214,.2)}
.filter-active{background:#fff5b1!important;padding:6px 10px;border-radius:5px;font-size:12px;color:#735c0f;margin-bottom:10px;display:none}
.filter-active.show{display:block}
.filter-active a{color:#0366d6;text-decoration:none;margin-left:6px;font-weight:600}
.stat-grid{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:16px}
.stat-box{background:#f6f8fa;padding:8px 10px;border-radius:6px;font-size:11px;color:#586069}
.stat-box b{color:#0366d6;font-size:14px;display:block}
.cat-list a{display:block;padding:7px 10px;color:#24292e;text-decoration:none;border-radius:5px;font-size:13px;margin-bottom:2px;transition:background .15s}
.cat-list a:hover{background:#f1f4f7;color:#0366d6}
.cat-list a .count{float:right;color:#6a737d;font-size:11px;background:#eaecef;padding:2px 8px;border-radius:10px;font-weight:500}
.main{flex:1;padding:32px 44px;max-width:calc(100% - 300px)}
.main-header{margin-bottom:32px;padding-bottom:18px;border-bottom:1px solid #e1e4e8}
.main-header h1{font-size:28px;margin-bottom:10px}
.main-header p{color:#586069;font-size:14px}
h2.cat-title{font-size:22px;color:#0366d6;border-bottom:2px solid #0366d6;padding-bottom:8px;margin:32px 0 18px;scroll-margin-top:20px}
h2.cat-title small{font-size:13px;color:#6a737d;font-weight:400;margin-left:8px}
.paper{background:#fff;border:1px solid #e1e4e8;border-radius:8px;padding:18px 22px;margin-bottom:14px;box-shadow:0 1px 2px rgba(0,0,0,.04);transition:box-shadow .15s}
.paper:hover{box-shadow:0 2px 8px rgba(0,0,0,.06)}
.paper-title{font-size:16px;font-weight:600;color:#24292e;margin-bottom:8px;line-height:1.45}
.paper-title a{color:inherit;text-decoration:none}
.paper-title a:hover{color:#0366d6;text-decoration:underline}
.paper-meta{font-size:12px;color:#586069;margin-bottom:10px}
.paper-meta .badge{display:inline-block;background:#e7f3ff;color:#0366d6;padding:2px 8px;border-radius:10px;margin-right:5px;font-size:11px;font-weight:500;cursor:pointer;border:none;font-family:inherit}
.paper-meta .badge:hover{background:#0366d6;color:#fff}
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
@media(max-width:900px){.container{flex-direction:column}.sidebar{width:100%;height:auto;position:relative}.main{max-width:100%;padding:20px}.dim{flex-direction:column;gap:4px}.dim-label{width:auto}}
"""

JS = """
const search=document.getElementById('search');
const primarySel=document.getElementById('primary-filter');
const filterBar=document.getElementById('filter-active');
const papers=document.querySelectorAll('.paper');
const sections=document.querySelectorAll('section');
const sidebarLinks=document.querySelectorAll('.cat-list a');

function applyFilters(){
  const q=(search.value||'').trim().toLowerCase();
  const pa=primarySel.value;
  papers.forEach(p=>{
    const txt=p.dataset.search||'';
    const myPa=p.dataset.primary||'';
    const matchSearch=!q || txt.includes(q);
    const matchPrimary=(pa==='__all__') || (myPa===pa);
    p.classList.toggle('hidden', !(matchSearch && matchPrimary));
  });
  sections.forEach(s=>{
    const visible=s.querySelectorAll('.paper:not(.hidden)').length;
    s.classList.toggle('hidden', visible===0);
    const link=document.querySelector('.cat-list a[href="#'+s.id+'"]');
    if(link){
      const cnt=link.querySelector('.count');
      if(cnt) cnt.textContent=visible;
      link.classList.toggle('hidden', visible===0);
    }
  });
  // 顶部黄色提示条：当前正在按 Primary Area 筛选
  if(pa==='__all__'){
    filterBar.classList.remove('show');
  }else{
    filterBar.classList.add('show');
    filterBar.querySelector('.fa-name').textContent=primarySel.options[primarySel.selectedIndex].dataset.label;
  }
}
search.addEventListener('input', applyFilters);
primarySel.addEventListener('change', applyFilters);
filterBar.querySelector('a').addEventListener('click', e=>{
  e.preventDefault();
  primarySel.value='__all__';
  applyFilters();
});
// 点击论文卡上的 Primary Area 标签 → 一键筛选
document.querySelectorAll('.paper-meta .badge').forEach(b=>{
  b.addEventListener('click',()=>{
    const v=b.dataset.primary;
    if(!v) return;
    primarySel.value=v;
    applyFilters();
    window.scrollTo({top:0, behavior:'smooth'});
  });
});
"""

def build():
    data = json.loads(Path(INPUT_JSON).read_text(encoding="utf-8"))
    papers = data["papers"]

    # 兜底翻译 + 统一 primary_area
    for p in papers:
        p["primary_area"] = _norm_primary(p.get("primary_area"))

    # 按 category 分组
    by_cat = {c: [] for c in CATEGORY_ORDER}
    for p in papers:
        c = p.get("category", "其他")
        by_cat.setdefault(c, []).append(p)

    # 统计 primary_area，按数量降序排
    from collections import Counter
    primary_counter = Counter(p["primary_area"] for p in papers)
    primary_order = [pa for pa, _ in primary_counter.most_common()]

    total = len(papers)
    n_cats = sum(1 for c in CATEGORY_ORDER if by_cat.get(c))

    # 侧边栏
    sidebar_links = []
    for c in CATEGORY_ORDER:
        items = by_cat.get(c, [])
        if not items:
            continue
        anchor = "cat-" + quote(c)
        sidebar_links.append(
            f'<a href="#{anchor}">{escape(c)}<span class="count">{len(items)}</span></a>'
        )

    # 正文
    sections_html = []
    for c in CATEGORY_ORDER:
        items = by_cat.get(c, [])
        if not items:
            continue
        anchor = "cat-" + quote(c)
        cards = []
        for p in items:
            title = escape(p["title"])
            url = escape(p.get("url", "#"))
            primary = escape(p.get("primary_area", "") or "")
            kws = p.get("keywords", []) or []
            kw_html = " ".join(f'<span class="kw">#{escape(k)}</span>' for k in kws)
            tldr = p.get("tldr") or ""
            tldr_html = (
                f'<div class="paper-tldr"><b>TL;DR：</b>{escape(tldr)}</div>'
                if tldr else ""
            )
            analysis = p.get("中文分析") or {}
            dims_html = []
            for key, label in DIM_LABELS:
                val = analysis.get(key, "") or ""
                dims_html.append(
                    f'<div class="dim"><span class="dim-label">{label}</span>'
                    f'<div class="dim-content">{escape(val)}</div></div>'
                )
            search_blob = (
                p["title"] + " " + " ".join(kws) + " " + (tldr or "")
            ).lower()
            cards.append(f"""
<article class="paper" data-search="{escape(search_blob)}" data-primary="{primary}">
  <div class="paper-title"><a href="{url}" target="_blank">{title}</a></div>
  <div class="paper-meta">
    {f'<button class="badge" data-primary="{primary}" title="点击只看这一类 Primary Area">{primary}</button>' if primary else ''}
    {kw_html}
  </div>
  {tldr_html}
  {''.join(dims_html)}
  <span class="toggle-abs" onclick="this.parentElement.classList.toggle('expanded')">查看完整摘要 (Abstract)</span>
  <div class="full-abs">{escape(p.get('abstract','') or '')}</div>
</article>""")
        sections_html.append(f"""
<section id="{anchor}">
  <h2 class="cat-title">{escape(c)}<small>{len(items)} 篇</small></h2>
  {''.join(cards)}
</section>""")

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ICLR 2026 视觉-语言模型论文集（{total} 篇）</title>
<style>{CSS}</style>
</head>
<body>
<div class="container">
  <aside class="sidebar">
    <h1>📚 ICLR 2026<br>视觉-语言模型论文集</h1>
    <div class="sub">VLM / MLLM 全景整理 · 中文六维度导读</div>
    <input type="search" id="search" placeholder="🔍 搜索标题 / 关键词…">
    <div class="filter-label">🏷️ 按 Primary Area 筛选</div>
    <select id="primary-filter">
      <option value="__all__" data-label="全部">全部（{total}）</option>
      {''.join(f'<option value="{escape(pa)}" data-label="{escape(pa)}">{escape(pa)}（{primary_counter[pa]}）</option>' for pa in primary_order)}
    </select>
    <div id="filter-active" class="filter-active">
      正在筛选 Primary Area：<b class="fa-name"></b><a href="#">[× 清除]</a>
    </div>
    <div class="stat-grid">
      <div class="stat-box"><b>{total}</b>VLM 论文</div>
      <div class="stat-box"><b>{n_cats}</b>子领域</div>
    </div>
    <div style="font-size:12px;font-weight:600;color:#586069;margin-bottom:8px">📁 子领域分类</div>
    <div class="cat-list">{''.join(sidebar_links)}</div>
    <div style="margin-top:24px;padding-top:16px;border-top:1px solid #eaecef;font-size:11px;color:#959da5;line-height:1.6">
      📊 数据来源：<br>OpenReview ICLR 2026<br>
      （从 5,352 篇接收论文中筛选 {total} 篇）<br><br>
      💡 每篇论文的"六维度"由大语言模型基于 abstract 自动生成，仅供快速浏览，详见原文。<br><br>
      <span id="visit-stats" style="display:none">👁 总访问 <b id="gc-pv" style="color:#0366d6"></b> 次　·　访客 <b id="gc-uv" style="color:#0366d6"></b> 人</span>
    </div>
    <!-- GoatCounter：访问追踪 -->
    <script data-goatcounter="https://jenniferzhao0531.goatcounter.com/count" async src="//gc.zgo.at/count.js"></script>
    <!-- GoatCounter：在页面上显示总访问 / 访客数 -->
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
      <h1>ICLR 2026 视觉-语言模型（VLM / MLLM）论文集</h1>
      <p>从 ICLR 2026 共 5,352 篇接收论文中筛选 {total} 篇 VLM/MLLM 相关论文，按 {n_cats} 个子领域分类，并按"研究动机 / 解决问题 / 现象分析 / 主要方法 / 数据集与实验 / 主要贡献"六个维度整理。中文分析由大语言模型基于英文 abstract 自动生成，仅供快速浏览参考，建议结合原文阅读。左上 Primary Area 下拉菜单可按 ICLR 官方一级研究方向再筛选；点论文标题跳 OpenReview 原文。</p>
    </div>
    {''.join(sections_html)}
  </main>
</div>
<script>{JS}</script>
</body>
</html>
"""

    Path(OUTPUT_HTML).write_text(html, encoding="utf-8")
    print(f"✅ 已生成 {OUTPUT_HTML}（{total} 篇，{n_cats} 个子领域）")

if __name__ == "__main__":
    build()
