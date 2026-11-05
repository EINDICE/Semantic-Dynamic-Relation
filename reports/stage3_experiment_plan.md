# Stage 3 实验方案 — 多维度跨模态表示对齐（Weather Pilot）

> 创建：2026-11-05。依据总任务书《多维度跨模态表示对齐研究：实验推进总任务书》。
> 配套代码与样本：`05_Experiments/stage3_pilot/`。本轮只推进第一实际任务（文本构造 + 最小对照实验骨架 + Smoke Test）。
> **状态标记**：✅已实现并运行 / 🟡已实现未运行 / 🔧已设计未实现 / 💡仅设想。

## 1. 研究问题（与总任务书 H1–H6 对齐）

核心科学问题：**文本/语义信息到底为时间序列表示带来了什么、何时有效、是否会损害时序模态自身信息？**

| 假设 | 本研究将其转化为的可验证问题 |
|---|---|
| H1 不同对齐维度可能捕获不同信息 | Semantic / Dynamic / Temporal / Relational 文本各自对表示与预测的贡献是否不同？ |
| H2 维度间可能互补/冗余/冲突 | 联合对齐是否优于最佳单一对齐？是否存在负迁移？ |
| H3 单一对齐不足以表达复杂对应 | 是否存在需要联合监督才能显现的对应关系？ |
| H4 错误对应可能损害表示 | 随机/置换/错误配对文本是否使表示或预测变差？ |
| H5 对齐可能损害模态特有信息 | 对齐后 TS-specific 信息（线性探针）是否下降？ |
| H6 样本级对齐质量可能差异 | （Stage C 候选）自适应权重是否优于固定权重？ |

## 2. Alignment Space 定义

框架：`A = (Alignment Unit, Alignment Dimension, Alignment Scope)`（**仅为分析与设计框架，不宣称为新理论**）。

| 轴 | 候选值 | Weather 当前可操作性 |
|---|---|---|
| Unit | channel / window / event / variable-group | v1：**window-level**（每个 4h 窗口 ↔ 文本）；channel-level 受"不拆分全局 Prompt"约束，暂不实现 |
| Dimension | semantic / temporal / dynamic / event / relational | v1：**semantic**（全局 Prompt 整段）+ **dynamic**（规则化窗口特征）；temporal/event 暂无可靠监督，推迟 |
| Scope | local / global / cross-temporal | v1：global semantic + window dynamic；cross-temporal 未做 |

**结论**：v1 聚焦 Semantic + Dynamic 两个维度；其余维度在获得可靠监督后再扩展，避免强行构造五种文本/损失。

## 3. 文本构造规则（v1，已实现 ✅）

| 视图 | 内容 | 合规 |
|---|---|---|
| `existing` | 用户全局 Prompt V1 **整段**（逐字，SHA256 已登记），**不拆分为 21 段** | 符合"不擅自拆分全局 Prompt" |
| `dynamic` | 规则化：对每通道窗口算 趋势(↑↓→)/波动(H/M/L/C)/极值(*/^) ，输出紧凑 token 流 | 纯数值依据、无 LLM、无臆造物理含义、可复现 |
| `none` | 空文本（TS-only） | — |
| `both` | existing + dynamic 拼接 | — |

动态文本生成：`05_Experiments/stage3_pilot/src/text_generation/dynamic_text.py`。规则阈值见 `configs/exp_config.yaml[text_views.dynamic]`。已生成样本 8621 条，98.5% 动态文本唯一、0% 全常量无意义窗口（见 `results/text_views_stats.json`）。

## 4. 实验矩阵（阶段化）

**Phase 2 基线（已实现骨架 🟡，待正式运行）**

| 组 | 输入文本 | 对齐 | 目的 |
|---|---|---|---|
| A_ts_only | none | 否 | 时间序列基线 |
| B_ts_existing | existing | 否 | 现有描述增量 |
| C_ts_dynamic | dynamic | 是(InfoNCE) | 动态文本增量 |
| D_ts_both | both | 是 | 多维文本潜在价值 |

**Stage A 独立对齐 🔧**：semantic-only / dynamic-only 对齐，比较各自表征效果。
**Stage B 联合对齐 🔧**：semantic+dynamic；设 单一/联合/不对齐 三向对照，检验互补/冗余/冲突/负迁移。
**Stage C 自适应对齐 💡**：仅当 A/B 实验发现样本级质量差异后才研究；必须回答"为何需要自适应、解决什么问题"。

## 5. Baseline 与对照

- TS-only vs TS+Text：区分"文本增量" vs "普通融合" vs "真正对齐作用"。
- **伪对齐审计**（参考 `Multimodel/ts_align_audit/evaluate.py`）：原始/改写/随机文本相似度 gap。
- 随机文本、错误配对、置换文本对照（检验 H4）。
- TS-specific 信息保留：对齐前后对 TS 表示做线性探针（H5）。

## 6. 评价指标（多层，不只用下游指标）

1. **Correspondence Correctness**：窗口↔文本的检索 Recall@K / MRR（需可靠正负样本）。
2. **Representation Quality**：CKA / RSA / CCA / kNN / 线性探针（`src/evaluation/alignment_metrics.py` 已实现 CKA/RSA/CCA/探针）。明确：CKA≠语义正确、MMD≠对齐、CCA≠互补。
3. **Task Effectiveness**：Forecasting MSE/MAE（多通道下一窗口预测）。
4. **Modality-specific Preservation**：共享/特有信息分解，对齐指标↑时预测是否同步↑，是否过度对齐/负迁移。

## 7. 对照与消融

- 随机/置换文本（H4）；普通融合 vs 显式对齐；对齐强度（temperature / align_weight）扫描；对齐后 TS-specific 探针变化（H5）。

## 8. 预期风险

- **数据**：3 个 U+FFFD 通道、CH_20/OT 语义未确认——v1 只用稳定 ID 与数值，不断言物理含义；`-9999` 用 MASKED_VIEW 剔窗处理。
- **计算**：当前 Smoke 在**未归一化**原始尺度上跑（仅健全性）；正式实验须按 Stage 1.6 候选协议做 train-only 逐通道标准化，否则 MSE 被高方差通道主导。GPU 本机可用；如需租用须先报批。
- **方法**：动态/语义文本可能**不提供增量**（H1 可能不成立）；联合对齐可能负迁移（H2）；过度对齐抹除 TS 特有信息（H5）。若结果不支持某假设，如实记录。
- **创新纪律**：不把 MMD/CKA/Cross-Attention/Gating 本身当创新；不把模块组合当算法创新；不预设联合/自适应有效。

## 9. 状态汇总

| 项 | 状态 |
|---|---|
| 资产盘点（编码器/训练/评价复用） | ✅ 已完成（见本文件与代码注释） |
| 第一版增量文本视图（dynamic） | ✅ 已实现并生成 8621 样本 |
| TS-Text 样本（带索引，可复现） | ✅ 已生成 `results/ts_text_samples.csv` |
| TS-only/TS+Text 最小对照骨架 | ✅ 已实现（4 组） |
| Smoke Test（数据/前向/反向/设备） | ✅ 已运行（GPU），仅健全性 |
| 正式基线训练（归一化+全量） | 🔧 待执行 |
| 独立/联合对齐实验 | 🔧 已设计 |
| 自适应对齐 | 💡 仅设想 |
| 正式评价指标运行（CKA/RSA/CCA/探针） | 🔧 已实现函数，待接入 |
| 时间序列归一化接入 | 🔧 待接入（Stage 1.6 候选协议） |
