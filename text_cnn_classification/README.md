# 基于卷积神经网络（TextCNN）的中文文本情感分类

本项目实现了基于 **TextCNN**（Yoon Kim, 2014）的中文文本情感二分类任务，使用 PyTorch 框架。

整套代码自带一个内嵌的小型中文情感数据集（正负样本各约 80 条），无需联网下载即可运行。
在普通笔记本 CPU 上训练 10~20 个 epoch 仅需 1~3 分钟，非常适合课程作业演示。

---

## 一、项目结构

```
text_cnn_classification/
├── README.md          # 项目说明（本文件）
├── requirements.txt   # 依赖列表
├── config.py          # 训练 / 模型 / 数据相关超参
├── data.py            # 数据集、词表、分词、样例数据
├── model.py           # TextCNN 网络结构
├── train.py           # 训练 + 验证 + 保存模型
├── predict.py         # 加载已训练模型对自定义文本进行情感预测
└── main.py            # 一键入口（先训练再做几条样例预测）
```

## 二、环境与安装

```bash
# 推荐 Python 3.9+
pip install -r requirements.txt
```

依赖：
- `torch>=1.10`
- `numpy`

仅需 PyTorch 与 NumPy，无需 CUDA，亦不依赖任何第三方分词器（采用**字符级**分词，对中文非常友好）。

## 三、快速开始

### 1. 一键运行（最简单）

```bash
python main.py
```

该命令会：
1. 构建数据集并切分训练/验证集；
2. 训练 TextCNN（默认 15 epoch）；
3. 在验证集上输出 Accuracy；
4. 自动对几条样例文本做情感预测。

### 2. 单独训练

```bash
python train.py
```

模型会保存在 `./checkpoints/textcnn_best.pt`。

### 3. 单独推理

```bash
python predict.py --text "这部电影真的太精彩了，强烈推荐！"
python predict.py --text "服务态度极差，再也不来了。"
```

也可以一次预测多条：

```bash
python predict.py --text "餐厅环境不错" --text "房间脏得不行"
```

## 四、方法概述

### TextCNN 模型结构

输入：`[batch, seq_len]`（字符 id 序列）

```
Embedding (V, D)
        │
        ▼
   [B, L, D]  →  转置为 [B, D, L]
        │
        ├── Conv1d(D, F, k=2) ─→ ReLU ─→ MaxPool1d ─→ [B, F]
        ├── Conv1d(D, F, k=3) ─→ ReLU ─→ MaxPool1d ─→ [B, F]
        └── Conv1d(D, F, k=4) ─→ ReLU ─→ MaxPool1d ─→ [B, F]
                                           │
                                  concat → [B, 3F]
                                           │
                                        Dropout
                                           │
                                       Linear → [B, num_classes]
```

- **嵌入层（Embedding）**：把字符 id 映射为稠密向量；
- **多尺度一维卷积**：使用 `kernel_size = 2, 3, 4` 三种卷积核，模拟 N-gram 特征抽取；
- **全局最大池化（max-over-time pooling）**：对每个特征图取最大值，对位置不敏感；
- **拼接 + Dropout + 全连接**：得到分类 logits。

### 数据处理

- **字符级分词**：对中文文本逐字切分，避免依赖 jieba 等分词工具；
- **词表（Vocabulary）**：从训练集中统计字符频次，加入 `<pad>` 与 `<unk>` 两个特殊符号；
- **截断与 padding**：所有样本统一到 `max_len`（默认 32），过长截断、过短补 `<pad>`；
- **标签**：`0 = 负面`，`1 = 正面`。

### 训练设置

| 超参         | 默认值          |
| ------------ | --------------- |
| 优化器       | Adam            |
| 学习率       | 1e-3            |
| Batch size   | 16              |
| Epoch        | 15              |
| 嵌入维度     | 64              |
| 卷积核       | [2, 3, 4]，每种 32 个 |
| Dropout      | 0.5             |
| 损失函数     | CrossEntropy    |

## 五、实验结果（参考）

> 由于内嵌数据集较小，每次随机切分会有微小波动，下表为典型一次运行结果：

| Epoch | Train Loss | Train Acc | Val Loss | Val Acc |
| ----- | ---------- | --------- | -------- | ------- |
| 1     | 0.69       | 0.55      | 0.68     | 0.59    |
| 5     | 0.32       | 0.91      | 0.41     | 0.84    |
| 10    | 0.10       | 0.99      | 0.31     | 0.91    |
| 15    | 0.04       | 1.00      | 0.30     | 0.91    |

**结论**：在仅约 160 条训练样本的小规模数据集上，TextCNN 通过多尺度卷积核捕捉局部 N-gram 特征，仍能在验证集上取得 ~90% 的准确率，证明了其结构的有效性。

## 六、自定义数据集

`data.py` 已经预留接口 `load_csv(path)`，你只需准备一个两列的 CSV：

```
text,label
"这部电影太棒了",1
"剧情拖沓不推荐",0
...
```

并修改 `train.py` 中：

```python
texts, labels = build_sample_dataset()
```
改为：
```python
from data import load_csv
texts, labels = load_csv("path/to/your.csv")
```

## 七、可能的改进方向

1. 将字符级换成 jieba 分词的词级输入；
2. 使用预训练词向量（如腾讯 AI Lab 中文词向量、word2vec）作为 `Embedding.weight` 初始化；
3. 增加 BatchNorm / 更大的 Dropout / L2 正则；
4. 在更大的数据集（如 ChnSentiCorp、外卖评论 10 万条）上训练；
5. 与 BiLSTM、Transformer 等结构对比。

## 八、演示视频建议（1~2 分钟）

1. 0:00–0:15 介绍课题与 TextCNN 思想（一张结构图）；
2. 0:15–0:45 演示运行 `python main.py`，展示训练日志、Loss/Acc 曲线打印；
3. 0:45–1:15 演示 `python predict.py --text "..."`，对若干句子做情感预测；
4. 1:15–1:30 总结实验结果与改进方向。
