"""独立的时间连续性检查（Stage 1.5 新增），供未来窗口构建调用。

设计原则：
- 以「实际时间差」判断采样连续性，不依赖行索引是否相邻；
- 标记所有不等于预期间隔的位置（含 0 分钟重复、100 分钟缺口、倒退等）；
- 给出窗口不得跨越的分段与可执行的窗口校验接口；
- 重复时间戳策略必须显式传入，函数**不删除、不合并、不插值、不重采样**任何记录；
  `excluded_rows` 只表示「窗口视图中不参与」，原始数据层始终全部保留；
- 纯只读、无副作用：不修改输入、不写文件、不构建窗口、不计算关系矩阵。

重复时间戳策略：
- ``boundary``    : 方案 A，全部记录保留，重复时间戳处作为窗口硬边界（0 分钟间隔切断）。
- ``exclude_all`` : 方案 B，窗口视图排除重复时间戳的全部记录（数据层仍保留）。
- ``keep_first``  : 方案 B 的变体，仅排除重复组中的后续记录，保留首条。
"""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np
import pandas as pd

VALID_POLICIES = ("boundary", "exclude_all", "keep_first")


def _as_time_series(time_values: Any) -> pd.Series:
    """统一转成 0..n-1 位置索引的 datetime Series。"""
    if isinstance(time_values, pd.Series):
        return pd.to_datetime(time_values, errors="coerce").reset_index(drop=True)
    return pd.to_datetime(pd.Series(list(time_values)), errors="coerce").reset_index(drop=True)


def _find_issues(
    times: pd.Series, expected: pd.Timedelta, active_rows: Sequence[int]
) -> list[dict[str, Any]]:
    """逐对比较活跃记录的**实际时间差**，标记所有 != expected 的间隔。"""
    issues: list[dict[str, Any]] = []
    for left, right in zip(active_rows[:-1], active_rows[1:]):
        t0, t1 = times.iloc[left], times.iloc[right]
        if pd.isna(t0) or pd.isna(t1):
            issues.append(
                {
                    "from_row": int(left),
                    "to_row": int(right),
                    "from_time": str(t0),
                    "to_time": str(t1),
                    "interval": "NaT",
                    "interval_seconds": float("nan"),
                    "kind": "unparsable_time",
                    "n_missing_slots": 0,
                    "missing_slots": (),
                }
            )
            continue
        delta = t1 - t0
        if delta == expected:
            continue
        if delta == pd.Timedelta(0):
            kind = "duplicate_zero"
        elif delta < pd.Timedelta(0):
            kind = "negative"
        elif delta > expected:
            kind = "gap"
        else:
            kind = "short"
        missing_slots: tuple[str, ...] = ()
        if kind == "gap":
            steps = int(delta / expected)
            missing_slots = tuple(str(t0 + k * expected) for k in range(1, steps))
        issues.append(
            {
                "from_row": int(left),
                "to_row": int(right),
                "from_time": str(t0),
                "to_time": str(t1),
                "interval": str(delta),
                "interval_seconds": float(delta.total_seconds()),
                "kind": kind,
                "n_missing_slots": len(missing_slots),
                "missing_slots": missing_slots,
            }
        )
    return issues


def _make_segment(times: pd.Series, rows: Sequence[int]) -> dict[str, Any]:
    return {
        "start_row": int(rows[0]),
        "end_row": int(rows[-1]),
        "start_time": str(times.iloc[rows[0]]),
        "end_time": str(times.iloc[rows[-1]]),
        "n_rows": int(len(rows)),
        "rows": tuple(int(row) for row in rows),
    }


def check_time_continuity(
    time_values: Any,
    expected_interval: str = "10min",
    duplicate_policy: str = "boundary",
) -> dict[str, Any]:
    """检查时间连续性并返回窗口分段。

    参数
    ----
    time_values : 时间戳序列（pd.Series 或可迭代对象），按文件原始顺序传入。
    expected_interval : 预期采样间隔，默认 ``"10min"``。
    duplicate_policy : ``boundary`` / ``exclude_all`` / ``keep_first``，必须显式选择。

    返回
    ----
    dict：含 issues、duplicate_groups、excluded_rows、segments、
    window_boundary_rows 等；所有行号均为原始文件 0-based 位置索引。
    """
    if duplicate_policy not in VALID_POLICIES:
        raise ValueError(f"duplicate_policy 必须是 {VALID_POLICIES} 之一，收到 {duplicate_policy!r}")

    times = _as_time_series(time_values)
    expected = pd.Timedelta(expected_interval)
    n_rows = int(len(times))
    unparsable = [int(pos) for pos in np.flatnonzero(times.isna().to_numpy())]

    duplicate_groups: list[dict[str, Any]] = []
    duplicate_mask = times.duplicated(keep=False) & times.notna()
    if bool(duplicate_mask.any()):
        subset = times[duplicate_mask]
        for stamp, group in subset.groupby(subset):
            rows = [int(index) for index in group.index]
            duplicate_groups.append(
                {"timestamp": str(stamp), "rows": rows, "n_rows": len(rows)}
            )

    if duplicate_policy == "exclude_all":
        excluded = [row for group in duplicate_groups for row in group["rows"]]
    elif duplicate_policy == "keep_first":
        excluded = [row for group in duplicate_groups for row in group["rows"][1:]]
    else:
        excluded = []
    excluded_set = set(excluded)
    active_rows = [row for row in range(n_rows) if row not in excluded_set]

    issues = _find_issues(times, expected, active_rows)
    boundary_rows = {issue["to_row"] for issue in issues}

    segments: list[dict[str, Any]] = []
    if active_rows:
        segment_start = 0
        for index in range(1, len(active_rows)):
            if active_rows[index] in boundary_rows:
                segments.append(_make_segment(times, active_rows[segment_start:index]))
                segment_start = index
        segments.append(_make_segment(times, active_rows[segment_start:]))

    return {
        "expected_interval": str(expected),
        "expected_interval_seconds": float(expected.total_seconds()),
        "duplicate_policy": duplicate_policy,
        "n_rows": n_rows,
        "n_active_rows": len(active_rows),
        "unparsable_rows": unparsable,
        "duplicate_groups": duplicate_groups,
        "excluded_rows": sorted(excluded),
        "issues": issues,
        "n_issues": len(issues),
        "gap_rows": [issue["to_row"] for issue in issues if issue["kind"] == "gap"],
        "window_boundary_rows": sorted(boundary_rows),
        "segments": segments,
        "n_segments": len(segments),
    }


def estimate_window_count(segments: Sequence[dict[str, Any]], window_size: int) -> int:
    """估算步长为 1 的滑动窗口总数；跨段窗口不计入。"""
    if window_size < 1:
        raise ValueError("window_size 必须 >= 1")
    return sum(max(0, segment["n_rows"] - window_size + 1) for segment in segments)


def validate_window_rows(
    rows: Sequence[int],
    time_values: Any,
    continuity: dict[str, Any],
    window_size: int,
    expected_interval: str = "10min",
) -> dict[str, Any]:
    """校验由「活跃行序列」构成的窗口：长度正确、是段内连续子序列、时间严格等间隔。

    适用于存在 ``excluded_rows`` 的策略（此时窗口行号在原始文件中不连续）。
    """
    rows = [int(row) for row in rows]
    expected = pd.Timedelta(expected_interval)
    times = _as_time_series(time_values)

    def invalid(reason: str) -> dict[str, Any]:
        return {"valid": False, "reason": reason}

    if len(rows) != window_size:
        return invalid("窗口行数不等于 window_size")
    if rows != sorted(rows) or len(set(rows)) != len(rows):
        return invalid("窗口行序列必须严格递增且不重复")
    excluded = set(continuity["excluded_rows"])
    if any(row in excluded for row in rows):
        return invalid("窗口包含窗口视图中排除的重复时间戳记录")

    owner = None
    for segment in continuity["segments"]:
        if rows[0] in segment["rows"]:
            owner = segment
            break
    if owner is None:
        return invalid("起点不属于任何连续段")
    segment_rows = owner["rows"]
    start_index = segment_rows.index(rows[0])
    if tuple(segment_rows[start_index : start_index + len(rows)]) != tuple(rows):
        return invalid("窗口不是段内连续的活跃行序列（可能跨越时间不连续边界）")

    for left, right in zip(rows[:-1], rows[1:]):
        if times.iloc[right] - times.iloc[left] != expected:
            return invalid(f"行 {left}->{right} 的实际时间差不等于 {expected}")
    return {
        "valid": True,
        "reason": "",
        "start_time": str(times.iloc[rows[0]]),
        "end_time": str(times.iloc[rows[-1]]),
        "span": str(times.iloc[rows[-1]] - times.iloc[rows[0]]),
    }


def validate_window(
    start_row: int,
    end_row: int,
    time_values: Any,
    continuity: dict[str, Any],
    window_size: int,
    expected_interval: str = "10min",
) -> dict[str, Any]:
    """便捷包装：以原始连续行区间构造窗口并校验（适用于无排除行的 ``boundary`` 策略）。"""
    return validate_window_rows(
        list(range(start_row, end_row + 1)),
        time_values,
        continuity,
        window_size,
        expected_interval,
    )
