# PROJECT_STATUS — Semantic-Dynamic-Relation

- 当前阶段：**Stage 1（Weather 数据规范化）—— 候选产物已完成，清洗策略待人工决策**（Stage 0 初始化 / 数据接入 / 数据检查已完成）
- 最后更新：2026-11-04（新增 Stage 1 记录，见第五节）
- 共享环境：`C:\Users\ZhaoChenguang\AppData\Local\Programs\Python\Python310\python.exe`（Python 3.10.6，复用 BEDTime，无新建 `.venv`）
- 固定随机种子：42（`configs/experiment.yaml`）

## 一、已完成

### 1. 项目初始化与规范
- 在 `d:/THU/Projects/202611/Semantic-Dynamic-Relation/` 下建立 `data/raw/`、`data/metadata/`、`configs/`、`scripts/`、`results/matrices/`、`results/figures/`、`results/tables/`、`reports/`、`logs/`，另加 `src/` 作为模块化代码包。
- 未修改 BEDTime 或工作区内其他任何项目；未创建 `.venv`；未执行任何 pip 安装/升级。
- 已创建：`README.md`、`requirements.txt`、`configs/experiment.yaml`、`PROJECT_STATUS.md`、`.gitignore`。
- 规范落地：路径统一在配置中以相对路径管理、随机种子固定 42、`data/raw/` 只读、结果/日志统一归档、所有写入「存在则另存带时间戳文件」不覆盖。

### 2. 共享环境核验（已实际运行 `scripts/check_environment.py`）
- Python 3.10.6；实测版本：pandas 2.2.0、numpy 1.26.4、scipy 1.15.3、matplotlib 3.10.9、seaborn 0.11.2、scikit-learn 1.1.2、torch 2.5.1+cu121、transformers 4.49.0、PyYAML 6.0.1、huggingface_hub 0.36.2。
- 第一阶段实际需要：`numpy` / `pandas` / `PyYAML`；**缺失项：无**，不需安装任何依赖。
- conda 中名为 `bedtime` 的环境（Python 3.10.22）缺少上述主要科学计算包，已排除；BEDTime README 中的 `conda activate bedtime_project` 在本机不存在对应环境。
- 归档：`reports/environment_check.md`、`logs/environment_versions.json`、运行日志。

### 3. 数据接入（已实际运行 `scripts/ingest_data.py`）
- 找到 Weather 数据：宽表 `../ChannelSemanticAlignment/data/raw/benchmark/Weather.csv`（7,235,425 B）与 TFB 长表 `../ChannelSemanticAlignment/archive/tfb_raw/Weather.csv`（41,540,278 B）；BEDTime 目录内无 Weather 数据。
- `data/raw/Weather.csv` **在初始化前已存在**且与宽表源 SHA256 完全一致 → 按「不覆盖已有文件」跳过复制，仅做一致性校验。
- 长表**实际复制**为 `data/raw/Weather_tfb_long.csv`，复制前后源 SHA256 不变、目标与源一致。
- 宽表 SHA256 `34ee981d07313e51da2a50bb600072c8ae4a69cb4b0651f4cb93a069d7a2ba63`；长表 SHA256 `7a6cf692e2b19ac7e9ed2d51c48799d4e49aa0013042282c5b1da5239fe65ae5`。
- 归档：`data/metadata/data_manifest.csv`（源/目标路径、大小、SHA256、校验结果、时间）。

### 4. 通道文本描述
- 单独检查结论：**未找到可靠、结构化、带逐条来源标注的通道描述表**。工作区内仅有 `ChannelSemanticAlignment/scripts/run_timecma_multidataset.py` 中硬编码的 `WEATHER_SEM` 字典及其自动生成的 `docs/dataset_audit_Weather.md`，无逐条 provenance，且 3 个通道因列名编码损伤退化成「描述 = 通道名」。
- 因此只创建模板 `data/metadata/channel_descriptions.template.csv`：21 个通道名逐字抄自原始表头，描述/单位/来源/provenance **全部留空**，`verified=pending`。未编造任何语义描述。

### 5. 数据检查（已实际运行 `scripts/check_data.py`，读取成功）
- 52,696 行 × 22 列；时间列 `date`；21 个变量列全部有效；时间范围 2020-01-01 00:10:00 ~ 2021-01-01 00:00:00，10 min 间隔。
- 缺失值 0；完全重复行 1、变量区重复 1、重复时间戳 1（`2020-05-12 06:00:00`）；时间缺口 1 处（2020-05-29 09:30 → 11:10，缺 9 个时间片）。
- IQR(×1.5) 异常 38,562 个（3.4847%）、无穷值 0、`rain (mm)` 与 `raining (s)` 的 IQR=0（其异常计数需谨慎解释）；疑似哨兵值 `-9999` 共 81 个（`wv (m/s)` 1、`max. PAR` 30、`OT` 50）。
- 3 个列名含 U+FFFD（源数据既有编码损伤，未修改）。
- 长表交叉校验：1,106,616 行 = 52,696 × 21，21 通道等长，`(date, cols)` 重复 0，`data` 无缺失。
- 归档：`reports/weather_data_check.md`、`results/tables/weather_summary.csv`、`weather_variables.csv`、`weather_audit.json`、运行日志。

## 二、进行中

- 研究问题尚未开始验证，不得据此声称任何关于语义/动态关系一致性的结论。
- Stage 1 事实调查已完成，**6 项清洗策略等待人工决策**（见第五节）；确认前不生成最终规范化版本。

## 三、待办 / 下一阶段缺少的输入（阻塞项，等待确认）

| # | 缺少的输入 | 用途 | 当前状态 |
|---|---|---|---|
| 1 | **可靠的通道文本描述表**：21 个通道各自的文本描述 + 单位 + 逐条来源（文档名/URL/版本）+ 许可确认 | 计算 Semantic Relationship 的唯一合法输入 | 只有空模板 `data/metadata/channel_descriptions.template.csv`；需用户提供，或明确授权引用既有硬编码字典并补齐 provenance |
| 2 | **编码损伤列名映射**：`SWDR (W/m...)`、`PAR (...mol/m.../s)`、`max. PAR (...mol/m.../s)` 的规范列名（原应为 `²`/`µ` 等字符） | 保证描述表与数据列能正确对齐；否则 3 个通道的语义会被错误回退 | 待确认；原始数据未修改 |
| 3 | **`-9999` 哨兵值处理决策**：是否视为缺失、采用何种清洗/掩码规则 | 81 个 -9999 会严重污染相关性与动态关系估计 | 待确认；本阶段仅统计，未替换 |
| 4 | **重复时间戳与时间缺口处理策略**：去重规则、是否补齐 9 个时间片、是否保持原始时间轴 | 决定动态关系计算的时间对齐方式 | 待确认 |
| 5 | **语义关系定义与文本编码方案**：TF-IDF / 句向量 / 大模型 embedding 及模型来源（是否允许下载） | 构造 \(S_{sem}\) | 未决定；第一阶段未下载任何 Embedding 模型 |
| 6 | **动态关系定义**：Pearson / Spearman / 互信息 / 时滞相关 / 格兰杰等，及是否分窗口 | 构造 \(S_{dyn}\) | 未决定 |
| 7 | **一致性评价与「错误先验」判定标准**：结构相关性、邻居重叠、不一致四象限、下游预测增益等 | 回答 RQ1–RQ3 | 未决定 |
| 8 | **实验划分与数据切分协议**（训练/验证/测试、窗口长度、归一化） | 保证可复现与公平比较 | 未决定；随机种子已固定 42 |

> 上述 1–4 项是启动语义/动态关系计算的前置条件；5–8 项需在计算前明确写入 `configs/experiment.yaml`。

## 四、明确未执行（第一阶段边界）

- 未训练任何深度学习模型，未设计融合网络；
- 未下载或加载大型文本 Embedding 模型；
- 未计算语义关系矩阵 \(S_{sem}\)、动态关系矩阵 \(S_{dyn}\) 或任何一致性指标；
- 未生成、补全或臆测通道语义描述；
- 未对 `data/raw/` 做任何写入、填充、替换或重采样；
- 未改动 BEDTime 的虚拟环境配置，未创建 `.venv`，未安装/升级依赖。

---

## 五、Stage 1：Weather 数据规范化（2026-11-04 新增）

- **状态**：候选产物已完成；所有清洗策略标记 `Unknown — pending human decision`，**未生成最终规范化版本**。
- **入口**：`python scripts/normalize_data.py`（复用 BEDTime 共享环境，未安装/升级任何依赖）。
- **原始数据保护**：`data/raw/Weather.csv` 与 `data/raw/Weather_tfb_long.csv` 处理前后 SHA256 完全一致；候选产物全部写入独立目录 `data/processed/`。
- **完整报告**：`reports/weather_data_normalization.md`；清单：`data/processed/processed_manifest.csv`。

### 5.1 已完成

1. **列名调查**：核查 3 份宽表副本、2 份 TFB 长表副本、工作区全部数据集说明，并做公开来源检索；所有副本的 3 个列名同样含 U+FFFD，无官方 dataset card / 编码说明 → **无法确认**。保留原始列名，为 21 个通道分配稳定 ID `CH_00` ~ `CH_20`；工作区硬编码的 ASCII 近似名仅作低置信度候选记录，未应用。
2. **`-9999` 调查**：81 个单元格 / 80 行 / 3 个变量（`OT` 50、`max. PAR` 30、`wv (m/s)` 1）；`OT` 含连续 34 点段，`max. PAR` 多段短连续且集中在白天；无官方缺失标记说明 → **无法确认是否缺失值**。构建 81 条稀疏掩码（置空 / NaN），不插值、不填 0。
3. **重复时间戳**：`2020-05-12 06:00:00` 共 2 行（索引 19043、19044），21 个变量逐列完全一致；未删除。
4. **时间缺口**：`2020-05-29 09:30:00 → 11:10:00`（100 分钟），缺 9 个 10 min 时间片；前后温度/湿度/辐射明显变化；未补齐、未重采样、未插值。
5. **候选数据**：A 原值版（0 处修改，SHA256 与原始文件字节级一致）、B masked 版（81 单元格 / 80 行 / 3 变量改为 NaN）；两者 52,696 行 × 22 列、时间轴与列名完全相同，均标记 `candidate — not final`。
6. **决策表**：`data/metadata/data_cleaning_decisions.csv` 列出 D01–D06 共 6 项待确认决策，含证据状态、可选方案、对滑动窗口与滞后相关的影响。
7. **运行验证**：12 项校验全部通过（候选 A 逐值一致、候选 B 仅 81 处 NaN 且其余值不变、时间列不变、原始 SHA256 前后不变等）。

### 5.2 待人工决策（阻塞 Stage 2）

- D01 列名是否规范化 / 采用哪套规范名；D02 `-9999` 是否视为缺失、是否应用掩码；D03 重复时间戳处理；D04 缺口处理（含补齐 / 切段 / 保留）；D05 最终版本选择与生成时机；D06 下游通道标识（原始列名 / 稳定 ID / 规范名）。
- 第三节待办 #2 / #3 / #4 已完成事实调查，转入上述 D01–D05；**#1 通道文本描述表仍缺**，Stage 1 未生成任何通道描述。
- 报告第 7 节已给出 5 种时间轴方案及哨兵值掩码对滑动窗口与滞后相关计算的影响分析，但**未替用户选择任何方案**。

### 5.3 明确未执行（Stage 1 边界）

- 未修改 `data/raw/` 任何文件，未修改 BEDTime 或其他项目；
- 未删除重复行、未补齐或重采样时间轴、未插值、未把 `-9999` 替换为 0 或其他值；
- 未把候选规范列名应用到数据文件，未生成通道语义描述；
- 未构建语义关系矩阵、动态关系矩阵，未训练模型，未安装或升级依赖。
