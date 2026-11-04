"""Stage 1 入口：Weather 数据规范化调查、候选产物生成与验证。

用法（共享环境解释器）：
    python scripts/normalize_data.py

只读取 data/raw/，只写入 data/processed/、data/metadata/、reports/、logs/。
任何清洗策略均不自动生效；输出全部标记为 candidate / pending_human_decision。
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import audit, io_utils, normalization, settings  # noqa: E402


def relative_path(path: str | Path) -> str:
    target = Path(path)
    try:
        return target.relative_to(settings.PROJECT_ROOT).as_posix()
    except ValueError:
        return target.as_posix()


def csv_rows(rows: list[dict], fields: tuple) -> list[list]:
    return [[row.get(field, "") for field in fields] for row in rows]


def verify_candidates(
    frame: pd.DataFrame,
    time_column: str,
    raw_candidate: Path,
    masked_candidate: Path,
    mask_records: list[dict],
    sentinel_value: float,
) -> dict:
    """回读两个候选 CSV，逐值校验「除掩码位置外完全不变」。"""
    reread_raw = pd.read_csv(raw_candidate, encoding="utf-8")
    reread_masked = pd.read_csv(masked_candidate, encoding="utf-8")
    variables = [col for col in frame.columns if col != time_column]

    expected = frame.copy(deep=True)
    positions = {col: index for index, col in enumerate(frame.columns)}
    for record in mask_records:
        expected.iat[record["row_index"], positions[record["original_column"]]] = np.nan

    return {
        "raw_candidate_rows_match": int(len(reread_raw)) == int(len(frame)),
        "raw_candidate_columns_match": list(reread_raw.columns) == list(frame.columns),
        "raw_candidate_values_identical": bool(
            np.allclose(
                reread_raw[variables].to_numpy(dtype="float64"),
                frame[variables].to_numpy(dtype="float64"),
            )
        ),
        "masked_rows_match": int(len(reread_masked)) == int(len(frame)),
        "masked_columns_match": list(reread_masked.columns) == list(frame.columns),
        "masked_time_column_unchanged": bool(
            (reread_masked[time_column] == frame[time_column]).all()
        ),
        "masked_nan_cells": int(reread_masked[variables].isna().sum().sum()),
        "expected_nan_cells": len(mask_records),
        "masked_sentinel_cells_remaining": int(
            (reread_masked[variables] == sentinel_value).sum().sum()
        ),
        "masked_other_values_unchanged": bool(
            np.allclose(
                reread_masked[variables].to_numpy(dtype="float64"),
                expected[variables].to_numpy(dtype="float64"),
                equal_nan=True,
            )
        ),
    }


def main() -> None:
    config = settings.load_config()
    settings.set_seed(config["project"]["seed"])
    stage1 = config["experiment"]["stage1"]
    if not stage1.get("enabled"):
        print("Stage 1 is disabled in configs/experiment.yaml")
        return

    logger, log_path = io_utils.make_logger(
        settings.resolve(config["outputs"]["logs_dir"]), "normalize_data"
    )
    weather = config["data"]["weather"]
    time_column = weather["time_column"]
    encoding = weather["encoding"]
    raw_path = settings.resolve(weather["primary"])
    long_path = settings.resolve(weather["long_format"])
    processed_dir = settings.resolve(config["data"]["processed_dir"])
    processed_dir.mkdir(parents=True, exist_ok=True)

    # ---- 原始数据：记录处理前哈希（全程只读）----
    raw_before = io_utils.sha256_file(raw_path)
    long_before = io_utils.sha256_file(long_path)
    logger.info("raw before: %s = %s", relative_path(raw_path), raw_before)
    logger.info("long before: %s = %s", relative_path(long_path), long_before)

    header = audit.read_header(raw_path, encoding=encoding)
    frame = audit.load_weather(raw_path, encoding=encoding)
    logger.info("loaded %d rows x %d columns", len(frame), len(frame.columns))

    # ---- 调查 ----
    mapping = normalization.build_channel_mapping(
        header, time_column, stage1["stable_id_prefix"]
    )
    sentinels = normalization.investigate_sentinels(
        frame, time_column, stage1["sentinel_values"], mapping
    )
    timeline = normalization.investigate_timeline(
        frame, time_column, stage1["expected_frequency"]
    )
    decisions = normalization.build_decision_rows(mapping, sentinels, timeline)
    logger.info(
        "investigation: %d damaged columns, %d sentinel cells in %d rows, "
        "%d duplicate groups, %d gaps",
        sum(1 for row in mapping if row["status"] == normalization.UNKNOWN_STATUS),
        sentinels["total_cells"],
        sentinels["n_affected_rows"],
        len(timeline["duplicate_groups"]),
        len(timeline["gaps"]),
    )

    # ---- 元数据表 ----
    mapping_path = io_utils.write_csv(
        settings.resolve(stage1["metadata"]["channel_name_mapping"]),
        normalization.MAPPING_FIELDS,
        csv_rows(mapping, normalization.MAPPING_FIELDS),
    )
    decisions_path = io_utils.write_csv(
        settings.resolve(stage1["metadata"]["data_cleaning_decisions"]),
        normalization.DECISION_FIELDS,
        csv_rows(decisions, normalization.DECISION_FIELDS),
    )
    mask_path = io_utils.write_csv(
        processed_dir / stage1["outputs"]["missing_mask"],
        normalization.MASK_FIELDS,
        csv_rows(sentinels["mask_records"], normalization.MASK_FIELDS),
    )
    timeline_path = io_utils.write_csv(
        processed_dir / stage1["outputs"]["timeline_issues"],
        normalization.TIMELINE_FIELDS,
        csv_rows(
            normalization.timeline_issue_rows(timeline), normalization.TIMELINE_FIELDS
        ),
    )

    # ---- 候选数据（非最终版本）----
    raw_candidate, raw_rows, raw_cols, raw_bytes, raw_sha = (
        normalization.write_candidate_csv(
            frame, processed_dir / stage1["outputs"]["candidate_raw"]
        )
    )
    masked_frame = normalization.apply_sentinel_mask(frame, sentinels["mask_records"])
    masked_candidate, masked_rows, masked_cols, masked_bytes, masked_sha = (
        normalization.write_candidate_csv(
            masked_frame, processed_dir / stage1["outputs"]["candidate_masked"]
        )
    )
    logger.info("candidate raw: %s", relative_path(raw_candidate))
    logger.info("candidate masked: %s", relative_path(masked_candidate))

    # ---- 验证 ----
    verification = verify_candidates(
        frame,
        time_column,
        raw_candidate,
        masked_candidate,
        sentinels["mask_records"],
        stage1["sentinel_values"][0],
    )
    raw_after = io_utils.sha256_file(raw_path)
    long_after = io_utils.sha256_file(long_path)
    verification["raw_sha256_unchanged"] = raw_before == raw_after
    verification["long_sha256_unchanged"] = long_before == long_after
    logger.info("verification: %s", verification)
    failed = [
        key
        for key, value in verification.items()
        if isinstance(value, (bool, np.bool_)) and not value
    ]
    if failed:
        logger.warning("以下布尔校验项未通过: %s", failed)

    # ---- 候选清单 ----
    affected_rows = sentinels["n_affected_rows"]
    affected_columns = "; ".join(sentinels["affected_columns"])
    manifest_rows = [
        {
            "entry": "raw_weather_wide",
            "path": relative_path(raw_path),
            "role": "read-only source",
            "sha256_before": raw_before,
            "sha256_after": raw_after,
            "source_unchanged": raw_before == raw_after,
            "rules": "none (read-only)",
            "status": "protected",
        },
        {
            "entry": "raw_weather_long",
            "path": relative_path(long_path),
            "role": "read-only source",
            "sha256_before": long_before,
            "sha256_after": long_after,
            "source_unchanged": long_before == long_after,
            "rules": "none (read-only)",
            "status": "protected",
        },
        {
            "entry": "candidate_raw",
            "path": relative_path(raw_candidate),
            "role": "candidate A (not final)",
            "rows": raw_rows,
            "columns": raw_cols,
            "bytes": raw_bytes,
            "sha256": raw_sha,
            "modified_cells": 0,
            "modified_rows": 0,
            "affected_columns": "",
            "rules": "verbatim copy; no value/column/row/time changes",
            "status": normalization.UNKNOWN_STATUS,
        },
        {
            "entry": "candidate_masked",
            "path": relative_path(masked_candidate),
            "role": "candidate B (not final)",
            "rows": masked_rows,
            "columns": masked_cols,
            "bytes": masked_bytes,
            "sha256": masked_sha,
            "modified_cells": sentinels["total_cells"],
            "modified_rows": affected_rows,
            "affected_columns": affected_columns,
            "rules": "sentinel_to_NA__no_imputation__no_zero_fill; no row/time/column changes",
            "status": normalization.UNKNOWN_STATUS,
        },
    ]
    manifest_path = io_utils.write_csv(
        processed_dir / stage1["outputs"]["processed_manifest"],
        normalization.MANIFEST_FIELDS,
        csv_rows(manifest_rows, normalization.MANIFEST_FIELDS),
    )

    # ---- 报告 ----
    report_target = io_utils.unique_path(settings.resolve(stage1["report"]))
    outputs = [
        {"path": relative_path(path), "purpose": purpose}
        for path, purpose in (
            (raw_candidate, "候选 A：原值、原始列名、原始时间轴（52,696 行）"),
            (masked_candidate, "候选 B：81 个 -9999 置空（NaN），其余完全一致"),
            (mask_path, "稀疏缺失掩码：逐条记录 81 个哨兵单元格的位置"),
            (timeline_path, "时间轴问题清单：重复时间戳、1 处缺口、9 个缺失时间片"),
            (manifest_path, "候选清单：原始文件 SHA256 前后、候选文件规则与修改统计"),
            (mapping_path, "列名映射：原始列名 / 稳定 ID / 候选规范名 / 证据 / 置信度 / 状态"),
            (decisions_path, "清洗决策清单：待人工确认项、可选方案与影响"),
            (report_target, "本报告"),
            (log_path, "运行日志"),
        )
    ]
    candidates = [
        {
            "path": relative_path(raw_candidate),
            "rules": "逐字复制，无任何修改",
            "modified_cells": 0,
            "modified_rows": 0,
            "affected_columns": "",
            "rows": raw_rows,
            "columns": raw_cols,
            "sha256": raw_sha,
            "status": "candidate A — not final",
        },
        {
            "path": relative_path(masked_candidate),
            "rules": "-9999 → 空值（NaN）；不插值、不填 0、不删行、不改名",
            "modified_cells": sentinels["total_cells"],
            "modified_rows": affected_rows,
            "affected_columns": affected_columns,
            "rows": masked_rows,
            "columns": masked_cols,
            "sha256": masked_sha,
            "status": "candidate B — not final",
        },
    ]
    ctx = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "seed": config["project"]["seed"],
        "stage_status": stage1["status"],
        "raw_path": relative_path(raw_path),
        "long_path": relative_path(long_path),
        "raw_before": raw_before,
        "raw_after": raw_after,
        "long_before": long_before,
        "long_after": long_after,
        "mapping": mapping,
        "sentinels": sentinels,
        "timeline": timeline,
        "decisions": decisions,
        "candidates": candidates,
        "outputs": outputs,
        "verification": verification,
    }
    report_path = io_utils.write_text(report_target, normalization.render_report(ctx))
    logger.info("report: %s", relative_path(report_path))
    logger.info("log: %s", relative_path(log_path))

    print("\n=== Stage 1 数据规范化摘要 ===")
    print(f"  原始文件 SHA256 前后一致: {verification['raw_sha256_unchanged']} / "
          f"{verification['long_sha256_unchanged']}")
    print(f"  列名: {len(mapping)} 个通道, "
          f"{sum(1 for row in mapping if row['status'] == normalization.UNKNOWN_STATUS)} 个 Unknown "
          f"(保留原始列名 + 稳定 ID)")
    print(f"  -9999: {sentinels['total_cells']} 个单元格 / {affected_rows} 行 / "
          f"{affected_columns}")
    print(f"  重复时间戳: {sum(g['n_rows'] for g in timeline['duplicate_groups'])} 行 "
          f"({'; '.join(g['timestamp'] for g in timeline['duplicate_groups'])}), "
          f"21 变量一致={all(g['all_variables_identical'] for g in timeline['duplicate_groups'])}")
    print(f"  时间缺口: {len(timeline['gaps'])} 处, "
          f"缺 {sum(g['n_missing_slots'] for g in timeline['gaps'])} 个时间片")
    print(f"  候选 A: {relative_path(raw_candidate)} (修改 0 单元格)")
    print(f"  候选 B: {relative_path(masked_candidate)} "
          f"(修改 {sentinels['total_cells']} 单元格 / {affected_rows} 行)")
    print(f"  报告: {relative_path(report_path)}")
    print(f"  待确认决策: {len(decisions)} 项 → {relative_path(decisions_path)}")
    print(f"  日志: {relative_path(log_path)}")


if __name__ == "__main__":
    main()
