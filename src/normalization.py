"""Stage 1：Weather 数据规范化的调查、候选数据生成与报告渲染。

本模块只做「质量事实调查 + 可逆的候选产物」，不执行任何删除、插值、
重采样、重命名或值替换到原始数据；所有策略状态保持 pending_human_decision。
"""

from __future__ import annotations

import json
from typing import Any, Sequence

import numpy as np
import pandas as pd

from . import audit, io_utils

REPLACEMENT_CHAR = "\ufffd"
UNKNOWN_STATUS = "Unknown — pending human decision"
PRIMARY_HEADER_EVIDENCE = "data/raw/Weather.csv:1"

# 只读调查结果：工作区内唯一「未损坏式」写法，来自另一项目脚本中的硬编码字典。
# 这是引用，不是推测；无 provenance，且与原表头字面不匹配，故不应用。
ASCII_APPROXIMATION_SOURCE = (
    "../ChannelSemanticAlignment/scripts/run_timecma_multidataset.py"
)
DAMAGED_COLUMN_EVIDENCE: dict[str, tuple[str, str]] = {
    "SWDR (W/m\ufffd)": ("SWDR (W/m**2)", "68"),
    "PAR (\ufffdmol/m\ufffd/s)": ("PAR (umol/m**2/s)", "69"),
    "max. PAR (\ufffdmol/m\ufffd/s)": ("max. PAR (umol/m**2/s)", "70"),
}

EVIDENCE_CHANNELS: tuple[tuple[str, str, str], ...] = (
    (
        "同一数据集其他副本（宽表）",
        "../ChannelSemanticAlignment/data/raw/benchmark/Weather.csv ; "
        "../ChannelSemanticAlignment/data/raw/all_datasets/weather/weather.csv",
        "与项目内副本 SHA256 相同，表头逐字一致，3 个列名同样含 U+FFFD",
    ),
    (
        "同一数据集其他副本（TFB 长表）",
        "../ChannelSemanticAlignment/archive/tfb_raw/Weather.csv ; "
        "../ChannelSemanticAlignment/archive/benchmark_tfb_long/Weather.csv",
        "cols 列 21 个取值与宽表一致，同样有且仅有这 3 个含 U+FFFD",
    ),
    (
        "工作区数据集说明 / 脚本",
        "../ChannelSemanticAlignment/docs/dataset_audit_Weather.md ; "
        + ASCII_APPROXIMATION_SOURCE
        + ":68-70",
        "文档只重复损坏列名，3 条描述退化为列名本身；脚本硬编码 ASCII 近似键，无 provenance",
    ),
    (
        "公开来源检索（只读，不下载数据）",
        "Kaggle 'Weather Long-term Time Series Forecasting (2020)' ; "
        "Hugging Face 'Jena-Climate' ; 公开教程/文档",
        "检索结果只给出通用列名与 ASCII 近似（如 SWDR (W/m**2)），"
        "未给出可核验的含 Unicode ²/µ 的原始表头；HF 页面抓取超时；"
        "未发现 -9999 官方缺失标记说明",
    ),
)

MAPPING_FIELDS = (
    "channel_id",
    "original_column",
    "stable_channel_id",
    "canonical_name",
    "candidate_name",
    "evidence_type",
    "evidence_source",
    "confidence",
    "status",
    "applied_to_candidates",
    "notes",
)
MASK_FIELDS = (
    "row_index",
    "date",
    "channel_id",
    "stable_channel_id",
    "original_column",
    "original_value",
    "masked_value",
    "rule",
    "evidence_status",
)
TIMELINE_FIELDS = (
    "issue_type",
    "timestamp_or_interval",
    "row_indices",
    "n_rows",
    "n_variables",
    "n_variables_identical",
    "all_variables_identical",
    "interval",
    "missing_slots",
    "detail",
)
DECISION_FIELDS = (
    "decision_id",
    "topic",
    "observed_facts",
    "evidence_source",
    "evidence_status",
    "options",
    "project_action_taken",
    "impact_on_sliding_window",
    "impact_on_lagged_correlation",
    "status",
    "needs_human_decision",
)
MANIFEST_FIELDS = (
    "entry",
    "path",
    "role",
    "rows",
    "columns",
    "bytes",
    "sha256",
    "sha256_before",
    "sha256_after",
    "source_unchanged",
    "modified_cells",
    "modified_rows",
    "affected_columns",
    "rules",
    "status",
)


def build_channel_mapping(
    header: Sequence[str], time_column: str, prefix: str = "CH_"
) -> list[dict[str, Any]]:
    """为每个通道建立稳定 ID；无法确认的列名保留原样并标记 Unknown。"""
    variables = [col for col in header if col != time_column]
    rows: list[dict[str, Any]] = []
    for index, column in enumerate(variables):
        stable_id = f"{prefix}{index:02d}"
        if REPLACEMENT_CHAR in column:
            candidate, line = DAMAGED_COLUMN_EVIDENCE.get(column, ("", ""))
            rows.append(
                {
                    "channel_id": index,
                    "original_column": column,
                    "stable_channel_id": stable_id,
                    "canonical_name": "",
                    "candidate_name": candidate,
                    "evidence_type": "hardcoded_ascii_approximation_no_provenance",
                    "evidence_source": f"{ASCII_APPROXIMATION_SOURCE}:{line}",
                    "confidence": "low",
                    "status": UNKNOWN_STATUS,
                    "applied_to_candidates": "no (original column name preserved; stable ID used)",
                    "notes": "所有本地副本表头均含 U+FFFD，损伤不可逆；候选名仅为引用，未应用",
                }
            )
        else:
            rows.append(
                {
                    "channel_id": index,
                    "original_column": column,
                    "stable_channel_id": stable_id,
                    "canonical_name": column,
                    "candidate_name": "",
                    "evidence_type": "dataset_header",
                    "evidence_source": PRIMARY_HEADER_EVIDENCE,
                    "confidence": "high",
                    "status": "confirmed_from_header",
                    "applied_to_candidates": "no_renaming_needed",
                    "notes": "列名不含 U+FFFD，保持原样",
                }
            )
    return rows


def investigate_sentinels(
    frame: pd.DataFrame,
    time_column: str,
    sentinel_values: Sequence[float],
    mapping_rows: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    """按变量统计哨兵值的位置、连续段与时间分布，并生成稀疏掩码记录。"""
    time = pd.to_datetime(frame[time_column], errors="coerce")
    id_lookup = {
        row["original_column"]: (row["channel_id"], row["stable_channel_id"])
        for row in mapping_rows
    }
    by_column: dict[str, Any] = {}
    mask_records: list[dict[str, Any]] = []

    for column in frame.columns:
        if column == time_column:
            continue
        numeric = pd.to_numeric(frame[column], errors="coerce")
        hits = np.isin(numeric.to_numpy(dtype="float64"), list(sentinel_values))
        indices = np.flatnonzero(hits)
        if indices.size == 0:
            continue
        runs_raw = np.split(indices, np.where(np.diff(indices) != 1)[0] + 1)
        runs = [
            {
                "start_row": int(group[0]),
                "end_row": int(group[-1]),
                "length": int(len(group)),
                "start_time": str(time.iloc[int(group[0])]),
                "end_time": str(time.iloc[int(group[-1])]),
            }
            for group in runs_raw
        ]
        hit_times = time.iloc[indices]
        by_column[column] = {
            "count": int(indices.size),
            "row_indices": [int(pos) for pos in indices],
            "time_min": str(hit_times.min()),
            "time_max": str(hit_times.max()),
            "runs": runs,
            "n_runs": len(runs),
            "max_run_length": max(run["length"] for run in runs),
            "by_month": {
                str(key): int(value)
                for key, value in hit_times.dt.to_period("M")
                .astype(str)
                .value_counts()
                .sort_index()
                .items()
            },
            "by_hour": {
                str(key): int(value)
                for key, value in hit_times.dt.hour.value_counts().sort_index().items()
            },
        }
        channel_id, stable_id = id_lookup.get(column, (-1, ""))
        for pos in indices:
            mask_records.append(
                {
                    "row_index": int(pos),
                    "date": str(time.iloc[int(pos)]),
                    "channel_id": channel_id,
                    "stable_channel_id": stable_id,
                    "original_column": column,
                    "original_value": sentinel_values[0],
                    "masked_value": "",
                    "rule": "sentinel_to_NA__no_imputation__no_zero_fill",
                    "evidence_status": UNKNOWN_STATUS,
                }
            )

    mask_records.sort(key=lambda record: (record["row_index"], record["channel_id"]))
    affected_rows = sorted({record["row_index"] for record in mask_records})
    return {
        "sentinel_values": list(sentinel_values),
        "total_cells": len(mask_records),
        "n_affected_rows": len(affected_rows),
        "affected_rows": affected_rows,
        "affected_columns": sorted(by_column),
        "by_column": by_column,
        "mask_records": mask_records,
        "evidence_status": UNKNOWN_STATUS,
        "evidence_note": "工作区内无官方 dataset card / 缺失值编码说明；公开检索亦未核验；"
        "仅本项目 Stage 0 将其记为『疑似哨兵值』，未确认其是否为缺失标记",
    }


def investigate_timeline(
    frame: pd.DataFrame, time_column: str, expected_frequency: str
) -> dict[str, Any]:
    """定位重复时间戳全部记录、逐变量一致性，以及时间缺口与缺失时间片。"""
    time = pd.to_datetime(frame[time_column], errors="coerce")
    variables = [col for col in frame.columns if col != time_column]
    delta = pd.Timedelta(expected_frequency)

    duplicate_groups = []
    duplicate_mask = time.duplicated(keep=False)
    for stamp, group in frame.loc[duplicate_mask].groupby(time_column, sort=True):
        per_column = [int(group[col].nunique(dropna=False) <= 1) for col in variables]
        duplicate_groups.append(
            {
                "timestamp": str(stamp),
                "row_indices": [int(idx) for idx in group.index],
                "n_rows": int(len(group)),
                "n_variables": len(variables),
                "n_variables_identical": int(sum(per_column)),
                "all_variables_identical": bool(sum(per_column) == len(variables)),
                "first_row_values": {
                    col: group[col].iloc[0] for col in variables
                },
            }
        )

    diffs = time.diff()
    gaps = []
    gap_positions = np.flatnonzero((diffs > delta).to_numpy())
    for pos in gap_positions:
        previous, current = time.iloc[int(pos) - 1], time.iloc[int(pos)]
        step = diffs.iloc[int(pos)]
        missing_slots = [
            str(previous + k * delta)
            for k in range(1, int(step / delta))
        ]
        gaps.append(
            {
                "from": str(previous),
                "to": str(current),
                "interval": str(step),
                "from_row": int(pos) - 1,
                "to_row": int(pos),
                "missing_slots": missing_slots,
                "n_missing_slots": len(missing_slots),
                "before_values": {
                    col: frame[col].iloc[int(pos) - 1] for col in variables
                },
                "after_values": {
                    col: frame[col].iloc[int(pos)] for col in variables
                },
                "context_rows": [int(i) for i in range(int(pos) - 3, int(pos) + 3)],
            }
        )

    expected_slots = int((time.max() - time.min()) / delta) + 1
    return {
        "expected_frequency": expected_frequency,
        "n_rows": int(len(frame)),
        "n_variables": len(variables),
        "time_min": str(time.min()),
        "time_max": str(time.max()),
        "duplicate_groups": duplicate_groups,
        "n_duplicate_rows": sum(group["n_rows"] - 1 for group in duplicate_groups),
        "gaps": gaps,
        "expected_slots": expected_slots,
        "n_missing_timestamps": expected_slots - int(time.nunique()),
    }


def timeline_issue_rows(timeline: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for group in timeline["duplicate_groups"]:
        rows.append(
            {
                "issue_type": "duplicate_timestamp",
                "timestamp_or_interval": group["timestamp"],
                "row_indices": ";".join(str(i) for i in group["row_indices"]),
                "n_rows": group["n_rows"],
                "n_variables": group["n_variables"],
                "n_variables_identical": group["n_variables_identical"],
                "all_variables_identical": group["all_variables_identical"],
                "interval": "0 days 00:00:00",
                "missing_slots": 0,
                "detail": "NOT REMOVED — 候选数据完整保留全部记录",
            }
        )
    for gap in timeline["gaps"]:
        rows.append(
            {
                "issue_type": "time_gap",
                "timestamp_or_interval": f"{gap['from']} -> {gap['to']}",
                "row_indices": f"{gap['from_row']};{gap['to_row']}",
                "n_rows": 2,
                "n_variables": "",
                "n_variables_identical": "",
                "all_variables_identical": "",
                "interval": gap["interval"],
                "missing_slots": gap["n_missing_slots"],
                "detail": "NOT RESAMPLED / NOT INTERPOLATED — 保留原始时间轴",
            }
        )
        for slot in gap["missing_slots"]:
            rows.append(
                {
                    "issue_type": "missing_timestamp",
                    "timestamp_or_interval": slot,
                    "row_indices": "",
                    "n_rows": 0,
                    "n_variables": "",
                    "n_variables_identical": "",
                    "all_variables_identical": "",
                    "interval": gap["interval"],
                    "missing_slots": 1,
                    "detail": "仅登记，未补齐任何行",
                }
            )
    return rows


def apply_sentinel_mask(
    frame: pd.DataFrame, mask_records: Sequence[dict[str, Any]]
) -> pd.DataFrame:
    """把哨兵单元格写为空值（NaN）；不插值、不填 0、不删行、不改名、不动时间戳。"""
    masked = frame.copy(deep=True)
    column_positions = {column: index for index, column in enumerate(frame.columns)}
    for record in mask_records:
        masked.iat[
            int(record["row_index"]), column_positions[record["original_column"]]
        ] = np.nan
    return masked


def write_candidate_csv(frame: pd.DataFrame, path: str) -> tuple:
    """写入候选 CSV，绝不覆盖已有文件，返回 (路径, 行数, 列数, 字节数, SHA256)。"""
    target = io_utils.unique_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(target, index=False, encoding="utf-8", na_rep="")
    digest = io_utils.sha256_file(target)
    return target, int(len(frame)), int(len(frame.columns)), target.stat().st_size, digest


def build_decision_rows(
    mapping_rows: Sequence[dict[str, Any]],
    sentinels: dict[str, Any],
    timeline: dict[str, Any],
) -> list[dict[str, Any]]:
    damaged = [row for row in mapping_rows if row["status"] == UNKNOWN_STATUS]
    duplicate = timeline["duplicate_groups"]
    gap = timeline["gaps"]
    duplicate_desc = (
        "; ".join(
            f"{group['timestamp']} x{group['n_rows']} (rows "
            f"{','.join(str(i) for i in group['row_indices'])}, "
            f"21/21 变量一致={group['all_variables_identical']})"
            for group in duplicate
        )
        or "无"
    )
    gap_desc = (
        "; ".join(
            f"{item['from']} -> {item['to']} ({item['interval']}, "
            f"缺 {item['n_missing_slots']} 个时间片)"
            for item in gap
        )
        or "无"
    )
    common_action = (
        "未删除、未插值、未重采样、未重命名、未替换原值；仅生成候选版本与掩码/映射记录"
    )

    definitions = (
        (
            "D01",
            "三个含 U+FFFD 的列名是否规范化",
            f"{len(damaged)} 个列名含 U+FFFD；所有本地副本（3 宽表 / 2 长表）同样损坏；"
            "工作区唯一未损坏式写法为脚本硬编码 ASCII 近似，无 provenance",
            "data/metadata/channel_name_mapping.csv ; " + ASCII_APPROXIMATION_SOURCE + ":68-70",
            "无法确认（所有副本均损坏；公开来源未核验）",
            "A 保留原始列名 + 稳定 ID（当前候选）; B 采用工作区 ASCII 近似名（低置信度）; "
            "C 人工提供官方 dataset card / 未损坏表头后再确定规范名",
            "不改变时间轴；但若按列名匹配通道，3 个通道可能丢失，导致窗口张量通道数与顺序不一致",
            "不改变时间轴；但 3 个通道若匹配失败，其通道对的滞后相关无法计算",
        ),
        (
            "D02",
            "-9999 是否为缺失值标记、是否应用掩码",
            f"共 {sentinels['total_cells']} 个单元格，涉及 {sentinels['n_affected_rows']} 行、"
            f"{len(sentinels['affected_columns'])} 个变量："
            f"{', '.join(sentinels['affected_columns'])}；呈连续段分布",
            "reports/weather_data_check.md ; 工作区与公开来源均无缺失值编码说明",
            "无法确认（无官方/原始来源说明）",
            "A 视为缺失并掩码为 NaN（候选 masked 版本，不插值）; B 保留原值（候选 raw 版本）; "
            "C 视为异常值另定稳健统计规则",
            "未掩码时极端值进入窗口会污染归一化与协方差；掩码后窗口内出现 NaN，需显式 mask",
            "未掩码的 -9999 会显著扭曲 Pearson 协方差（尤其 OT 的连续 34 点）；"
            "掩码后需 pairwise-complete 或掩码相关，连续段会减少局部样本",
        ),
        (
            "D03",
            "重复时间戳如何处理",
            f"{duplicate_desc}；合计 {timeline['n_duplicate_rows']} 条冗余记录",
            "data/processed/weather_stage1_timeline_issues.csv ; data/raw/Weather.csv",
            "事实已确认（2 行 21 变量完全一致），但处理策略待决策",
            "A 保留两行（当前候选）; B 保留首行; C 保留末行; D 人工核验后合并",
            "保留时出现 0 分钟跨度的窗口，窗口与实际物理时长不再一一对应；去重改变行索引",
            "保留时 lag-1 在该处实际为 0 分钟，产生虚假的完全相关；去重可消除但需维护索引映射",
        ),
        (
            "D04",
            "2020-05-29 时间缺口如何处理",
            f"{gap_desc}；预计应有 {timeline['expected_slots']} 个时间片，"
            f"缺 {timeline['n_missing_timestamps']} 个",
            "data/processed/weather_stage1_timeline_issues.csv ; data/raw/Weather.csv",
            "事实已确认，但处理策略待决策",
            "A 保留原始时间轴（当前候选）; B 补齐 9 个时间片为 NaN，不插值; "
            "C 在缺口处切段，窗口不跨越缺口; D 重采样/插值（本阶段不执行）",
            "保留时跨缺口窗口实际跨 100 分钟；补齐可保证等间隔但引入全 NaN 窗口；"
            "切段保证窗口内等间隔但损失少量样本",
            "保留时跨缺口 lag-1 实为 100 分钟，系统性扭曲高频通道相关；"
            "补齐后 NaN 需掩码相关；切段最安全但样本量略减",
        ),
        (
            "D05",
            "最终规范化版本的选择与生成时机",
            "当前只有候选 A（原值）与候选 B（masked），两者行数/列数/时间轴完全相同，"
            "仅 81 个单元格不同",
            "data/processed/processed_manifest.csv",
            "待决策（本阶段不生成最终版本）",
            "A 采用原值候选; B 采用 masked 候选; C 待 D01–D04 全部确认后再生成最终版本",
            "决定窗口内是否含 NaN 及 -9999 极值，直接影响窗口特征与归一化",
            "决定相关系数计算采用 complete-case 还是含极值样本",
        ),
        (
            "D06",
            "下游使用哪套通道标识",
            f"已为 21 个通道分配稳定 ID（{mapping_rows[0]['stable_channel_id']} ~ "
            f"{mapping_rows[-1]['stable_channel_id']}）",
            "data/metadata/channel_name_mapping.csv",
            "待决策",
            "A 使用原始列名; B 使用稳定 ID; C 使用人工确认后的规范名",
            "影响通道索引与矩阵行列顺序的一致性；稳定 ID 不受编码损伤影响",
            "影响通道对 (i,j) 的标识与后续语义/动态矩阵的对齐",
        ),
    )
    return [
        {
            "decision_id": item[0],
            "topic": item[1],
            "observed_facts": item[2],
            "evidence_source": item[3],
            "evidence_status": item[4],
            "options": item[5],
            "project_action_taken": common_action,
            "impact_on_sliding_window": item[6],
            "impact_on_lagged_correlation": item[7],
            "status": UNKNOWN_STATUS,
            "needs_human_decision": "yes",
        }
        for item in definitions
    ]


def render_report(ctx: dict[str, Any]) -> str:
    """把调查事实、处理规则、修改统计、方案影响与待决策项渲染为 Markdown。"""
    sentinels = ctx["sentinels"]
    timeline = ctx["timeline"]
    verification = ctx["verification"]
    mapping = ctx["mapping"]
    candidates = ctx["candidates"]
    damaged = [row for row in mapping if row["status"] == UNKNOWN_STATUS]

    lines = [
        "# Weather 数据规范化报告（Stage 1）",
        "",
        f"> 状态：**{ctx['stage_status']}**。本文与 `data/processed/` 下的文件都是**候选方案，不是最终版本**；"
        "任何清洗策略均等待人工确认。",
        f"> 生成时间：{ctx['generated_at']}；配置：`configs/experiment.yaml`；"
        f"随机种子：{ctx['seed']}（本阶段无随机操作）。",
        "",
        "## 0. 本阶段边界",
        "",
        "- 只处理数据质量事实调查与可追溯性；不构建语义/动态关系矩阵，不训练模型，不生成通道描述。",
        "- 不修改 `data/raw/` 任何文件；不删除、不插值、不重采样、不重命名原始列、不把 -9999 填成 0。",
        "- 无法确认的事项一律标记 Unknown，交由人工决策。",
        "",
        "## 1. 原始数据保护与 SHA256",
        "",
        "| 原始文件 | 处理前 SHA256 | 处理后 SHA256 | 是否一致 |",
        "|---|---|---|---|",
        f"| `{ctx['raw_path']}` | `{ctx['raw_before']}` | `{ctx['raw_after']}` | "
        f"**{ctx['raw_before'] == ctx['raw_after']}** |",
        f"| `{ctx['long_path']}` | `{ctx['long_before']}` | `{ctx['long_after']}` | "
        f"**{ctx['long_before'] == ctx['long_after']}** |",
        "",
        "全部候选产物写入独立目录 `data/processed/`；`data/raw/` 仅以只读方式打开。",
        "",
        "## 2. 列名规范化",
        "",
        "### 2.1 调查渠道与结果",
        "",
        "| 渠道 | 位置 | 结果 |",
        "|---|---|---|",
    ]
    lines += [
        f"| {name} | `{paths}` | {result} |"
        for name, paths, result in EVIDENCE_CHANNELS
    ]
    lines += [
        "",
        "### 2.2 结论",
        "",
        f"- 21 个通道中 18 个列名不含 U+FFFD，直接来自表头（置信度 high）；"
        f"{len(damaged)} 个含 U+FFFD，编码损伤不可逆，工作区内所有副本同样损坏。",
        "- 唯一「未损坏式」写法是另一项目脚本中硬编码的 ASCII 近似键，无 provenance，"
        "且与原表头字面不匹配（这正是其语义描述退化为列名本身的原因）。",
        "- 公开来源检索只得到通用列名与 ASCII 近似，未给出可核验的含 Unicode ²/µ 的原始表头，"
        "也未发现该 CSV 副本的原始编码说明。",
        f"- **结论：无法确认 → 状态 `{UNKNOWN_STATUS}`**。保留原始列名（含 U+FFFD），"
        "为全部 21 个通道分配与列顺序绑定的稳定临时 ID `CH_00` ~ `CH_20`。",
        "- 候选名只记录在映射表 `candidate_name` 列（引用，置信度 low），**未应用到任何输出文件**。",
        "",
        "### 2.3 三个损坏列的映射记录",
        "",
        "| channel_id | 原始列名（含 U+FFFD） | 稳定 ID | 候选名（未应用） | 证据来源 | 置信度 | 状态 |",
        "|---:|---|---|---|---|---|---|",
    ]
    for row in damaged:
        lines.append(
            f"| {row['channel_id']} | `{row['original_column']}` | `{row['stable_channel_id']}` | "
            f"`{row['candidate_name']}` | `{row['evidence_source']}` | {row['confidence']} | "
            f"{row['status']} |"
        )
    lines += [
        "",
        f"完整 21 行映射（含 18 个已确认列）见 `data/metadata/channel_name_mapping.csv`。"
        "原始列名与规范列名一一对应，`canonical_name` 对 3 个损坏列留空表示 Unknown。",
        "",
        "## 3. -9999 哨兵值调查",
        "",
        f"- 合计 **{sentinels['total_cells']} 个单元格**，涉及 "
        f"**{sentinels['n_affected_rows']} 行**、"
        f"**{len(sentinels['affected_columns'])} 个变量**。",
        f"- 来源结论：**{sentinels['evidence_status']}**。{sentinels['evidence_note']}。",
        "",
        "### 3.1 按变量统计（位置与连续性）",
        "",
        "| 变量 | 稳定 ID | 数量 | 行索引 | 时间范围 | 连续段 | 最长段 |",
        "|---|---|---:|---|---|---|---:|",
    ]
    id_lookup = {
        row["original_column"]: row["stable_channel_id"] for row in mapping
    }
    for column, info in sentinels["by_column"].items():
        runs_text = "; ".join(
            f"{run['start_row']}-{run['end_row']} (n={run['length']})" for run in info["runs"]
        )
        lines.append(
            f"| `{column}` | `{id_lookup.get(column, '')}` | {info['count']} | "
            f"{', '.join(str(i) for i in info['row_indices'])} | "
            f"{info['time_min']} ~ {info['time_max']} | {runs_text} | {info['max_run_length']} |"
        )
    lines += [
        "",
        "### 3.2 时间分布",
        "",
        "| 变量 | 按月份 | 按小时 |",
        "|---|---|---|",
    ]
    for column, info in sentinels["by_column"].items():
        lines.append(
            f"| `{column}` | {json.dumps(info['by_month'], ensure_ascii=False)} | "
            f"{json.dumps(info['by_hour'], ensure_ascii=False)} |"
        )
    lines += [
        "",
        "观察（仅陈述事实，不作为语义确认）：`OT` 的 50 个值集中在两段连续区间；"
        "`max. PAR (...)` 的 30 个值呈多段短连续、集中在白天时段；"
        "`wv (m/s)` 的唯一 1 个值落在 `OT` 第一段内。该模式与仪器/记录故障一致，"
        "但**没有任何来源文件把它定义为缺失标记**，因此仍标记 Unknown。",
        "",
        "### 3.3 掩码方案（候选，不代表确认）",
        "",
        f"- 掩码记录 `{sentinels['total_cells']}` 条，逐条列出行索引、时间、通道、原值，"
        "见 `data/processed/weather_stage1_missing_mask.csv`。",
        "- 规则：`sentinel_to_NA__no_imputation__no_zero_fill` "
        "—— 把哨兵单元格写成 CSV 空值（NaN），**不插值、不填 0、不删行、不改时间戳、不改名**。",
        "- 因来源无法确认，同时提供候选 A（保留原值）与候选 B（masked），供后续比较；"
        "两者行数、列数、时间轴完全相同。",
        "",
        "## 4. 重复时间戳",
        "",
        "| 时间戳 | 全部记录行索引 | 行数 | 变量数 | 取值完全一致的变量数 | 21 变量是否完全一致 |",
        "|---|---|---:|---:|---:|---|",
    ]
    for group in timeline["duplicate_groups"]:
        lines.append(
            f"| {group['timestamp']} | {', '.join(str(i) for i in group['row_indices'])} | "
            f"{group['n_rows']} | {group['n_variables']} | {group['n_variables_identical']} | "
            f"**{group['all_variables_identical']}** |"
        )
    lines += [
        "",
        "- 重复时间戳的全部记录即上表两行；21 个变量逐列比对**完全一致**（含所有浮点值），"
        "属于完整重复行。",
        "- **未删除、未合并、未改值**；两个候选版本均完整保留 52,696 行。",
        "",
        "## 5. 2020-05-29 时间缺口详细检查",
        "",
    ]
    for gap in timeline["gaps"]:
        lines += [
            f"- 区间：`{gap['from']}` → `{gap['to']}`，间隔 `{gap['interval']}`"
            f"（行 {gap['from_row']} → {gap['to_row']}），缺 "
            f"**{gap['n_missing_slots']} 个 10 min 时间片**。",
            "- 缺失时间点：" + ", ".join(f"`{slot}`" for slot in gap["missing_slots"]) + "。",
            "",
            "缺口前后关键变量对比（原始值，未插值）：",
            "",
            "| 变量 | 缺口前 | 缺口后 |",
            "|---|---:|---:|",
        ]
        for column in (
            "T (degC)",
            "Tpot (K)",
            "rh (%)",
            "wv (m/s)",
            "wd (deg)",
            "SWDR (W/m\ufffd)",
            "PAR (\ufffdmol/m\ufffd/s)",
            "Tlog (degC)",
            "OT",
        ):
            before = gap["before_values"].get(column, "n/a")
            after = gap["after_values"].get(column, "n/a")
            lines.append(f"| `{column}` | {before} | {after} |")
    lines += [
        "",
        f"- 全表仅此 1 处超过 10 min 的间隔；应有 {timeline['expected_slots']} 个时间片，"
        f"实际唯一时间戳 {timeline['n_rows'] - timeline['n_duplicate_rows']} 个，"
        f"缺 {timeline['n_missing_timestamps']} 个。",
        "- 缺口前后温度、湿度、辐射等量有明显变化，说明中间 100 分钟内发生了真实变化，"
        "**不能据此简单插值**；本项目未重采样、未补齐、未删除任何行。",
        "",
        "## 6. 候选数据、处理规则、修改行数与影响变量",
        "",
        "| 候选文件 | 处理规则 | 修改单元格 | 修改行数 | 影响变量 | 行数 | 列数 | SHA256 | 状态 |",
        "|---|---|---:|---:|---|---:|---:|---|---|",
    ]
    for item in candidates:
        lines.append(
            f"| `{item['path']}` | {item['rules']} | {item['modified_cells']} | "
            f"{item['modified_rows']} | {item['affected_columns'] or '无'} | "
            f"{item['rows']} | {item['columns']} | `{item['sha256']}` | {item['status']} |"
        )
    lines += [
        "",
        "规则明细：",
        "",
        "- 候选 A（原值）：逐字复制 `data/raw/Weather.csv`，修改 0 个单元格、0 行、影响 0 个变量；"
        "列名、行序、时间戳、值全部保持原样；其 SHA256 与原始文件完全相同（字节级一致）。",
        f"- 候选 B（masked）：仅把 {sentinels['total_cells']} 个 -9999 写成空值（NaN），"
        f"修改 {sentinels['n_affected_rows']} 行、"
        f"影响 {len(sentinels['affected_columns'])} 个变量"
        f"（{', '.join(sentinels['affected_columns'])}）；"
        "未插值、未填 0、未删行、未改时间戳、未重命名列。",
        "- 时间轴相关规则：重复时间戳 0 行被删除，缺口 0 个时间片被补齐，0 次重采样。",
        "- 两个候选都不是最终版本；最终版本须在决策清单确认后另行生成。",
        "",
        "### 6.1 实际运行验证",
        "",
        "| 校验项 | 结果 |",
        "|---|---|",
    ]
    lines += [f"| {key} | **{value}** |" for key, value in verification.items()]
    lines += [
        "",
        "## 7. 可选处理方案及其对滑动窗口 / 滞后相关计算的影响",
        "",
        "> 以下仅为分析，本项目**未执行**任何一项（除「保留原样」这一当前候选状态）。",
        "",
        "| 方案 | 做法 | 行数变化 | 对滑动窗口 | 对滞后相关 |",
        "|---|---|---|---|---|",
        "| A 保留原始时间轴（当前候选） | 不去重、不补齐 | 52,696 不变 | "
        "绝大多数窗口为 10 min×W；跨 2020-05-29 缺口的窗口实际跨 100 分钟，"
        "跨 2020-05-12 重复行的窗口跨 0 分钟，同一窗口超参数对应不同真实时长 | "
        "lag-k 不再等于 10k 分钟：缺口处 lag-1 实为 100 分钟，重复处实为 0 分钟，"
        "会系统性扭曲高频通道（辐射类）的相关估计 |",
        "| B 仅去重（保留首条） | 删去 1 条完全重复行 | 52,696 → 52,695 | "
        "消除 0 分钟窗口；缺口问题仍在；行索引与原记录产生偏移，需维护索引映射 | "
        "消除虚假的完全自相关点；跨缺口 lag 仍为 100 分钟 |",
        "| C 补齐时间轴并留空 | 插入 9 个 NaN 时间片（不插值） | 52,696 → 52,705（含去重则 52,704） | "
        "时间步严格 10 min；但出现全 NaN 窗口，训练/统计必须显式使用掩码 | "
        "lag-k 恢复为 10k 分钟；NaN 需 pairwise-complete 或掩码相关，"
        "缺口附近样本量下降 |",
        "| D 缺口处切段 | 在缺口处切断序列，窗口不跨越 | 总行数不变，序列数 +1 | "
        "保证每个窗口内部严格等间隔，无需插入 NaN；损失跨缺口处的少量窗口样本 | "
        "不产生跨 100 分钟的 lag 对，估计最干净；需分段索引与分段统计 |",
        "| E 重采样 / 插值 | 人为补齐数值 | 视规则而定 | "
        "窗口等间隔且无 NaN，但引入非观测值，掩盖真实缺口与突变 | "
        "会制造平滑的虚假连续变化，可能高估相邻通道相关；本阶段明确不执行 |",
        "",
        "### 7.1 哨兵值是否掩码的影响",
        "",
        "- **滑动窗口**：保留原值时 `-9999` 作为极端负值与正常量级（如 `OT` 约 400）同窗，"
        "会主导窗口内归一化/标准化与协方差；掩码后窗口出现 NaN，需 mask-aware 的窗口统计，"
        "但不会引入虚假极值。",
        "- **滞后相关**：81 个点中 `OT` 有连续 34 点、`max. PAR` 多在白天短连续段。"
        "未掩码的极端值会显著改变 Pearson 协方差，可能产生虚假强相关或反相关；"
        "掩码后应采用 pairwise-complete / 掩码相关，代价是这些时间段的局部样本减少。",
        "- 由于 -9999 的语义为 Unknown，**两种候选必须并行保留**，由人工确认后再选其一。",
        "",
        "## 8. 输出清单",
        "",
        "| 文件 | 用途 |",
        "|---|---|",
    ]
    lines += [f"| `{item['path']}` | {item['purpose']} |" for item in ctx["outputs"]]
    lines += [
        "",
        "## 9. 待人工确认的决策清单",
        "",
        "| ID | 议题 | 证据状态 | 可选方案 | 状态 |",
        "|---|---|---|---|---|",
    ]
    for row in ctx["decisions"]:
        lines.append(
            f"| {row['decision_id']} | {row['topic']} | {row['evidence_status']} | "
            f"{row['options']} | {row['status']} |"
        )
    lines += [
        "",
        "完整字段（含事实、证据来源、本项目已执行动作、对滑动窗口/滞后相关的影响）"
        "见 `data/metadata/data_cleaning_decisions.csv`。",
        "",
        "## 10. 明确未执行",
        "",
        "- 未修改 `data/raw/` 下任何原始文件，未修改 BEDTime 或其他项目；",
        "- 未删除重复行、未补齐或重采样时间轴、未插值、未把 -9999 替换为 0 或其他值；",
        "- 未把任何候选规范列名应用到数据文件，未生成通道语义描述；",
        "- 未构建语义关系矩阵、动态关系矩阵，未训练模型，未安装或升级任何依赖；",
        "- 未生成「最终规范化版本」——规则确认前，两个候选版本均标记为非最终。",
        "",
    ]
    return "\n".join(lines)
