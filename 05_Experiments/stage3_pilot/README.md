# Stage 3 Pilot — Multi-dimensional Cross-modal Representation Alignment (Weather)

> 实验推进阶段（总任务书：多维度跨模态表示对齐研究）。本目录为**独立新增实验目录**，不覆盖任何已有审计报告或旧实验。
> 创建日期：2026-11-05。随机种子：42（全局固定）。

## 目标（本轮最小可运行）

1. 构造 Weather 的**第一版增量文本视图**（Dynamic Text，规则化、可复现、有数值依据），并保留 `existing` 视图 = 用户提供的全局 Prompt V1（整段，不拆分）。
2. 生成可复现的 **TS-Text 样本**（带样本索引 + 时间窗口索引）。
3. 建立 **TS-only 与 TS+Text 最小对照实验**骨架，并完成 CPU/GPU Smoke Test（数据加载→前向→Loss→反向→设备/显存）。

## 目录结构

```text
stage3_pilot/
├── README.md
├── configs/exp_config.yaml        # 全部超参与数据视图版本、来源
├── src/
│   ├── data/weather_window_dataset.py   # 连续性窗口 + 缺失窗口剔除 + 文本挂载
│   ├── text_generation/
│   │   ├── dynamic_text.py              # 规则化动态文本（增量信息）
│   │   └── text_views.py                # 四种文本视图与全局 Prompt V1
│   ├── encoders/{ts_encoder,text_encoder}.py
│   ├── alignment/contrastive.py         # InfoNCE
│   ├── models/cross_modal_model.py      # TS 编码器 + 文本编码器 + 预测头 + 投影头
│   └── evaluation/alignment_metrics.py  # CKA / RSA / CCA / TS-specific probe
├── scripts/
│   ├── generate_text_views.py           # 生成 TS-Text 样本 + 规则版本 + 校验
│   └── run_smoke_test.py                # 最小对照实验 Smoke Test
├── results/   # 生成的样本与实验结果
└── logs/      # 运行日志
```

## 数据保护

- `data/raw/Weather.csv` **只读**；窗口化复用 `src/continuity.py`（boundary 策略）。
- 使用 `MASKED_VIEW`（`-9999` → NaN）并**剔除含 NaN 的窗口**；不修改原始数据、不插值、不填 0。
- 所有窗口/切分/视图参数均为 **pilot 候选值**（源自 Stage 1.6 候选协议，未冻结），见 `configs/exp_config.yaml`，保证可复现。

## 文本视图合规说明

- `existing` 视图 = 全局 Prompt V1 逐字整段（来源：`reports/stage2_original_method_reproduction.md` V1，SHA256 已登记）。**未拆分为 21 段独立 Prompt**。
- `dynamic` 视图 = 由窗口数值特征（趋势/波动/极值）规则化生成的紧凑标记，**提供现有描述中没有的动态增量信息**，无 LLM、无臆造物理含义。
- 不猜测未确认通道（尤其 `CH_20`/`OT`）的物理含义；文本中仅使用稳定通道 ID 与数值特征。
