# -*- coding: utf-8 -*-
"""
ICLR 2026 全量论文 · 中文六维度分析（全量版）
==============================================

读 ICLR2026_all_papers.json（5352 篇），调 LLM 给每篇生成中文六维度分析，
输出 ICLR2026_all_papers_CN.json。

会自动复用旧版 ICLR2026_VLM_MLLM_papers_CN.json 里那 1063 篇已经做好的中文分析，
所以只需要给新增的 ~4290 篇调 LLM，省约 20% 费用。

支持断点续跑。
"""

import json
import os
from pathlib import Path

# ---- 自动加载同目录下的 .env 文件 ----
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

from openai import OpenAI
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed


# ============ 配置 ============
INPUT_JSON = "ICLR2026_all_papers.json"
OUTPUT_JSON = "ICLR2026_all_papers_CN.json"
REUSE_FROM = "ICLR2026_VLM_MLLM_papers_CN.json"   # 复用旧版的中文分析

API_KEY = os.environ.get("OPENAI_API_KEY", "YOUR_API_KEY_HERE")
BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")

MAX_WORKERS = 8
RESUME = True


# ============ Prompt ============
SYSTEM_PROMPT = """你是一位精通中英文的人工智能研究员，擅长用简练流畅的中文总结英文学术论文。
请严格输出 JSON 格式，不添加任何解释性文字。"""

USER_PROMPT_TEMPLATE = """请阅读下面这篇 ICLR 2026 的论文摘要，并用中文按六个维度进行精炼分析。

【论文标题】
{title}

【关键词】
{keywords}

【TL;DR】
{tldr}

【Abstract】
{abstract}

请用中文输出严格的 JSON，结构如下（每个字段 1-3 句话，专业精炼）：
{{
  "研究动机": "...",
  "解决问题": "...",
  "现象分析": "...",
  "主要方法": "...",
  "数据集与实验": "...",
  "主要贡献": "..."
}}"""


def analyze_paper(client, paper):
    prompt = USER_PROMPT_TEMPLATE.format(
        title=paper["title"],
        keywords="、".join(paper.get("keywords", []) or []),
        tldr=paper.get("tldr", "") or "(无)",
        abstract=paper.get("abstract", "")
    )
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )
        text = resp.choices[0].message.content.strip()
        if text.startswith("```"):
            text = text.split("```")[1].lstrip("json\n").rstrip()
        return paper["id"], json.loads(text), None
    except Exception as e:
        return paper["id"], None, str(e)


def main():
    if API_KEY == "YOUR_API_KEY_HERE":
        raise SystemExit("❌ 请先在同目录 .env 写 OPENAI_API_KEY")
    print(f"使用 LLM: {MODEL} @ {BASE_URL}  (key: {API_KEY[:8]}...)")

    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

    # 1. 读全量数据
    data = json.loads(Path(INPUT_JSON).read_text(encoding="utf-8"))
    papers = data["papers"]
    print(f"全量论文: {len(papers)}")

    # 2. 收集"已有中文分析"的论文（来自当前输出 + 旧 VLM/MLLM 版）
    done = {}  # id -> 中文分析

    # 2a. 当前输出（断点续跑）
    if RESUME and Path(OUTPUT_JSON).exists():
        try:
            existing = json.loads(Path(OUTPUT_JSON).read_text(encoding="utf-8"))
            for p in existing.get("papers", []):
                if p.get("中文分析"):
                    done[p["id"]] = p["中文分析"]
            if done:
                print(f"已恢复 {len(done)} 篇本次未完成的续跑数据")
        except Exception as e:
            print(f"读取 {OUTPUT_JSON} 失败：{e}")

    # 2b. 旧 VLM/MLLM 版（复用已有翻译，省钱）
    n_reused = 0
    if Path(REUSE_FROM).exists():
        try:
            old = json.loads(Path(REUSE_FROM).read_text(encoding="utf-8"))
            for p in old.get("papers", []):
                if p["id"] not in done and p.get("中文分析"):
                    done[p["id"]] = p["中文分析"]
                    n_reused += 1
            print(f"从 {REUSE_FROM} 复用了 {n_reused} 篇旧版翻译")
        except Exception as e:
            print(f"读取 {REUSE_FROM} 失败：{e}")

    # 3. 把 done 应用到 papers，识别 todo
    results = []
    todo = []
    for p in papers:
        if p["id"] in done:
            results.append({**p, "中文分析": done[p["id"]]})
        else:
            todo.append(p)

    print(f"\n待翻译: {len(todo)} 篇 / 总计: {len(papers)} 篇")
    print(f"  已复用: {len(results)} 篇（不调 LLM）")

    if not todo:
        save(results, data["meta"])
        print("\n✅ 无需调用 LLM，直接落盘")
        return

    # 4. 跑 LLM 翻译
    pbar = tqdm(total=len(todo), desc="翻译中")
    n_fail = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(analyze_paper, client, p): p for p in todo}
        for fut in as_completed(futures):
            pid, analysis, err = fut.result()
            paper = futures[fut]
            if analysis:
                results.append({**paper, "中文分析": analysis})
            else:
                results.append({**paper, "中文分析": None, "error": err})
                n_fail += 1
                tqdm.write(f"[失败] {pid}: {(err or '')[:120]}")
            pbar.update(1)
            # 每 50 篇落一次盘
            if len(results) % 50 == 0:
                save(results, data["meta"])
    pbar.close()

    save(results, data["meta"])
    n_ok = sum(1 for p in results if p.get("中文分析"))
    print(f"\n✅ 完成！结果保存至 {OUTPUT_JSON}")
    print(f"  成功: {n_ok}  失败: {n_fail}")
    if n_fail > 0:
        print(f"  💡 失败的 {n_fail} 篇可以直接重跑 python3 translate_all_papers.py，会自动只重做这些。")


def save(results, meta):
    out = {"meta": {**meta, "translated": True, "translation_model": MODEL}, "papers": results}
    Path(OUTPUT_JSON).write_text(
        json.dumps(out, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
