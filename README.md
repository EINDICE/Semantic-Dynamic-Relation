# Semantic-Dynamic-Relation

> 利用**通道文本语义信息**辅助**多变量时间序列的通道关系建模**。
> 当前阶段：Stage 1（Weather 数据规范化）—— 候选产物已完成、清洗策略待人工决策；Stage 0（初始化 / 数据接入 / 数据检查）已完成。**未训练任何模型、未计算任何关系矩阵、未生成最终规范化版本**。

## 1. 研究背景与问题

多变量时间序列模型常需要显式或隐式地建模「通道之间的关系」。一类做法是利用通道名称、变量说明等文本信息构造 **Semantic Relationship**（\(S_{sem}\)）；另一类做法是从观测到的时间变化中估计 **Dynamic Relationship**（\(S_{dyn}\)）。两者可能一致，也可能相互矛盾：语义相近的通道不一定同步变化，同步变化的通道也可能在文本上毫不相干。

本项目研究两个关系空间，并围绕三个核心问题展开：

1. **一致性**：语义关系与动态关系在多大程度上一致？不一致集中出现在哪些通道对？
2. **有效性**：语义信息在什么条件（数据类型、通道语义质量、动态结构强度、样本量等）下可以作为动态关系建模的有效先验？
3. **鲁棒性**：如何识别并抑制错误的语义先验，避免其干扰真实动态关系？

第一阶段只把「数据与事实」准备好，不对上述问题下结论。

## 2. 运行环境（复用 BEDTime 共享环境，不新建 .venv）

### 2.1 Python 解释器路径与激活方式

- **共享环境解释器（实测）**：
  `C:\Users\ZhaoChenguang\AppData\Local\Programs\Python\Python310\python.exe`
- **Python 版本**：3.10.6（64-bit，CPython）
- **环境性质**：这是一个**全局 Python 安装**，不是 venv / conda env（`sys.prefix == sys.base_prefix`），因此**没有 `activate` 脚本**。本项目直接复用它，不创建 `.venv`，不修改 BEDTime 的环境配置，不安装或升级任何依赖。
- **激活 / 使用方式（cmd.exe）**：

  ```bat
  :: 方式 A（推荐）：直接用绝对路径调用，不影响系统 PATH
  "C:\Users\ZhaoChenguang\AppData\Local\Programs\Python\Python310\python.exe" scripts\check_data.py

  :: 方式 B：仅在当前会话把该解释器目录置于 PATH 首位，随后可用 python
  set "PATH=C:\Users\ZhaoChenguang\AppData\Local\Programs\Python\Python310;C:\Users\ZhaoChenguang\AppData\Local\Programs\Python\Python310\Scripts;%PATH%"
  python scripts\check_data.py
  ```

- **判定依据**：BEDTime 的 `requirements.txt` / `environment.yml` 记录 Python 3.10.6 与 `numpy==1.26.4`、`pandas==2.2.0`、`matplotlib==3.10.9`、`scikit-learn==1.1.2`、`huggingface_hub==0.36.2`，与上述解释器实测版本逐一吻合；多个既有项目的运行日志中 torch 警告路径也指向 `...\Python310\lib\site-packages\torch\...`。
- **不要使用 conda `bedtime` 环境**：BEDTime README 写的是 `conda activate bedtime_project`，但本机 conda 中并无该环境；实际存在的 `C:\Users\ZhaoChenguang\anaconda3\envs\bedtime` 为 Python 3.10.22，且缺少 numpy / pandas / scipy / matplotlib / seaborn / scikit-learn / torch / transformers，不是本项目可用环境。

### 2.2 共享环境依赖版本（实测，见 `reports/environment_check.md`）

| 包 | 版本 | 第一阶段是否使用 |
|---|---|---|
| pandas | 2.2.0 | 是 |
| numpy | 1.26.4 | 是 |
| PyYAML | 6.0.1 | 是 |
| scipy | 1.15.3 | 否 |
| matplotlib | 3.10.9 | 否 |
| seaborn | 0.11.2 | 否 |
| scikit-learn | 1.1.2 | 否 |
| torch | 2.5.1+cu121 | 否 |
| transformers | 4.49.0 | 否 |
| huggingface_hub | 0.36.2 | 否 |

**第一阶段真正需要的依赖只有 `numpy`、`pandas`、`PyYAML`，三者均已安装，缺失项：无。**
未执行 `pip install`，未执行 `pip install -U`，未为本项目安装任何大型深度学习依赖。`requirements.txt` 仅作版本记录，不代表需要安装动作。

## 3. 目录结构

```
Semantic-Dynamic-Relation/
├── README.md                     项目背景、研究问题、环境与运行说明
├── PROJECT_STATUS.md             已完成 / 进行中 / 待完成任务
├── requirements.txt              第一阶段实际依赖（仅记录）
├── .gitignore                    缓存、临时文件、模型权重、大型中间文件
├── configs/
│   └── experiment.yaml           数据路径、随机种子、模型名称、实验参数的唯一来源
├── data/
│   ├── raw/                      【只读】Weather.csv、Weather_tfb_long.csv
│   ├── processed/                Stage 1 候选数据（非最终版本）、掩码、时间轴问题、清单
│   └── metadata/                 data_manifest.csv、channel_descriptions.template.csv、
│                                channel_name_mapping.csv、data_cleaning_decisions.csv
├── src/                          模块化 Python 代码
│   ├── settings.py               配置加载 / 路径解析 / 固定随机种子
│   ├── io_utils.py               SHA256、只读复制、绝不覆盖的写入、日志
│   ├── environment.py            共享环境版本采集
│   ├── audit.py                  数据加载、质量审计、表格与报告生成
│   └── normalization.py          Stage 1 调查、候选产物与规范化报告
├── scripts/
│   ├── ingest_data.py            数据接入入口
│   ├── check_environment.py      环境检查入口
│   ├── check_data.py             数据检查入口
│   └── normalize_data.py         Stage 1 数据规范化入口
├── results/
│   ├── matrices/                 关系矩阵（预留，为空）
│   ├── figures/                  图（预留，为空）
│   └── tables/                   weather_summary.csv、weather_variables.csv、weather_audit.json
├── reports/                      weather_data_check.md、environment_check.md、
│                                weather_data_normalization.md
└── logs/                         带时间戳的运行日志、environment_versions.json
```

规范：所有数据/输出路径都在 `configs/experiment.yaml` 中以相对路径集中配置（以项目根目录为基准）；随机种子固定为 `42`；`data/raw/` 只读，脚本只读取不写回；结果与日志统一归档；所有写入使用「存在则加时间戳另存」，**绝不覆盖已有文件**。

## 4. 数据接入

Weather 数据集来自工作区内既有项目 `ChannelSemanticAlignment`（源自 TimesNet `all_datasets/weather`，经 TFB 镜像）。BEDTime 项目目录内没有 Weather 数据。

| 表示 | 外部只读来源（相对本项目根） | 大小 | 项目内文件 | 处理 |
|---|---|---|---|---|
| 宽表 `date + 21 通道` | `../ChannelSemanticAlignment/data/raw/benchmark/Weather.csv` | 7,235,425 B | `data/raw/Weather.csv` | 目标文件已存在且与源一致 → 按「不覆盖」原则跳过复制，仅校验 |
| TFB 长表 `date,data,cols` | `../ChannelSemanticAlignment/archive/tfb_raw/Weather.csv` | 41,540,278 B | `data/raw/Weather_tfb_long.csv` | 实际复制，复制前后 SHA256 一致 |

- 宽表 SHA256：`34ee981d07313e51da2a50bb600072c8ae4a69cb4b0651f4cb93a069d7a2ba63`
- 长表 SHA256：`7a6cf692e2b19ac7e9ed2d51c48799d4e49aa0013042282c5b1da5239fe65ae5`
- 两个外部源文件在接入前后 SHA256 均未改变；目标文件 SHA256 与源逐一一致。完整记录见 `data/metadata/data_manifest.csv`。
- 另有同内容副本：`../ChannelSemanticAlignment/data/raw/all_datasets/weather/weather.csv`（宽表）、`../ChannelSemanticAlignment/archive/benchmark_tfb_long/Weather.csv`（长表）。
- 宽表是本项目的主分析文件；长表仅用于完整性交叉校验。

**通道文本描述表**：未找到可靠、结构化且带逐条来源标注的描述表。工作区内只有另一项目脚本中硬编码的 `WEATHER_SEM` 字典与自动生成的 Markdown 审计文档，缺少逐条 provenance，且 3 个通道因列名编码损伤退化为「描述 = 通道名」。因此本项目**不编造任何描述**，只生成模板 `data/metadata/channel_descriptions.template.csv`：通道名逐字抄自原始表头，`description` / `unit` / `source` / `provenance` 全部留空，`verified=pending`。

## 5. 运行说明

在项目根目录执行（cmd.exe）：

```bat
cd /d D:\THU\Projects\202611\Semantic-Dynamic-Relation
set "PY=C:\Users\ZhaoChenguang\AppData\Local\Programs\Python\Python310\python.exe"

"%PY%" scripts\check_environment.py   :: 记录共享环境版本 → reports/ + logs/
"%PY%" scripts\ingest_data.py         :: 只读复制 + SHA256 校验 + 清单 + 描述模板
"%PY%" scripts\check_data.py          :: 读取 Weather 并输出审计结果 → results/ + reports/ + logs/
"%PY%" scripts\normalize_data.py      :: Stage 1 规范化调查与候选产物（非最终版本）
```

三个脚本均可重复运行；若输出文件已存在，会自动写入带时间戳的新文件而不覆盖。脚本不依赖当前工作目录（通过 `__file__` 定位项目根目录）。

## 6. 第一阶段实测结果（已实际运行验证）

| 项目 | 结果 |
|---|---|
| 主文件格式 | UTF-8 CSV 宽表，22 列 |
| 行数 / 列数 | 52,696 行 / 22 列 |
| 时间列 | `date`，可完整解析，范围 `2020-01-01 00:10:00` ~ `2021-01-01 00:00:00`，标称间隔 10 min |
| 变量列 | 21 个，**全部有效**（数值可完整解析、非全空、非常量） |
| 缺失值 | 0（1,106,616 个变量单元格） |
| 重复值 | 完全重复行 1 行、变量区重复 1 行、重复时间戳 1 个（`2020-05-12 06:00:00`） |
| 时间缺口 | 1 处：`2020-05-29 09:30:00` → `11:10:00`（1h40），相当于缺 9 个 10 min 时间片 |
| 异常值 | IQR(×1.5) 共 38,562 个（3.4847%）；无穷值 0 |
| 疑似哨兵值 | `-9999` 共 81 个：`wv (m/s)` 1、`max. PAR (...)` 30、`OT` 50（仅统计，未替换） |
| 编码损伤 | 3 个列名含 U+FFFD：`SWDR (W/m...)`、`PAR (...mol/m.../s)`、`max. PAR (...mol/m.../s)`（源数据既有，未修改） |
| 长表交叉校验 | 1,106,616 行 = 52,696 × 21；21 通道长度一致；`(date, cols)` 重复 0 |

21 个变量列（按原始顺序；其中 `\ufffd` 是对 **U+FFFD 替换字符**的转义写法，原始列名中并不含反斜杠，完整原文见 `reports/weather_data_check.md`）：

`p (mbar)`, `T (degC)`, `Tpot (K)`, `Tdew (degC)`, `rh (%)`, `VPmax (mbar)`, `VPact (mbar)`, `VPdef (mbar)`, `sh (g/kg)`, `H2OC (mmol/mol)`, `rho (g/m**3)`, `wv (m/s)`, `max. wv (m/s)`, `wd (deg)`, `rain (mm)`, `raining (s)`, `SWDR (W/m\ufffd)`, `PAR (\ufffdmol/m\ufffd/s)`, `max. PAR (\ufffdmol/m\ufffd/s)`, `Tlog (degC)`, `OT`。

详见 `reports/weather_data_check.md` 与 `results/tables/`。

## 7. 第一阶段边界（明确不做）

- 不训练深度学习模型，不加载/下载大型文本 Embedding 模型；
- 不设计新的融合网络，不计算语义关系矩阵 \(S_{sem}\) 或动态关系矩阵 \(S_{dyn}\)；
- 不生成、不补全、不臆测任何通道语义描述；
- 不修改 `data/raw/` 中的原始数据，不做缺失值填充、异常值替换、时间重采样；
- 不改动 BEDTime 或工作区内其他项目，不创建新的 `.venv`，不安装/升级依赖。

## 8. 下一阶段缺少的输入

见 `PROJECT_STATUS.md` 的「待办 / 阻塞项」。核心缺口是：**带逐条来源标注的通道文本描述表**、**编码损伤列名的确认映射**、以及**哨兵值/重复时间戳/时间缺口的预处理决策**。这些输入确认之前，不启动语义矩阵与动态矩阵的计算。
