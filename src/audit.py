"""Weather 数据集的第一阶段只读审计：规模、列、缺失、重复、异常与时间完整性。"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pandas as pd

from . import io_utils

REPLACEMENT_CHAR = "\ufffd"


def read_header(path: str | Path, encoding: str = "utf-8") -> list[str]:
    """从原始 CSV 逐字读取表头，不经 pandas 列名清洗。"""
    with Path(path).open("r", encoding=encoding, newline="") as handle:
        return next(csv.reader(handle))


def load_weather(path: str | Path, encoding: str = "utf-8") -> pd.DataFrame:
    return pd.read_csv(Path(path), encoding=encoding, low_memory=False)


def audit_dataframe(
    df: pd.DataFrame,
    time_column: str,
    expected_frequency: str = "10min",
    iqr_multiplier: float = 1.5,
    sentinel_values: Sequence[float] = (-9999,),
) -> dict[str, Any]:
    if time_column not in df.columns:
        raise KeyError(f"时间列 {time_column!r} 不存在于数据表: {list(df.columns)}")

    columns = list(df.columns)
    variables = [col for col in columns if col != time_column]
    n_rows = len(df)

    # ---- 时间列 ----
    time = pd.to_datetime(df[time_column], errors="coerce")
    time_valid = time.dropna()
    sorted_time = time_valid.sort_values().reset_index(drop=True)
    full_diffs = sorted_time.diff()
    diffs = full_diffs.dropna()
    expected_delta = pd.Timedelta(expected_frequency)
    interval_counts = diffs.value_counts()
    expected_slots = (
        int((time_valid.max() - time_valid.min()) / expected_delta) + 1
        if len(time_valid) > 0
        else 0
    )
    irregular_mask = full_diffs.notna() & full_diffs.ne(expected_delta)
    irregular_intervals = [
        {
            "from": str(sorted_time.iloc[pos - 1]),
            "to": str(sorted_time.iloc[pos]),
            "interval": str(full_diffs.iloc[pos]),
        }
        for pos in np.flatnonzero(irregular_mask.to_numpy())[:10]
        if pos >= 1
    ]
    duplicated_values = [
        str(value) for value in sorted_time[sorted_time.duplicated()].unique()[:10]
    ]
    time_info = {
        "column": time_column,
        "dtype": str(df[time_column].dtype),
        "unparsable": int(time.isna().sum()),
        "min": str(time_valid.min()) if len(time_valid) else "",
        "max": str(time_valid.max()) if len(time_valid) else "",
        "monotonic_increasing": bool(time_valid.is_monotonic_increasing),
        "duplicate_timestamps": int(time_valid.duplicated().sum()),
        "duplicate_timestamp_values": duplicated_values,
        "most_common_interval": str(interval_counts.index[0]) if len(interval_counts) else "",
        "most_common_interval_count": int(interval_counts.iloc[0]) if len(interval_counts) else 0,
        "expected_interval": str(expected_delta),
        "intervals_not_matching_expected": int(irregular_mask.sum()),
        "irregular_intervals": irregular_intervals,
        "expected_slots": expected_slots,
        "missing_timestamps": expected_slots - int(time_valid.nunique()),
    }

    # ---- 变量列 ----
    variable_rows: list[dict[str, Any]] = []
    numeric_missing_total = 0
    infinite_total = 0
    outlier_total = 0
    sentinel_total = 0
    for col in variables:
        numeric = pd.to_numeric(df[col], errors="coerce")
        values = numeric.to_numpy(dtype="float64")
        finite = values[np.isfinite(values)]
        raw_missing = int(df[col].isna().sum())
        numeric_missing = int(numeric.isna().sum())
        unparsable = numeric_missing - raw_missing
        n_unique = int(numeric.nunique(dropna=True))
        is_constant = n_unique <= 1

        q1 = float(np.percentile(finite, 25)) if finite.size else float("nan")
        q3 = float(np.percentile(finite, 75)) if finite.size else float("nan")
        iqr = q3 - q1
        low = q1 - iqr_multiplier * iqr
        high = q3 + iqr_multiplier * iqr
        if finite.size and np.isfinite(low) and np.isfinite(high):
            n_outliers = int(((values < low) | (values > high)).sum())
        else:
            n_outliers = 0
        n_infinite = int(np.isinf(values).sum())
        sentinel_count = (
            int(np.isin(values, list(sentinel_values)).sum()) if len(sentinel_values) else 0
        )
        sentinel_total += sentinel_count

        valid = (numeric_missing < n_rows) and (not is_constant) and (unparsable == 0)
        if not valid:
            reason = []
            if numeric_missing == n_rows:
                reason.append("全列缺失")
            if is_constant:
                reason.append("常量列")
            if unparsable > 0:
                reason.append(f"存在 {unparsable} 个不可解析数值")
            invalid_reason = "; ".join(reason)
        else:
            invalid_reason = ""

        variable_rows.append(
            {
                "channel_id": len(variable_rows),
                "channel_name": col,
                "dtype": str(df[col].dtype),
                "valid": valid,
                "invalid_reason": invalid_reason,
                "missing": numeric_missing,
                "unparsable_numeric": unparsable,
                "infinite": n_infinite,
                "sentinel_count": sentinel_count,
                "n_unique": n_unique,
                "is_constant": is_constant,
                "all_zero": bool(finite.size and np.all(finite == 0)),
                "min": float(finite.min()) if finite.size else float("nan"),
                "q1": q1,
                "median": float(np.percentile(finite, 50)) if finite.size else float("nan"),
                "q3": q3,
                "max": float(finite.max()) if finite.size else float("nan"),
                "mean": float(finite.mean()) if finite.size else float("nan"),
                "std": float(finite.std(ddof=1)) if finite.size > 1 else float("nan"),
                "iqr": iqr,
                "iqr_lower_fence": low,
                "iqr_upper_fence": high,
                "iqr_outliers": n_outliers,
                "iqr_zero": bool(finite.size and iqr == 0),
            }
        )
        numeric_missing_total += numeric_missing
        infinite_total += n_infinite
        outlier_total += n_outliers

    # ---- 重复 / 编码 / 汇总 ----
    duplicates = {
        "full_row": int(df.duplicated().sum()),
        "variable_block": int(df.duplicated(subset=variables).sum()),
        "time_column": time_info["duplicate_timestamps"],
    }
    damaged_columns = [col for col in columns if REPLACEMENT_CHAR in col]
    valid_variables = [row["channel_name"] for row in variable_rows if row["valid"]]

    result = {
        "n_rows": n_rows,
        "n_columns": len(columns),
        "columns": columns,
        "time_column": time_column,
        "variables": variables,
        "n_variables": len(variables),
        "n_valid_variables": len(valid_variables),
        "valid_variables": valid_variables,
        "invalid_variables": {
            row["channel_name"]: row["invalid_reason"]
            for row in variable_rows
            if not row["valid"]
        },
        "missing": {
            "total_cells": n_rows * len(variables),
            "total_missing": numeric_missing_total,
            "missing_ratio": numeric_missing_total / (n_rows * len(variables))
            if n_rows and variables
            else 0.0,
            "by_column": {row["channel_name"]: row["missing"] for row in variable_rows},
            "columns_with_missing": [
                row["channel_name"] for row in variable_rows if row["missing"] > 0
            ],
        },
        "duplicates": duplicates,
        "outliers": {
            "method": "IQR",
            "multiplier": iqr_multiplier,
            "total": outlier_total,
            "total_ratio": outlier_total / (n_rows * len(variables))
            if n_rows and variables
            else 0.0,
            "by_column": {row["channel_name"]: row["iqr_outliers"] for row in variable_rows},
            "iqr_zero_columns": [
                row["channel_name"] for row in variable_rows if row["iqr_zero"]
            ],
            "infinite_cells": infinite_total,
        },
        "sentinels": {
            "values": list(sentinel_values),
            "total": sentinel_total,
            "by_column": {
                row["channel_name"]: row["sentinel_count"] for row in variable_rows
            },
            "columns": [
                row["channel_name"] for row in variable_rows if row["sentinel_count"] > 0
            ],
            "note": "疑似哨兵/占位值，仅统计出现次数，不替换、不修改原始数据",
        },
        "constant_columns": [row["channel_name"] for row in variable_rows if row["is_constant"]],
        "all_zero_columns": [row["channel_name"] for row in variable_rows if row["all_zero"]],
        "time": time_info,
        "encoding_damaged_columns": damaged_columns,
        "variables_detail": variable_rows,
    }
    return result


def audit_long_format(path: str | Path, encoding: str = "utf-8") -> dict[str, Any]:
    """用 TFB 长表交叉校验通道数与每通道长度（只读）。"""
    path = Path(path)
    long_df = pd.read_csv(path, encoding=encoding, usecols=["date", "data", "cols"], low_memory=False)
    counts = long_df.groupby("cols", sort=False).size()
    return {
        "file": str(path),
        "n_rows": int(len(long_df)),
        "n_channels": int(counts.size),
        "channels": [str(name) for name in counts.index.tolist()],
        "min_rows_per_channel": int(counts.min()) if len(counts) else 0,
        "max_rows_per_channel": int(counts.max()) if len(counts) else 0,
        "all_channels_equal_length": bool(counts.nunique() == 1) if len(counts) else False,
        "data_missing": int(long_df["data"].isna().sum()),
        "date_channel_duplicates": int(long_df.duplicated(subset=["date", "cols"]).sum()),
    }


def summary_pairs(result: dict[str, Any]) -> list[tuple[str, Any]]:
    pairs: list[tuple[str, Any]] = [
        ("rows", result["n_rows"]),
        ("columns", result["n_columns"]),
        ("time_column", result["time_column"]),
        ("n_variables", result["n_variables"]),
        ("n_valid_variables", result["n_valid_variables"]),
        ("missing_cells", result["missing"]["total_missing"]),
        ("missing_ratio", round(result["missing"]["missing_ratio"], 8)),
        ("duplicate_full_rows", result["duplicates"]["full_row"]),
        ("duplicate_variable_blocks", result["duplicates"]["variable_block"]),
        ("duplicate_timestamps", result["duplicates"]["time_column"]),
        ("iqr_outliers_total", result["outliers"]["total"]),
        ("infinite_cells", result["outliers"]["infinite_cells"]),
        ("sentinel_cells", result["sentinels"]["total"]),
        ("sentinel_columns", "; ".join(result["sentinels"]["columns"])),
        ("time_unparsable", result["time"]["unparsable"]),
        ("time_min", result["time"]["min"]),
        ("time_max", result["time"]["max"]),
        ("time_most_common_interval", result["time"]["most_common_interval"]),
        ("missing_timestamps", result["time"]["missing_timestamps"]),
        ("encoding_damaged_columns", len(result["encoding_damaged_columns"])),
    ]
    if "long_format" in result:
        long_info = result["long_format"]
        pairs += [
            ("long_format_rows", long_info["n_rows"]),
            ("long_format_channels", long_info["n_channels"]),
            ("long_format_all_equal_length", long_info["all_channels_equal_length"]),
            ("long_format_date_channel_duplicates", long_info["date_channel_duplicates"]),
        ]
    return pairs


VARIABLE_FIELDS: Sequence[str] = (
    "channel_id",
    "channel_name",
    "dtype",
    "valid",
    "missing",
    "unparsable_numeric",
    "infinite",
    "sentinel_count",
    "n_unique",
    "is_constant",
    "all_zero",
    "min",
    "q1",
    "median",
    "q3",
    "max",
    "mean",
    "std",
    "iqr",
    "iqr_lower_fence",
    "iqr_upper_fence",
    "iqr_outliers",
    "iqr_zero",
)


def write_tables(result: dict[str, Any], tables_dir: str | Path) -> list[Path]:
    tables_dir = Path(tables_dir)
    summary_path = io_utils.write_csv(
        tables_dir / "weather_summary.csv", ["key", "value"], summary_pairs(result)
    )
    variable_rows = [
        [row[field] for field in VARIABLE_FIELDS] for row in result["variables_detail"]
    ]
    variables_path = io_utils.write_csv(
        tables_dir / "weather_variables.csv", list(VARIABLE_FIELDS), variable_rows
    )
    json_path = io_utils.write_json(tables_dir / "weather_audit.json", result)
    return [summary_path, variables_path, json_path]


def render_report(result: dict[str, Any], primary_file: str, config: dict[str, Any]) -> str:
    seed = config["project"]["seed"]
    lines = [
        "# Weather 数据检查报告（第一阶段）",
        "",
        f"- 主数据文件：`{primary_file}`（只读副本）",
        f"- 随机种子：{seed}（本阶段无随机采样）",
        "- 读取方式：`pandas.read_csv`，未做任何填充、删除、重采样或写回",
        "",
        "## 1. 规模与列结构",
        "",
        f"- 行数：**{result['n_rows']}**；列数：**{result['n_columns']}**",
        f"- 时间列：**{result['time_column']}**",
        f"- 变量列：**{result['n_variables']}** 个；其中有效变量 **{result['n_valid_variables']}** 个"
        "（有效 = 数值可完整解析、非全空、非常量）",
        f"- 无效变量：{result['invalid_variables'] or '无'}",
        "",
        "变量列（按文件原始顺序，保留原始字符）：",
        "",
    ]
    lines += [f"{i + 1}. `{name}`" for i, name in enumerate(result["variables"])]
    lines += [
        "",
        "## 2. 时间列",
        "",
        "| 项目 | 值 |",
        "|---|---|",
        f"| 解析失败 | {result['time']['unparsable']} |",
        f"| 起止 | {result['time']['min']} ~ {result['time']['max']} |",
        f"| 单调递增 | {result['time']['monotonic_increasing']} |",
        f"| 重复时间戳 | {result['time']['duplicate_timestamps']} |",
        f"| 最常见间隔 | {result['time']['most_common_interval']} "
        f"({result['time']['most_common_interval_count']} 次) |",
        f"| 期望间隔 | {result['time']['expected_interval']} |",
        f"| 不符合期望间隔的步数 | {result['time']['intervals_not_matching_expected']} |",
        f"| 应有时间片 / 缺失时间片 | {result['time']['expected_slots']} / "
        f"{result['time']['missing_timestamps']} |",
        "",
        f"- 重复时间戳取值：{result['time']['duplicate_timestamp_values'] or '无'}",
        f"- 不符合期望间隔的位置：{result['time']['irregular_intervals'] or '无'}",
        "",
        "## 3. 缺失值、重复值、异常值",
        "",
        f"- 缺失：变量区共 {result['missing']['total_cells']} 个单元格，"
        f"缺失 {result['missing']['total_missing']} 个 "
        f"({result['missing']['missing_ratio']:.6%})；"
        f"含缺失的列：{result['missing']['columns_with_missing'] or '无'}",
        f"- 重复：整行完全重复 {result['duplicates']['full_row']} 行；"
        f"变量区重复 {result['duplicates']['variable_block']} 行；"
        f"时间戳重复 {result['duplicates']['time_column']} 个",
        f"- 异常：IQR(×{result['outliers']['multiplier']}) 规则共 "
        f"{result['outliers']['total']} 个 "
        f"({result['outliers']['total_ratio']:.4%})；"
        f"无穷值 {result['outliers']['infinite_cells']} 个",
        f"- IQR = 0 的列（此类列的 IQR 异常统计需谨慎解释）："
        f"{result['outliers']['iqr_zero_columns'] or '无'}",
        f"- 疑似哨兵值 {result['sentinels']['values']}：共 {result['sentinels']['total']} 个单元格，"
        f"出现于 {result['sentinels']['columns'] or '无'}（{result['sentinels']['note']}）",
        f"- 常量列：{result['constant_columns'] or '无'}；全零列：{result['all_zero_columns'] or '无'}",
        "",
        "### 各变量异常值数量（IQR）",
        "",
        "| 通道 | 缺失 | IQR 异常 | 无穷值 | 疑似哨兵值 | min | max |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in result["variables_detail"]:
        lines.append(
            f"| `{row['channel_name']}` | {row['missing']} | {row['iqr_outliers']} | "
            f"{row['infinite']} | {row['sentinel_count']} | "
            f"{row['min']:.4g} | {row['max']:.4g} |"
        )
    lines += [
        "",
        "## 4. 编码与完整性提示",
        "",
        f"- 表头中含 U+FFFD 替换字符的列名（源数据既有的编码损伤，**未作修改**）："
        f"{result['encoding_damaged_columns'] or '无'}",
        "- 该损伤会使按字面匹配的通道文本描述表失效，后续阶段必须先确认通道名映射或提供带来源的描述表。",
    ]
    if "long_format" in result:
        long_info = result["long_format"]
        lines += [
            "",
            "## 5. 长表（TFB 格式）交叉校验",
            "",
            f"- 文件：`{long_info['file']}`",
            f"- 行数：{long_info['n_rows']}；通道数：{long_info['n_channels']}",
            f"- 每通道行数：min={long_info['min_rows_per_channel']}, "
            f"max={long_info['max_rows_per_channel']}；"
            f"是否全部一致：{long_info['all_channels_equal_length']}",
            f"- `data` 缺失：{long_info['data_missing']}；"
            f"(date, cols) 重复：{long_info['date_channel_duplicates']}",
        ]
    lines += [
        "",
        "## 结论",
        "",
        "- 本阶段仅完成读取与质量审计；未计算语义关系矩阵、未计算动态关系矩阵、未训练模型。",
        "- 原始数据保持只读；所有统计结果归档在 `results/tables/`，日志归档在 `logs/`。",
        "",
    ]
    return "\n".join(lines)
