# -*- coding: utf-8 -*-
"""
ICLR 2026 全量爬取 + 二级分类（大类 = ICLR 官方 primary_area，小类 = LLM 打标）
==============================================================================

流水线：
  1. 从 OpenReview 拉取 ICLR 2026 全部 5,352 篇接收论文
  2. 大类直接复用作者填的 primary_area（免费、权威）
  3. 小类调 LLM —— 每个 primary_area 内有自己的小类清单（见 SUBCATEGORIES_BY_PRIMARY）
  4. 输出 ICLR2026_all_papers.json，schema 和原 VLM/MLLM 文件兼容

使用：
  pip install openreview-py openai tqdm
  在 .env 里填好 OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL
  python crawl_all_papers.py

支持断点续跑：中断后重跑会跳过已分类的论文。
"""

import json
import os
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed


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


# ============ 1. 基本配置 ============
VENUE_ID = "ICLR.cc/2026/Conference"
OUTPUT_JSON = "ICLR2026_all_papers.json"
DESCRIPTION = "ICLR 2026 全部接收论文（中文导读 · 二级目录）"

OPENREVIEW_API = "https://api2.openreview.net"

API_KEY = os.environ.get("OPENAI_API_KEY", "YOUR_API_KEY_HERE")
BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")
MAX_WORKERS = 8
RESUME = True


# ============ 2. primary_area 中英文对照（大类）============
PRIMARY_AREA_ZH = {
    "alignment, fairness, safety, privacy, and societal considerations": "对齐/安全/公平性/隐私",
    "applications to computer vision, audio, language, and other modalities": "应用：CV/音频/语言等",
    "applications to neuroscience & cognitive science": "应用：神经/认知科学",
    "applications to physical sciences (physics, chemistry, biology, etc.)": "应用：物理科学",
    "applications to robotics, autonomy, planning": "应用：机器人/自动化/规划",
    "datasets and benchmarks": "数据集与基准",
    "foundation or frontier models, including LLMs": "基础/前沿模型 (含LLM)",
    "generative models": "生成模型",
    "infrastructure, software libraries, hardware, systems, etc.": "基础设施/软硬件",
    "interpretability and explainable AI": "可解释 AI",
    "neurosymbolic & hybrid AI systems (physics-informed, logic & formal reasoning, etc.)": "神经符号/混合 AI",
    "neurosymbolic & hybrid AI systems": "神经符号/混合 AI",
    "optimization": "优化",
    "other topics in machine learning (i.e., none of the above)": "其他 ML 主题",
    "other topics in machine learning": "其他 ML 主题",
    "probabilistic methods (Bayesian methods, variational inference, sampling, UQ, etc.)": "概率方法",
    "probabilistic methods": "概率方法",
    "reinforcement learning": "强化学习",
    "transfer learning, meta learning, and lifelong learning": "迁移/元/终身学习",
    "unsupervised, self-supervised, semi-supervised, and supervised representation learning": "表征学习",
    "learning on time series and dynamical systems": "时间序列与动力系统",
    "learning theory": "学习理论",
    "learning on graphs and other geometries & topologies": "图与几何拓扑学习",
    "causal reasoning": "因果推理",
}


# ============ 3. 二级分类清单：每个 primary_area 下的小类 ============
# 每个小类 {"name": 中文名, "hint": 给 LLM 看的英文关键词提示}
# 顺序就是网页侧边栏里的展示顺序；末尾的"其他"是兜底。
SUBCATEGORIES_BY_PRIMARY = {
    "应用：CV/音频/语言等": [
        {"name": "视觉-语言模型 (VLM/MLLM)",  "hint": "vision-language model, multimodal LLM, visual instruction tuning, MLLM"},
        {"name": "视觉理解",                  "hint": "image classification, recognition, detection, segmentation, image understanding"},
        {"name": "视频理解",                  "hint": "video understanding, temporal reasoning, action recognition, long video"},
        {"name": "3D 视觉与场景",             "hint": "3D vision, point cloud, depth, scene understanding, NeRF"},
        {"name": "医学图像",                  "hint": "medical imaging, radiology, pathology, clinical, diagnosis"},
        {"name": "文档/OCR/图表",             "hint": "OCR, document understanding, chart, table, GUI screen"},
        {"name": "遥感与科学图像",            "hint": "remote sensing, satellite, microscopy, scientific imaging"},
        {"name": "语音与音频",                "hint": "speech, audio, sound understanding, audio-visual"},
        {"name": "自然语言处理",              "hint": "NLP, question answering, translation, summarization, language tasks"},
        {"name": "其他应用",                  "hint": "其他不属于以上的 CV/音频/语言应用"},
    ],
    "基础/前沿模型 (含LLM)": [
        {"name": "LLM 预训练",               "hint": "pretraining, foundation training, scaling laws"},
        {"name": "指令微调与对齐",            "hint": "instruction tuning, SFT, DPO, preference optimization"},
        {"name": "推理与思维链",              "hint": "reasoning, chain-of-thought, GRPO, mathematical reasoning"},
        {"name": "多模态基础模型",            "hint": "multimodal foundation, unified model, omni-modal"},
        {"name": "长上下文",                  "hint": "long context, context extension, long-form"},
        {"name": "Agent 与工具使用",          "hint": "agent, tool use, GUI agent, web agent, mobile agent"},
        {"name": "效率与压缩",                "hint": "efficiency, distillation, quantization, KV-cache, speculative decoding"},
        {"name": "模型架构",                  "hint": "architecture, attention, mixture-of-experts, MoE, novel backbone"},
        {"name": "其他",                      "hint": "其他基础/前沿模型相关"},
    ],
    "数据集与基准": [
        {"name": "通用 VLM/MLLM 评测",        "hint": "multimodal benchmark, VLM eval, MLLM benchmark"},
        {"name": "推理与数学评测",            "hint": "reasoning benchmark, math eval, logic benchmark"},
        {"name": "Agent / 工具使用评测",      "hint": "agent benchmark, tool use eval, embodied benchmark"},
        {"name": "安全/对齐评测",             "hint": "safety benchmark, alignment eval, jailbreak benchmark"},
        {"name": "视觉理解基准",              "hint": "image, vision benchmark, perception eval"},
        {"name": "视频/长任务基准",           "hint": "video benchmark, long-form benchmark, streaming eval"},
        {"name": "代码与领域基准",            "hint": "code benchmark, scientific benchmark, domain-specific eval"},
        {"name": "数据集（不含评测协议）",    "hint": "pure dataset contribution, data collection, data curation"},
        {"name": "其他",                      "hint": "其他数据集与基准"},
    ],
    "生成模型": [
        {"name": "文本到图像 (T2I)",          "hint": "text-to-image, T2I"},
        {"name": "文本到视频 (T2V)",          "hint": "text-to-video, T2V, video generation"},
        {"name": "图像编辑",                  "hint": "image editing, inpainting, manipulation"},
        {"name": "3D / 4D 生成",              "hint": "3D generation, 4D, mesh, NeRF, Gaussian splatting"},
        {"name": "扩散模型",                  "hint": "diffusion model, score-based, DDPM"},
        {"name": "自回归 / 流匹配生成",       "hint": "autoregressive generation, flow matching"},
        {"name": "生成评测与可控",            "hint": "generation evaluation, controllability, conditioning"},
        {"name": "其他",                      "hint": "其他生成模型相关"},
    ],
    "对齐/安全/公平性/隐私": [
        {"name": "安全对齐",                  "hint": "safety alignment, RLHF, DPO, value alignment"},
        {"name": "越狱与攻击",                "hint": "jailbreak, prompt injection, attack"},
        {"name": "幻觉与事实性",              "hint": "hallucination, factuality, faithfulness"},
        {"name": "公平性与偏见",              "hint": "fairness, bias, discrimination"},
        {"name": "隐私 / 水印 / 版权",        "hint": "privacy, watermark, copyright, membership inference"},
        {"name": "鲁棒性与对抗",              "hint": "robustness, adversarial, distribution shift"},
        {"name": "红队与评估",                "hint": "red-teaming, safety eval, alignment eval"},
        {"name": "其他",                      "hint": "其他安全/对齐相关"},
    ],
    "应用：机器人/自动化/规划": [
        {"name": "视觉-语言-动作 (VLA)",      "hint": "vision-language-action, VLA"},
        {"name": "操作 (Manipulation)",       "hint": "manipulation, grasping, dexterous"},
        {"name": "导航",                      "hint": "navigation, visual navigation"},
        {"name": "任务规划",                  "hint": "task planning, hierarchical planning, LLM planner"},
        {"name": "模仿学习",                  "hint": "imitation learning, behavior cloning"},
        {"name": "仿真到现实",                "hint": "sim-to-real, domain randomization"},
        {"name": "GUI / Web / Mobile Agent",  "hint": "GUI agent, web agent, mobile agent, computer use"},
        {"name": "其他",                      "hint": "其他机器人/规划相关"},
    ],
    "表征学习": [
        {"name": "自监督学习",                "hint": "self-supervised learning"},
        {"name": "对比学习",                  "hint": "contrastive learning, CLIP-like"},
        {"name": "跨模态表征",                "hint": "cross-modal representation, multimodal embedding"},
        {"name": "域适应与泛化",              "hint": "domain adaptation, generalization, OOD"},
        {"name": "表征分析",                  "hint": "representation analysis, probing"},
        {"name": "其他",                      "hint": "其他表征学习"},
    ],
    "强化学习": [
        {"name": "离线 RL",                   "hint": "offline RL, batch RL"},
        {"name": "多智能体 RL",               "hint": "multi-agent RL"},
        {"name": "基于偏好/反馈的 RL",        "hint": "preference-based RL, RLHF, RL from feedback"},
        {"name": "探索与奖励设计",            "hint": "exploration, intrinsic reward, reward shaping"},
        {"name": "RL 理论",                   "hint": "RL theory, PAC, regret"},
        {"name": "应用型 RL",                 "hint": "RL applications, RL for X"},
        {"name": "其他",                      "hint": "其他 RL 相关"},
    ],
    "应用：物理科学": [
        {"name": "物理 / 分子动力学",         "hint": "physics, molecular dynamics, MD simulation"},
        {"name": "化学",                      "hint": "chemistry, molecule, reaction"},
        {"name": "生物 / 蛋白质 / 药物",      "hint": "biology, protein, drug discovery, genomics"},
        {"name": "材料科学",                  "hint": "materials science, crystal"},
        {"name": "气候/地球科学",             "hint": "climate, earth science, atmosphere, ocean"},
        {"name": "其他",                      "hint": "其他物理科学"},
    ],
    "迁移/元/终身学习": [
        {"name": "迁移学习",                  "hint": "transfer learning, fine-tuning"},
        {"name": "元学习",                    "hint": "meta learning, few-shot"},
        {"name": "持续/终身学习",             "hint": "continual learning, lifelong, incremental"},
        {"name": "测试时适应",                "hint": "test-time adaptation, TTA"},
        {"name": "其他",                      "hint": "其他迁移/元/终身相关"},
    ],
    "可解释 AI": [
        {"name": "机制可解释性",              "hint": "mechanistic interpretability, circuit"},
        {"name": "探针与表征分析",            "hint": "probing, representation analysis, feature visualization"},
        {"name": "归因与因果",                "hint": "attribution, causal explanation, saliency"},
        {"name": "其他",                      "hint": "其他可解释性"},
    ],
    "图与几何拓扑学习": [
        {"name": "图神经网络 (GNN)",          "hint": "graph neural network, message passing"},
        {"name": "图 Transformer",            "hint": "graph transformer"},
        {"name": "几何深度学习",              "hint": "geometric deep learning, equivariant, manifold"},
        {"name": "其他",                      "hint": "其他图/几何"},
    ],
    "学习理论": [
        {"name": "泛化理论",                  "hint": "generalization theory, PAC-Bayes"},
        {"name": "优化理论",                  "hint": "optimization theory, convergence"},
        {"name": "表达能力",                  "hint": "expressiveness, approximation"},
        {"name": "其他",                      "hint": "其他理论"},
    ],
    "优化": [
        {"name": "优化器设计",                "hint": "optimizer design, Adam variants"},
        {"name": "训练动态",                  "hint": "training dynamics, loss landscape"},
        {"name": "凸 / 非凸优化",             "hint": "convex, non-convex optimization"},
        {"name": "其他",                      "hint": "其他优化"},
    ],
    "概率方法": [
        {"name": "贝叶斯方法",                "hint": "Bayesian, posterior"},
        {"name": "变分推断",                  "hint": "variational inference, ELBO"},
        {"name": "采样方法",                  "hint": "sampling, MCMC, Langevin"},
        {"name": "不确定性量化",              "hint": "uncertainty quantification, calibration"},
        {"name": "其他",                      "hint": "其他概率方法"},
    ],
    "时间序列与动力系统": [
        {"name": "时间序列预测",              "hint": "time series forecasting"},
        {"name": "动力系统建模",              "hint": "dynamical systems, ODE, neural ODE"},
        {"name": "时空数据",                  "hint": "spatiotemporal, traffic, weather"},
        {"name": "其他",                      "hint": "其他时间序列"},
    ],
    "应用：神经/认知科学": [
        {"name": "脑信号 / 脑解码",           "hint": "brain decoding, fMRI, EEG, neural signal"},
        {"name": "认知建模",                  "hint": "cognitive modeling"},
        {"name": "神经网络与大脑对齐",        "hint": "brain-aligned, neuroscience-inspired"},
        {"name": "其他",                      "hint": "其他神经/认知"},
    ],
    "神经符号/混合 AI": [
        {"name": "符号推理 + 神经网络",       "hint": "neuro-symbolic, symbolic reasoning"},
        {"name": "物理引导",                  "hint": "physics-informed neural network, PINN"},
        {"name": "形式化验证",                "hint": "formal verification, theorem proving"},
        {"name": "其他",                      "hint": "其他神经符号"},
    ],
    "基础设施/软硬件": [
        {"name": "训练系统",                  "hint": "training infrastructure, distributed training"},
        {"name": "推理加速系统",              "hint": "inference systems, serving"},
        {"name": "硬件 / 量化加速",           "hint": "hardware, accelerator, GPU, TPU"},
        {"name": "库与工具",                  "hint": "software library, framework"},
        {"name": "其他",                      "hint": "其他基础设施"},
    ],
    "其他 ML 主题": [
        {"name": "量子机器学习",              "hint": "quantum machine learning, QML, quantum computing"},
        {"name": "状态空间模型 (SSM/Mamba)",  "hint": "state space model, SSM, Mamba, structured state space"},
        {"name": "检索与索引",                "hint": "retrieval, indexing, search system, nearest neighbor"},
        {"name": "联邦学习",                  "hint": "federated learning, distributed training across clients"},
        {"name": "异常检测",                  "hint": "anomaly detection, out-of-distribution detection"},
        {"name": "AI for Science (杂项)",     "hint": "AI4Science not covered elsewhere"},
        {"name": "新方法/算法",               "hint": "novel learning algorithm, training method"},
        {"name": "其他",                      "hint": "其他 ML 主题，以上都不合适"},
    ],
    "因果推理": [
        {"name": "因果发现 / 结构学习",       "hint": "causal discovery, structure learning, DAG"},
        {"name": "因果推断 / 处理效应",       "hint": "causal inference, treatment effect estimation, ATE/CATE"},
        {"name": "异质性处理效应",            "hint": "heterogeneous treatment effects, HTE, individualized"},
        {"name": "反事实推理",                "hint": "counterfactual reasoning, what-if analysis"},
        {"name": "因果表征学习",              "hint": "causal representation learning, disentanglement"},
        {"name": "因果鲁棒性 / 不变性",       "hint": "causal robustness, invariance, distribution shift"},
        {"name": "其他",                      "hint": "其他因果推理"},
    ],
}

# 兜底小类（primary_area 不在上表里时使用）
DEFAULT_SUBCATEGORIES = [{"name": "其他", "hint": "无明确小类"}]


# ============ 4. 拉 OpenReview ============
def _v(field):
    if isinstance(field, dict) and "value" in field:
        return field["value"]
    return field


def fetch_all_iclr_papers():
    try:
        import openreview
    except ImportError:
        raise SystemExit("❌ 未安装 openreview-py：pip install openreview-py")

    print(f"[1/3] 从 OpenReview 拉取 {VENUE_ID} 全部接收论文...")
    client = openreview.api.OpenReviewClient(baseurl=OPENREVIEW_API)
    notes = client.get_all_notes(content={"venueid": VENUE_ID})
    print(f"  共拉到 {len(notes)} 篇接收论文。")
    return [{"id": n.id, "content": n.content} for n in notes]


def normalize_paper(note):
    content = note.get("content", {}) or {}
    pid = note.get("id", "")
    keywords = _v(content.get("keywords", [])) or []
    if isinstance(keywords, str):
        keywords = [keywords]
    primary_en = (_v(content.get("primary_area", "")) or "").strip()
    return {
        "id": pid,
        "url": f"https://openreview.net/forum?id={pid}",
        "title": (_v(content.get("title", "")) or "").strip(),
        "primary_area_en": primary_en,
        "primary_area": PRIMARY_AREA_ZH.get(primary_en, primary_en or "(未填)"),
        "category": None,  # 待 LLM 填（小类）
        "keywords": keywords,
        "tldr": (_v(content.get("TLDR", "")) or _v(content.get("tldr", "")) or "").strip(),
        "abstract": (_v(content.get("abstract", "")) or "").strip(),
    }


# ============ 5. LLM 二级分类 ============
SYSTEM_PROMPT_CAT = (
    "你是一位精通中英文的 AI 研究员。给定一篇论文和它所在大类下的小类清单，"
    "你需要选出最匹配的一个小类。严格只输出 JSON：{\"category\": \"<中文名>\"}，"
    "不要写任何解释、Markdown、思考过程。"
)


def build_categorize_prompt(paper, subcats):
    cat_list = "\n".join(f"- {c['name']}：{c['hint']}" for c in subcats)
    keywords = "、".join(paper.get("keywords", []) or [])
    fallback = subcats[-1]["name"]
    return f"""这篇论文属于大类「{paper['primary_area']}」。请从下列小类中选**最匹配的一个**，输出 JSON：

{cat_list}

规则：
1. 只能从上面列表里选，名字一字不差。
2. 不到万不得已不要选 "{fallback}"。明显属于具体类别的，必须选具体类别。
3. 同时涉及多个时，选**研究焦点最集中**的那个。

【论文标题】{paper['title']}
【关键词】{keywords}
【TL;DR】{paper.get('tldr') or '(无)'}
【Abstract】
{paper.get('abstract', '')}

只输出 JSON：{{"category": "<中文名>"}}"""


def _extract_text(resp):
    if isinstance(resp, str):
        return resp
    if isinstance(resp, dict):
        try:
            return resp["choices"][0]["message"]["content"] or ""
        except Exception:
            return json.dumps(resp, ensure_ascii=False)[:500]
    try:
        return (resp.choices[0].message.content or "").strip()
    except Exception:
        return str(resp)[:500]


def _parse_category(text, valid_names):
    raw = (text or "").strip()
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict) and "category" in obj:
            cand = str(obj["category"]).strip()
            if cand in valid_names:
                return cand
    except Exception:
        pass
    m = re.search(r'"category"\s*:\s*"([^"]+)"', raw)
    if m and m.group(1) in valid_names:
        return m.group(1)
    cleaned = re.sub(r"[\"'`*【】「」\s]", "", raw)
    for name in valid_names:
        if cleaned == re.sub(r"\s", "", name):
            return name
    real_names = [n for n in valid_names if n != "其他" and not n.endswith("其他")]
    hits = [n for n in real_names if n in raw]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        return max(hits, key=len)
    for n in valid_names:
        if n in raw:
            return n
    return None


def categorize_paper(client, paper):
    primary = paper.get("primary_area") or "(未填)"
    subcats = SUBCATEGORIES_BY_PRIMARY.get(primary, DEFAULT_SUBCATEGORIES)
    valid_names = [c["name"] for c in subcats]
    fallback = subcats[-1]["name"]

    kwargs = dict(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT_CAT},
            {"role": "user", "content": build_categorize_prompt(paper, subcats)},
        ],
        max_tokens=200,
        temperature=0,
    )
    try:
        resp = client.chat.completions.create(**kwargs, response_format={"type": "json_object"})
    except Exception:
        try:
            resp = client.chat.completions.create(**kwargs)
        except Exception as e:
            return paper["id"], fallback, f"api error: {e}"

    text = _extract_text(resp)
    name = _parse_category(text, valid_names)
    if name is None:
        return paper["id"], fallback, f"unparsed: {text[:100]}"
    return paper["id"], name, None


# ============ 6. 主流程 ============
def save(papers, total_accepted):
    out = {
        "meta": {
            "source": f"OpenReview {VENUE_ID}",
            "total": len(papers),
            "total_accepted": total_accepted,
            "description": DESCRIPTION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "taxonomy": "two-level: primary_area (ICLR official) → category (LLM)",
            "fields": {
                "id": "论文唯一标识",
                "url": "OpenReview 论文链接",
                "title": "英文标题",
                "primary_area": "ICLR 官方一级方向（中文）",
                "primary_area_en": "ICLR 官方一级方向（英文原文）",
                "category": "LLM 打的二级小类（中文）",
                "keywords": "关键词列表",
                "tldr": "TL;DR",
                "abstract": "完整 Abstract",
            },
        },
        "papers": papers,
    }
    Path(OUTPUT_JSON).write_text(
        json.dumps(out, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main():
    if API_KEY == "YOUR_API_KEY_HERE":
        raise SystemExit("❌ 请先在 .env 写 OPENAI_API_KEY")
    print(f"使用 LLM: {MODEL} @ {BASE_URL}  (key: {API_KEY[:8]}...)")

    # ---- 1. 拉所有接收论文 ----
    notes = fetch_all_iclr_papers()
    all_papers = [normalize_paper(n) for n in notes]

    # 大类分布快速统计
    primary_cnt = Counter(p["primary_area"] for p in all_papers)
    print("\n[2/3] 大类分布（来自 ICLR 作者填写的 primary_area）:")
    for k, v in primary_cnt.most_common():
        has_subcats = "✓" if k in SUBCATEGORIES_BY_PRIMARY else "⚠ 未配小类"
        print(f"  {v:5d}  {k}  [{has_subcats}]")

    # ---- 2. 续跑：从已存在的 JSON 中读已分类的论文 ----
    done = {}
    if RESUME and Path(OUTPUT_JSON).exists():
        try:
            existing = json.loads(Path(OUTPUT_JSON).read_text(encoding="utf-8"))
            done = {p["id"]: p for p in existing.get("papers", []) if p.get("category")}
            if done:
                print(f"\n[3/3] 已恢复 {len(done)} 篇已分类的论文。")
        except Exception:
            pass
    if not done:
        print("\n[3/3] 调用 LLM 给每篇论文分配二级小类...")

    todo = [p for p in all_papers if p["id"] not in done]
    results = list(done.values())

    if todo:
        client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
        pbar = tqdm(total=len(todo), desc="分类中")
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            futures = {ex.submit(categorize_paper, client, p): p for p in todo}
            for fut in as_completed(futures):
                pid, cat, err = fut.result()
                paper = futures[fut]
                rec = {**paper, "category": cat}
                if err:
                    rec["category_error"] = err
                    tqdm.write(f"[警告] {pid}: {err[:120]}")
                results.append(rec)
                pbar.update(1)
                if len(results) % 100 == 0:
                    save(results, len(all_papers))
        pbar.close()
    else:
        print("  无新论文需要分类。")

    # ---- 3. 排序：先按大类（按数量降序），再按小类、标题 ----
    primary_order = {k: i for i, (k, _) in enumerate(primary_cnt.most_common())}
    def sort_key(p):
        primary = p.get("primary_area", "")
        subcats = SUBCATEGORIES_BY_PRIMARY.get(primary, DEFAULT_SUBCATEGORIES)
        sub_order = {c["name"]: i for i, c in enumerate(subcats)}
        return (
            primary_order.get(primary, 999),
            sub_order.get(p.get("category", ""), 999),
            p["title"],
        )
    results.sort(key=sort_key)

    save(results, len(all_papers))
    print(f"\n✅ 完成！共 {len(results)} 篇 → {OUTPUT_JSON}")

    # 最终分布
    print("\n二级目录分布:")
    by_primary = Counter(p["primary_area"] for p in results)
    for primary, _ in by_primary.most_common():
        n = by_primary[primary]
        print(f"\n📁 {primary} ({n})")
        sub_cnt = Counter(p["category"] for p in results if p["primary_area"] == primary)
        for sub, c in sub_cnt.most_common():
            print(f"    └─ {sub}: {c}")


if __name__ == "__main__":
    main()
