# Stage 1.5 — 数据决策预案与 Stage 2 前置准备

> **状态**：准备阶段。Stage 1 的全部清洗决策仍为 `Unknown — pending human decision`；**本轮没有、也不会把任何候选方案升级为最终规范化方案**。
> **依据**：`reports/weather_data_normalization.md`、`data/metadata/data_cleaning_decisions.csv`、`data/processed/processed_manifest.csv`。
> **本轮产物**：本报告；`src/continuity.py`（独立的时间连续性检查函数，属于「必要时新增独立函数」）；`PROJECT_STATUS.md` 准备状态更新。
> **本轮未生成任何数据集、CSV 表、矩阵或模型**，未修改 `data/raw/`、未覆盖 Stage 1 候选文件、未修改 BEDTime 及其他项目、未安装或升级依赖。

## 0. 本轮目标与边界

成功标准是让后续实验的**数据处理假设透明、可追溯、可复现**，而不是产出一份看起来干净的数据集。因此本轮只做三件事：

1. 把 7 条暂定原则整理成可检查的契约，检查冲突并给出建议（第 1 节）；
2. 定义 RAW_VIEW / MASKED_VIEW 的**接口契约与使用规范**，本轮不落地实现、不计算任何动态关系指标（第 2 节）；
3. 实现并验证一个独立的时间连续性检查函数，给出窗口构建的硬边界规则（第 3 节）。

另外整理 21 通道证据清单（第 4 节）与 Stage 2 前置 checklist（第 5 节）。所有结论中凡证据不足者一律保留 `Unknown`。

---

## 1. 数据决策预案：一致性检查与建议

### 1.1 七条暂定原则的落地状态

| # | 暂定原则 | 当前落地状态 | 对应产物 | 待注意的风险 |
|---:|---|---|---|---|
| P1 | 原始列名全部保留，不应用低置信度候选名称 | 已满足：Stage 1 两个候选文件均使用原始列名；3 个损坏列的 `canonical_name` 为空 | `data/metadata/channel_name_mapping.csv` | 无 |
| P2 | `CH_00`~`CH_20` 作为内部稳定通道 ID | 已建立：21 行映射，ID 与列顺序绑定 | 同上 | 未来列重排/子集选择会使 ID 漂移 |
| P3 | `-9999` 暂不认定为缺失值，但必须建立候选掩码 | 语义上未认定；81 条掩码已建立 | `data/processed/weather_stage1_missing_mask.csv`、候选 B | 「设为 NaN」与「不认定为缺失」存在语义层级张力（C1） |
| P4 | 重复时间戳暂时保留，标记重复记录 | 已满足：两个候选文件均 52,696 行；重复记录登记在独立清单 | `data/processed/weather_stage1_timeline_issues.csv` | 「标记」在数据文件之外，需明确载体；与窗口层排除的边界需分层（C4） |
| P5 | 原始时间轴不补齐、不插值、不重采样 | 已满足：时间列、行序、行数完全不变 | 候选 A / B 的验证结果 | 与 P6 是互补约束，不是冲突（C3） |
| P6 | 后续窗口构建不得跨越 100 分钟时间缺口 | 已具备执行手段：`src/continuity.py` 提供硬边界与窗口校验 | 本报告第 3 节 | **只覆盖 100 分钟缺口，未覆盖 0 分钟重复间隔**（C2） |
| P7 | 不生成最终规范化版本，直到用户确认关键决策 | 已满足：两个候选均标记 `candidate — not final` | `processed_manifest.csv` | 无 |

### 1.2 冲突与张力检查

**结论：7 条原则之间不存在硬逻辑冲突**，但存在 2 处语义层级混同、1 处覆盖缺口和 3 项实现/协议建议。

| 编号 | 涉及原则 | 性质 | 说明 | 建议 |
|---|---|---|---|---|
| C1 | P3 内部 | **语义层级混同** | 「`-9999` 不认定为缺失值」是**数据解释结论**；「MASKED_VIEW 把该单元格设为 NaN」是**计算层对照处理**。把后者称为「缺失值数据」会与 P3 直接矛盾 | 明确区分「语义认定 = Unknown」与「计算视图 = 敏感性对照」；所有输出强制声明 `view` 与 `nan_origin`；禁止把 MASKED_VIEW 描述为「已确认缺失的数据」 |
| C2 | P6 / P4 | **覆盖缺口** | P6 只禁止跨越 100 分钟缺口，但重复时间戳产生 **0 分钟间隔**、`exclude_all` 策略产生 **20 分钟间隔**，同样 `≠ 10min`。若只按 100 分钟切段，窗口仍会包含非等间隔步长 | 把 P6 改写为：**窗口不得跨越任何 `≠ 10min` 的实际时间间隔**；由 `check_time_continuity()` 统一标记 `issues`，其 `to_row` 全部作为硬边界 |
| C3 | P5 + P6 | **互补约束（非冲突）** | 正因为不补齐、不重采样，窗口才必须切段；而按**行索引**滑动的窗口会掩盖 100 分钟跳跃 | 窗口构建前强制调用连续性函数，且每个窗口必须通过 `validate_window*`；禁止仅凭行号相邻判定连续性 |
| C4 | P4 与第 3 节方案 B | **数据层 / 窗口视图层混同** | P4 要求「保留重复记录」，方案 B 要求「构造窗口时排除重复时间戳记录」。两者不矛盾，但必须显式分层，否则容易被理解为静默删行 | 用 `excluded_rows` 表示**仅窗口视图排除**，`duplicate_policy` 显式传入；数据层任何策略都保留 52,696 行，绝不删除或合并 |
| C5 | P2 | **潜在一致性风险** | 稳定 ID 与列顺序绑定；Stage 2 若做通道筛选、重排或新增派生通道，ID ↔ 列名契约会失效 | 把 `channel_name_mapping.csv` 作为不可变契约；任何通道子集/矩阵都必须携带 `channel_id_list`，禁止用位置隐式推断 |
| C6 | P3 与敏感性择优禁令 | **协议缺口** | 「如果两套结果差异明显，必须标记为数据解释敏感性」需要预先定义什么叫「差异明显」，否则事后可主观解释、实质上仍可能择优 | **预注册**差异度量与阈值（如 `abs_delta`、符号翻转、邻居排序变化）；两套结果同表并列呈现；阈值本身也是待用户确认项（P-S1） |

### 1.3 建议（不改变任何决策状态）

1. 把 7 条原则改写成**三层契约**，避免层级混同：

   | 层 | 内容 | 是否可在本轮变更 |
   |---|---|---|
   | 数据层 | `data/raw/` 只读；Stage 1 候选文件不覆盖、不升级；52,696 行、22 列、原始列名与原始时间轴 | 否 |
   | 视图层 | RAW_VIEW / MASKED_VIEW 逻辑别名；`nan_origin` 标签；`view` 必填声明 | 否（本轮仅定义契约） |
   | 窗口层 | `duplicate_policy`、硬边界、窗口长度 W、步长、`validate_window*` | 待用户确认后启用 |

2. **补充 P6 表述**为「任何 `≠ 10min` 的间隔均为窗口硬边界」（见 C2）。
3. **预注册敏感性阈值**（C6），并规定「双视图结果必须并列报告」。
4. 按暂定原则 P3，`-9999` 未被认定为缺失，因此 **RAW_VIEW 为基准视图，MASKED_VIEW 仅为敏感性对照视图**；不得把 MASKED_VIEW 单独作为主结果（最终仍需用户确认）。
5. 窗口长度 `W`、步长、训练/验证/测试划分、标准化 fit 范围等仍为 Stage 2 待定参数，本轮不设定。

---

## 2. RAW_VIEW / MASKED_VIEW 接口规范

> 本节是**接口契约与使用规范**，本轮不新建 Python 模块、不实现计算、不产出任何关系指标。

### 2.1 视图定义（只读逻辑别名，不新建文件）

| 视图 | 逻辑别名指向（Stage 1 候选，**非最终版本**） | SHA256 | 形状 | `-9999` | NaN | 状态 |
|---|---|---|---|---|---|---|
| `RAW_VIEW` | `data/processed/weather_stage1_candidate_raw.csv` | `34ee981d07313e51da2a50bb600072c8ae4a69cb4b0651f4cb93a069d7a2ba63` | 52,696 × 22 | 81 | 0 | 基准视图（按 P3 推论，待确认） |
| `MASKED_VIEW` | `data/processed/weather_stage1_candidate_masked.csv` | `968aa822f2a461db93fdd14da01923438c4f7fed4ebbb40f60ebc2e0c82e7105` | 52,696 × 22 | 0 | 81 | 敏感性对照视图 |

- 两个视图**不覆盖原始数据、不新建数据文件**：视图只是对既有候选文件的只读引用，且**不改变其 `candidate — not final` 状态**。
- 两者行数、列数、列名、`date` 列完全相同；唯一差异是 81 个单元格（已由 Stage 1 逐值验证）。
- MASKED_VIEW 中**没有插值、没有零填充、没有删行、没有改时间戳**；NaN 全部来自候选掩码。

### 2.2 强制声明契约

任何统计计算、动态关系计算或报告结果，必须显式声明所用视图；**`view` 参数必填且无默认值**，防止静默使用默认视图。

```python
# 接口契约（仅文档，本轮不落地实现）
def compute_dynamic_relation(
    view: ViewName,          # 必填，无默认值：RAW_VIEW | MASKED_VIEW
    metric: str,             # "pearson" | "spearman" | 其他（数学定义待 Stage 2 确认）
    *,
    nan_policy: str,         # 必填："pairwise_complete" | "listwise_delete" | "masked"
    time_scope: str,         # 必填："global" | "window" | "lagged"（待确认）
    duplicate_policy: str,   # 必填：见第 3 节
    seed: int = 42,
) -> RelationResult: ...
```

`RelationResult` 必须携带的元数据（缺任一项视为无效结果，不得进入报告）：

```
view_name, view_file, view_sha256, nan_policy, metric, time_scope,
n_rows, n_channels, channel_id_list, n_used_pairs, n_dropped_pairs,
duplicate_policy, window_rule_version, computed_at, seed
```

**禁止跨视图混用**：同一次实验的训练/验证/测试切分、标准化参数、关系矩阵、消融对照必须来自同一视图；禁止把两套结果择优拼接。

### 2.3 NaN 来源标签（不自动把所有 NaN 当成同一种缺失机制）

| 标签 | 含义 | 本数据中的数量 |
|---|---|---|
| `SENTINEL_CANDIDATE_MASK` | 由候选 `-9999` 掩码置空，**语义仍为 Unknown** | 81 |
| `SOURCE_MISSING` | 原始数据本身缺失 | 0 |
| `WINDOW_BOUNDARY` | 窗口切段产生的边界空位（未来若出现） | 0 |
| `DERIVED_UNKNOWN` | 由派生计算引入、来源未定 | 0 |

- 逐条 provenance 见 `data/processed/weather_stage1_missing_mask.csv`（81 行，含 row_index / date / channel_id / original_value / rule / evidence_status）。
- 禁止对不同 `nan_origin` 的 NaN 采用统一插补或统一删除；`nan_policy` 必须随结果记录。
- 禁止把 MASKED_VIEW 的 NaN 表述为「已确认的缺失值」。

### 2.4 敏感性对比协议

1. 每个动态关系指标（Pearson、Spearman 及其他待定指标）必须**在两个视图上各计算一次**，输出对照表：

   ```
   metric | channel_pair | raw_value | masked_value | abs_delta | sign_flip
          | rank_change | exceeds_threshold | interpretation_sensitivity
   ```

2. 差异度量候选：`abs_delta`、符号翻转、通道邻居排序变化（如 Jaccard@k）。**阈值需预注册**（P-S1，待用户确认），不得事后根据结果方向调整。
3. 若 `exceeds_threshold = True`，则 `interpretation_sensitivity = True`：两套结果**并列呈现**，报告中必须说明「结论对 `-9999` 的处理方式敏感」，**禁止直接选取更符合预期的一套**，也禁止省略另一套。
4. 本轮不实现该接口、不计算任何 Pearson / Spearman / 其他动态关系指标。

### 2.5 使用规范要点

- RAW_VIEW 为基准、MASKED_VIEW 为对照，二者地位不因结果好坏而改变（最终仍需用户确认）。
- 所有结果文件、表格、图注必须标注 `view_name` 与 `view_sha256`。
- 任何「数据解释敏感性」结论必须同时引用两套数值，不能只引用其中一套。
- 视图不落盘、不覆盖、不升级；最终规范化数据集在 D01–D06 确认前不生成。

---

## 3. 时间轴与窗口构建规则

### 3.1 独立的时间连续性检查函数

本轮唯一新增代码：`src/continuity.py`（独立模块，不修改 Stage 1 任何脚本）。只读、无副作用、不写文件、不构建窗口、不计算关系矩阵。

| 函数 | 作用 |
|---|---|
| `check_time_continuity(time_values, expected_interval="10min", duplicate_policy=...)` | 以**实际时间差**判断连续性；标记所有 `≠ 10min` 的间隔（`duplicate_zero` / `gap` / `short` / `negative` / `unparsable_time`）；返回 `issues`、`window_boundary_rows`、`segments`、`excluded_rows` |
| `estimate_window_count(segments, window_size)` | 估算步长 1、不跨段的窗口总数 |
| `validate_window_rows(rows, ...)` | 校验「活跃行序列」窗口：长度、段内连续子序列、时间严格等间隔 |
| `validate_window(start_row, end_row, ...)` | 便捷包装，适用于无排除行的 `boundary` 策略 |

`duplicate_policy` 必须**显式传入**，函数绝不静默删除或合并记录：

| 策略 | 含义 | 数据层行数 |
|---|---|---|
| `boundary` | 方案 A：全部记录保留，重复时间戳处作为窗口硬边界 | 52,696 |
| `exclude_all` | 方案 B：窗口视图排除重复时间戳的**全部**记录 | 52,696（仅视图排除 2 行） |
| `keep_first` | 方案 B 变体：仅排除重复组的后续记录 | 52,696（仅视图排除 1 行） |

### 3.2 实际运行验证结果（本轮只做连续性检查与窗口数估算）

| 策略 | 检出的不规则间隔 | 分段长度 | 窗口视图行数 | 段数 | W=24 窗口数 | W=96 窗口数 |
|---|---|---|---:|---:|---:|---:|
| `boundary` | `0 min` @19043→19044；`100 min` @21513→21514（缺 9 片） | 19044 / 2470 / 31182 | 52,696 | 3 | 52,627 | 52,411 |
| `exclude_all` | `20 min` @19042→19045（缺 1 片）；`100 min` @21513→21514（缺 9 片） | 19043 / 2469 / 31182 | 52,694 | 3 | 52,625 | 52,409 |
| `keep_first` | `100 min` @21513→21514（缺 9 片） | 21513 / 31182 | 52,695 | 2 | 52,649 | 52,505 |

窗口校验示例（实际运行结果）：

- `validate_window(0, 23, boundary, W=24)` → `valid=True`，跨度 `0 days 03:50:00`（23 × 10 min）。
- `validate_window(21510, 21533, ..., W=24)` → `valid=False`，原因「窗口跨越了时间不连续边界（含 100 分钟缺口）」。
- `validate_window(19040, 19063, keep_first, W=24)` → `valid=False`，原因「窗口包含窗口视图中排除的重复时间戳记录」。
- `validate_window_rows(19040..19043 + 19045..19064, keep_first, W=24)` → `valid=True`（活跃行序列合法）。

> **关键发现**：方案 B（`exclude_all`）**并没有消除不连续**——把 0 分钟间隔变成了 20 分钟间隔（新增 1 个缺失时间片），段数仍为 3，仍需切段。只有 `keep_first` 能让重复处保持 10 分钟连续并把段数降到 2。这一点只能靠「按实际时间差检查」发现，按行索引滑窗会完全漏掉。

### 3.3 两种重复时间戳方案比较

| 维度 | 方案 A：保留重复行 + 重复时间戳作为窗口边界 | 方案 B：保留原始记录，构造窗口时排除重复时间戳记录 |
|---|---|---|
| 数据层 | 52,696 行全部保留，无排除 | 52,696 行全部保留，`excluded_rows = [19043, 19044]` 仅为视图标记 |
| 窗口视图行数 | 52,696 | 52,694 |
| 重复处实际间隔 | 0 分钟（硬边界，切段） | 20 分钟（硬边界，切段，且新增 1 个缺失时间片） |
| 段数 / W=24 样本量 | 3 段 / 52,627 | 3 段 / 52,625 |
| 时间索引 | 段 1 末与段 2 首同为 `2020-05-12 06:00`，两段存在重叠时间戳；索引须段内重置 | `06:00` 在窗口视图中完全缺席，行索引连续但物理时间跳 20 分钟；需维护活跃行 ↔ 原始行映射 |
| 动态关系估计 | 两条完全相同的记录分属两段，该时刻模式在两段各计入一次；段内无 0 分钟 lag | 该时刻完全不参与；避免 0 分钟 lag，但出现 20 分钟 lag 风险（本函数已强制切段，故不会进入任何窗口） |
| 可追溯性 | 最保守：无排除行、无索引映射 | 需记录 `duplicate_policy` 与 `excluded_rows`，否则「排除」等价于静默丢样本 |
| 是否删除/合并记录 | 否 | 否（数据层保留，仅窗口视图排除） |

补充变体 `keep_first`：窗口视图 52,695 行、2 段、W=24 为 52,649 个窗口，是三者中样本量最大且时间轴最连续的方案；但它改变了参与计算的记录数，属于**需要用户明确确认**的策略，本轮不采用为默认。

### 3.4 窗口硬边界规则

1. `check_time_continuity()` 返回的所有 `window_boundary_rows` 为**硬边界**；窗口必须完整落在单个 `segment` 内。
2. `2020-05-29 09:30 → 11:10` 的 100 分钟缺口必须切断，9 个缺失时间片**不补齐、不插值**；`2020-05-12 06:00` 处按所选 `duplicate_policy` 处理。
3. 窗口数公式（步长 1、窗口长度 W）：`Σ max(0, L_i − W + 1)`，其中 `L_i` 为各段活跃行数；3.2 节给出 W=24 / 96 的实测值。**W 本身仍是 Stage 2 待定参数**。
4. 每个候选窗口必须先通过 `validate_window*`；返回 `valid=False` 一律拒绝，**禁止静默修正、补齐或跨段拼接**。
5. 缺口前后变量确有真实变化（`T` 17.17→15.28、`rh` 53.97→49.63、`SWDR` 565.59→926.91），跨缺口窗口会把 100 分钟当作 10 分钟，系统性扭曲滞后相关与高频通道估计。

### 3.5 处理建议（不替用户决定）

- **建议 1**：把暂定原则 P6 扩展为「任何 `≠ 10min` 的实际时间间隔都是硬边界」，覆盖 0 / 20 / 100 分钟三类情况（C2）。
- **建议 2**：以 `boundary` 作为最保守的默认窗口策略（不排除任何记录、可追溯性最好），`exclude_all` 作为对照；若希望消除 0 间隔又保留 `06:00` 一次记录，可评估 `keep_first`，但需用户确认。
- **建议 3**：三种策略都只是**窗口视图策略**，不修改 Stage 1 候选数据；`duplicate_policy` 必须写入每次实验的元数据。
- **建议 4**：窗口长度 W、步长、是否允许段内重叠、训练/验证/测试是否跨段，均应在 Stage 2 开始前预注册，避免按结果调参。

---

## 4. 21 通道语义描述证据清单

> 本轮**不生成正式 channel descriptions**。`data/metadata/channel_descriptions.template.csv` 仍为空模板（`description` / `unit` / `source` / `provenance` 全空，`verified=pending`）。

### 4.1 证据类型枚举

| 类型 | 定义 | 本轮使用情况 |
|---|---|---|
| `csv_header` | 原始 CSV 表头逐字读出的列名/单位 | 19 个通道的名称；19 个单位的字面来源 |
| `hardcoded_code` | 项目已有代码中硬编码的名称/描述 | 3 个 ASCII 近似候选名及其单位；`OT` 的物理含义叙述 |
| `official_documentation` | 官方 dataset card / 变量字典 / 随数据分发的 README，含文档名/URL/版本 | **0 条**：工作区内不存在（Stage 1 已确认） |
| `other_traceable` | 其他可追溯来源（带明确出处） | `dataset_audit_Weather.md` 仅到数据集级（「TimesNet all_datasets/weather via TFB mirror」），无逐通道信息，不足以支撑任何通道候选名 |
| `inference_or_guess` | 模型或人工推测 | **0 条**：本轮明确禁止生成推测 |

### 4.2 证据文件与位置

| 表中代号 | 完整路径（相对本项目根） | 说明 |
|---|---|---|
| `Weather.csv` | `data/raw/Weather.csv` | L1 为表头，C1=`date`，C2…C22 为 21 个通道 |
| `SEM.py` | `../ChannelSemanticAlignment/scripts/run_timecma_multidataset.py` | L51–L73 `WEATHER_SEM` 硬编码字典；L68–L70 为 3 个 ASCII 近似键；L99–L101 为数据集来源标注 |
| `AUDIT.md` | `../ChannelSemanticAlignment/docs/dataset_audit_Weather.md` | L13 通道名清单、L17–L18 语义来源声明、L9 数据集来源；由 `SEM.py` 自动生成 |
| `TEMPLATE.csv` | `data/metadata/channel_descriptions.template.csv` | 21 行空模板，无任何描述内容 |

> 表中 `\ufffd` 是 **U+FFFD 替换字符**的转义写法，原始列名中并不含反斜杠。

### 4.3 21 通道证据表

| channel_id | original_name | candidate_name | candidate_unit | evidence_file | evidence_location | evidence_type | confidence | unresolved_questions |
|---:|---|---|---|---|---|---|---|---|
| 0 | `p (mbar)` | `p (mbar)` | `mbar` | `Weather.csv` | L1/C2 | `csv_header` | high | 物理含义、官方变量字典与 provenance 未确认 |
| 1 | `T (degC)` | `T (degC)` | `degC` | `Weather.csv` | L1/C3 | `csv_header` | high | 同上 |
| 2 | `Tpot (K)` | `Tpot (K)` | `K` | `Weather.csv` | L1/C4 | `csv_header` | high | 同上 |
| 3 | `Tdew (degC)` | `Tdew (degC)` | `degC` | `Weather.csv` | L1/C5 | `csv_header` | high | 同上 |
| 4 | `rh (%)` | `rh (%)` | `%` | `Weather.csv` | L1/C6 | `csv_header` | high | 同上 |
| 5 | `VPmax (mbar)` | `VPmax (mbar)` | `mbar` | `Weather.csv` | L1/C7 | `csv_header` | high | 同上 |
| 6 | `VPact (mbar)` | `VPact (mbar)` | `mbar` | `Weather.csv` | L1/C8 | `csv_header` | high | 同上 |
| 7 | `VPdef (mbar)` | `VPdef (mbar)` | `mbar` | `Weather.csv` | L1/C9 | `csv_header` | high | 同上 |
| 8 | `sh (g/kg)` | `sh (g/kg)` | `g/kg` | `Weather.csv` | L1/C10 | `csv_header` | high | 同上 |
| 9 | `H2OC (mmol/mol)` | `H2OC (mmol/mol)` | `mmol/mol` | `Weather.csv` | L1/C11 | `csv_header` | high | 同上 |
| 10 | `rho (g/m**3)` | `rho (g/m**3)` | `g/m**3` | `Weather.csv` | L1/C12 | `csv_header` | high | 同上 |
| 11 | `wv (m/s)` | `wv (m/s)` | `m/s` | `Weather.csv` | L1/C13 | `csv_header` | high | 同上；该通道含 1 个 `-9999`（行 7245） |
| 12 | `max. wv (m/s)` | `max. wv (m/s)` | `m/s` | `Weather.csv` | L1/C14 | `csv_header` | high | 同上 |
| 13 | `wd (deg)` | `wd (deg)` | `deg` | `Weather.csv` | L1/C15 | `csv_header` | high | 同上 |
| 14 | `rain (mm)` | `rain (mm)` | `mm` | `Weather.csv` | L1/C16 | `csv_header` | high | 同上；IQR=0，异常统计需谨慎 |
| 15 | `raining (s)` | `raining (s)` | `s` | `Weather.csv` | L1/C17 | `csv_header` | high | 同上；IQR=0，异常统计需谨慎 |
| 16 | `SWDR (W/m\ufffd)` | `SWDR (W/m**2)` | `W/m**2`（low） | `SEM.py` | L68 | `hardcoded_code` | **low** | 原始字符不可逆；ASCII 近似无 provenance、与表头字面不匹配；**不得当作官方原始字段名**；单位与物理含义待确认 |
| 17 | `PAR (\ufffdmol/m\ufffd/s)` | `PAR (umol/m**2/s)` | `umol/m**2/s`（low） | `SEM.py` | L69 | `hardcoded_code` | **low** | 同上；含 0 个 `-9999`，但列名损坏 |
| 18 | `max. PAR (\ufffdmol/m\ufffd/s)` | `max. PAR (umol/m**2/s)` | `umol/m**2/s`（low） | `SEM.py` | L70 | `hardcoded_code` | **low** | 同上；含 30 个 `-9999` |
| 19 | `Tlog (degC)` | `Tlog (degC)` | `degC` | `Weather.csv` | L1/C21 | `csv_header` | high | 物理含义、官方变量字典与 provenance 未确认 |
| 20 | `OT` | `OT` | **Unknown** | `Weather.csv` | L1/C22（名称）；`SEM.py` L72（含义叙述） | `csv_header` / `hardcoded_code` | high（名称）/ low（单位与含义） | 表头未给单位；「observed air temperature」仅来自硬编码字典、无 provenance；含 50 个 `-9999`；单位与物理含义 Unknown |

### 4.4 关键结论

- **没有任何 `official_documentation` 证据**：工作区不存在官方 dataset card、变量字典或缺失值编码说明；`AUDIT.md` 与 `SEM.py` 只给数据集级来源「TimesNet all_datasets/weather (via TFB mirror)」，无文档名/URL/版本。
- **3 个 ASCII 近似名称（`SWDR (W/m**2)`、`PAR (umol/m**2/s)`、`max. PAR (umol/m**2/s)`）来自硬编码代码，置信度 low**，与原始表头字面不匹配（这正是 `AUDIT.md` 中这 3 条描述退化为列名本身的原因）。**严禁把其当作官方原始字段名**。
- 所有 21 行都存在未解决问题；`candidate_unit` 仅对表头含单位括号的 18 个通道可核验，`OT` 为 Unknown，3 个损坏列的单位仅有 low 置信度候选。
- 没有可核验来源的候选名称一律低置信度；本轮**未生成任何正式通道描述**，也未使用 `inference_or_guess` 类型。

---

## 5. Stage 2 前置条件 checklist

> 全部为 **Unknown / 未确认**。任一未确认项都不应被默认值隐式绕过。

| # | 前置条件 | 当前状态 | 为什么阻塞 | 需要确认的内容 | 关联决策 / 接口 |
|---:|---|---|---|---|---|
| 1 | 通道物理含义与单位 | Unknown | 3 个列名编码损伤、`OT` 无单位；硬编码描述无 provenance | 21 通道的物理含义、单位、以及 3 个损坏列的规范名 | D01、第 4 节证据表 |
| 2 | 通道描述 provenance | 缺失 | 无官方 dataset card；`WEATHER_SEM` 为脚本硬编码、无逐条引用 | 逐通道来源（文档名/URL/版本）+ 许可确认；是否允许引用现有硬编码字典 | D01、Stage 0 待办 #1 |
| 3 | `-9999` 处理规则 | Unknown（81 个单元格） | 未确认是否为缺失标记；掩码只是对照 | 语义认定、是否采用 MASKED_VIEW、`nan_policy`、敏感性阈值 | D02、P-S1、第 2 节 |
| 4 | 重复时间戳处理规则 | Unknown（2 行完全一致） | 三种窗口策略样本量与时间索引不同 | `boundary` / `exclude_all` / `keep_first` 或人工核验后合并 | D03、P-S2 |
| 5 | 时间缺口与窗口构建规则 | Unknown | 100 分钟缺口 + 9 个缺失时间片；窗口长度未定 | 是否所有 `≠10min` 均为硬边界；W、步长、段内重叠、是否允许跨段 | D04、P-S3、第 3 节 |
| 6 | 数据划分方案 | 未定 | 时间序贯切分与硬边界耦合，随机切分会跨越缺口并泄漏 | 训练/验证/测试比例与切分点、是否按段切分、是否避开缺口 | P-S6 |
| 7 | 标准化是否仅在训练集拟合 | 未定 | 全量拟合会引入测试集泄漏；跨视图/跨划分混用会污染比较 | 拟合范围、是否按视图分别拟合、参数是否随结果归档 | P-S5 |
| 8 | 语义关系与动态关系的数学定义 | 未定 | 定义不同则结果不可比较 | \(S_{sem}\) 的编码方式（TF-IDF / embedding / 是否允许下载模型）；\(S_{dyn}\) 的度量与显著性处理 | P-S7、P-S8 |
| 9 | 动态关系使用全局统计 / 滑动窗口 / 滞后关系 | 未定 | 三者对缺口、重复、掩码的敏感性完全不同 | 采用哪一种或多种并列、滞后阶数、窗口统计口径 | P-S8、第 3 节 |
| 10 | 区分统计相关、语义相似与实际有用交互 | 未定 | 相关≠语义、语义≠可用先验；无下游增益验证则无法回答研究问题 | 评价协议（结构一致性/邻居重叠/不一致四象限）、消融设计与「有用」的判定标准 | P-S9 |

---

## 6. 仍需用户决策的事项

**沿用 Stage 1（`data/metadata/data_cleaning_decisions.csv`）**：D01 列名规范化、D02 `-9999` 语义与掩码、D03 重复时间戳、D04 时间缺口、D05 最终版本选择、D06 下游通道标识 —— 6 项全部仍为 `Unknown`。

**本轮新增的待决协议项（均未设定默认值）**：

| 编号 | 待决事项 | 不确认的后果 |
|---|---|---|
| P-S1 | 双视图敏感性差异的度量与判定阈值 | 「差异明显」主观化，存在事后择优风险 |
| P-S2 | 窗口层 `duplicate_policy`（`boundary` / `exclude_all` / `keep_first`） | 窗口样本量、时间索引与估计口径不固定 |
| P-S3 | 窗口长度 W、步长、是否允许段内重叠 | 窗口数公式无法定值，结果不可复现 |
| P-S4 | `nan_policy`（pairwise-complete / listwise-delete / masked） | 两套视图的差异可能来自 NaN 处理而非 `-9999` 本身 |
| P-S5 | 标准化拟合范围（是否仅训练集） | 信息泄漏风险 |
| P-S6 | 数据划分方案（是否按段、是否避开缺口） | 跨缺口切分导致分布漂移 |
| P-S7 | 语义关系 \(S_{sem}\) 的数学定义与是否允许下载 Embedding 模型 | 无法计算语义矩阵 |
| P-S8 | 动态关系 \(S_{dyn}\) 的定义：全局 / 滑动窗口 / 滞后 | 无法计算动态矩阵 |
| P-S9 | 「统计相关 / 语义相似 / 实际有用交互」的区分标准与评价协议 | 无法回答核心研究问题 |

---

## 7. 本轮明确未执行

- 未修改 `data/raw/` 任何原始文件，未修改 BEDTime 或其他项目；
- 未生成最终规范化数据集，未覆盖 Stage 1 任何候选文件，未把候选方案升级为最终方案；
- 未新建任何 CSV/JSON 数据产物；本报告之外仅新增 `src/continuity.py`（独立时间连续性检查函数）并更新 `PROJECT_STATUS.md`；
- 未生成正式通道描述，未补全任何语义文本，未把 ASCII 近似名当作官方字段名；
- 未计算 Pearson / Spearman / 任何其他动态关系指标，未构建语义关系矩阵或动态关系矩阵；
- 未执行窗口训练、未训练模型、未安装或升级依赖；
- 未替用户选择任何清洗策略；所有决策仍为 `Unknown — pending human decision`。
