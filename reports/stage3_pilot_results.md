# Stage 3 Pilot — 实际运行结果与产物（截至 2026-11-05）

> **重要**：本节记录的是**已实际运行的产物与 Smoke Test 健全性输出**，**不是科学结论**。是否文本带来增量、对齐是否有效，需在正式（归一化、全量）实验中验证。

## 1. 文本视图生成（✅ 实际运行）

- 脚本：`05_Experiments/stage3_pilot/scripts/generate_text_views.py`
- 窗口构建：复用 `src/continuity.py`（boundary 策略），`W=24, S=6`，`masked` 视图（`-9999`→NaN）并剔除含 NaN 窗口。
- 结果：**8621 个有效窗口样本**，3 个连续段。
- 校验（`results/text_views_stats.json`）：
  - 动态文本唯一比例 **0.985**（8489/8621）→ 文本非无意义重复；
  - 全常量无意义窗口比例 **0.0**；
  - 潜在文本泄漏：**false**（动态文本仅由输入窗口推导，不含目标，无 LLM，无臆造物理含义）；
  - `raw_csv_sha256 = 34ee981d…`（与 Stage 1 候选原始文件一致，证明只读未改）；
  - `prompt_v1_sha256 = 55aba833…`（全局 Prompt V1 整段登记）。
- 产物：`results/ts_text_samples.csv`（sample_id + 窗口索引 + dynamic_text + existing_ref）。

## 2. 最小对照实验 Smoke Test（✅ 实际运行，GPU）

- 脚本：`05_Experiments/stage3_pilot/scripts/run_smoke_test.py`
- 规模：≤3000 窗口，chronological 70/15/15，batch=64，5 epoch，device=**cuda**（本机 CUDA 可用）。
- TF-IDF 仅在 **训练文本**上拟合（泄漏控制），实际词表维度 **81**。
- 四组（A_ts_only / B_ts_existing / C_ts_dynamic / D_ts_both）均能完成：数据加载→前向→预测 MSE→（C/D）InfoNCE 对齐损失→反向。
- 记录（`results/smoke_test_results.json`）的 **train/val forecast MSE** 与 **train_align**：

| 组 | view | align | val_f ep0→ep4（原始尺度 MSE，仅健全性） |
|---|---|---|---|
| A_ts_only | none | 否 | 84608 → 25214 |
| B_ts_existing | existing | 否 | 86242 → 27475 |
| C_ts_dynamic | dynamic | 是 | 66844 → 30906 |
| D_ts_both | both | 是 | 81960 → 30632 |

- `train_align ≈ 2.076`（C/D）：随机初始化下 InfoNCE 近似基线，5 步内未明显优化（预期，仅验证反向可行）。

### 2.1 为何这些数字**不能**作为结论

1. **未做时间序列归一化**：MSE 在原始尺度（不同通道量纲差异巨大）计算，被高方差通道主导；正式实验须按 Stage 1.6 候选协议做 train-only 逐通道标准化。
2. **仅 3000 窗口 / 5 epoch / 微型模型**：非完整训练，仅证明管线可端到端运行。
3. **组间差异微小且未控制变量**：B/C/D 的"文本增量"需在归一化、全量、固定随机种子与严格对照（随机文本、置换文本）下比较，才能回答 H1/H4。

## 3. 下一步必须做的事（才能产生可信结果）

1. 接入 **train-only 逐通道标准化**（RAW/MASKED 双视图并列，沿用 Stage 1.6 候选）。
2. 用**全部 8621 样本**训练，扩大模型与 epoch，固定 seed=42。
3. 加入**随机/置换文本对照**与**伪对齐审计**，分离"文本增量"与"普通融合"。
4. 接入 **CKA/RSA/CCA + TS-specific 线性探针**，回答 H5（是否损害模态特有信息）。
5. 在得到上述证据前，**不**宣称任何文本或对齐带来收益。
