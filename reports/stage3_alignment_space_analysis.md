# Stage 3 — 对齐空间分析（初步，截至 2026-11-05）

> 框架 `A = (Alignment Unit, Alignment Dimension, Alignment Scope)` 仅用于分析与设计，不宣称为新理论。

## 1. Alignment Unit（对齐单位）

| 单位 | Weather 可行性 | 状态 |
|---|---|---|
| window-level | 每个 4h 窗口 ↔ 文本（v1 已做） | ✅ |
| channel-level | 变量↔语义概念 | 🔧 受"不拆分全局 Prompt"约束；若需实现须先解决通道描述 provenance 与 Prompt 拆分约束 |
| event-level | 事件/状态变化↔文本 | 💡 缺可靠事件定义，推迟 |
| variable-group-level | 多变量关系↔复合描述 | 💡 推迟 |

## 2. Alignment Dimension（对齐维度）

| 维度 | 含义 | Weather 当前可操作性 |
|---|---|---|
| Semantic | 物理含义/概念属性 | ✅ v1 用全局 Prompt 整段（global-level） |
| Dynamic | 变化模式（趋势/周期/波动/突变） | ✅ v1 规则化窗口特征 |
| Temporal | 时间位置/顺序/边界 | 🔧 目前仅时间戳元数据；缺"有意义的语义时间监督"，暂不作为独立对齐目标 |
| Event | 事件身份/状态变化/时间边界 | 💡 缺可靠事件定义 |
| Relational | 变量间相关/依赖/协同 | 🔧 可由窗口统计（Pearson/滞后）派生"关系文本"，但须区分统计关系与语义/物理关系 |

**区别纪律**（总任务书强调）：
- Temporal ≠ Dynamic（前者时间位置，后者变化模式）；
- Semantic ≠ Event（前者概念含义，后者事件/状态变化）；
- Unit ≠ Dimension（两个独立分类轴）。

## 3. Alignment Scope（对齐范围）

- Local：窗口级（v1）。
- Global：语义 Prompt 为全局级。
- Cross-temporal：不同时间段/状态对齐 —— 未做。

## 4. 当前数据能支持的实验维度

**v1 实际支持**：Semantic(global) + Dynamic(window) 两个维度；可比较二者是否捕获不同信息（H1）、是否互补/冲突（H2）、是否损害 TS 特有信息（H5）。

## 5. 后续值得扩展的方向（须先有可靠监督）

- Temporal/Event：当且仅当能构造"非平凡且非泄漏"的时间/事件监督文本时。
- Relational 文本：由窗口统计派生，但须显式标注为统计关系、不冒充物理/语义关系。
- Adaptive alignment（Stage C）：仅当 A/B 实验发现样本级质量差异。

## 6. 风险

- 不应为凑齐五个维度而强行构造文本或损失函数；维度选择须由数据与实验结果驱动。
- Semantic 用全局 Prompt（非逐通道）会限制 channel-level 语义对齐的细粒度分析——这是当前合规约束下的折中，已在计划中标注为待解问题。
