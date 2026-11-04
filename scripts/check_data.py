"""数据检查入口：读取 Weather 只读副本，输出统计表、报告与日志。

用法（共享环境解释器）：
    python scripts/check_data.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import audit, io_utils, settings  # noqa: E402


def main() -> None:
    config = settings.load_config()
    settings.set_seed(config["project"]["seed"])
    logger, log_path = io_utils.make_logger(
        settings.resolve(config["outputs"]["logs_dir"]), "check_data"
    )

    weather_cfg = config["data"]["weather"]
    audit_cfg = config["experiment"]["audit"]
    primary = settings.resolve(weather_cfg["primary"])
    if not primary.exists():
        raise FileNotFoundError(f"未找到主数据文件: {primary}（请先运行 scripts/ingest_data.py）")

    logger.info("读取主数据文件: %s", primary)
    frame = audit.load_weather(primary, encoding=weather_cfg["encoding"])
    result = audit.audit_dataframe(
        frame,
        time_column=weather_cfg["time_column"],
        expected_frequency=weather_cfg["expected_frequency"],
        iqr_multiplier=audit_cfg["iqr_multiplier"],
        sentinel_values=audit_cfg.get("sentinel_values", []),
    )

    if audit_cfg["cross_check_long_format"]:
        long_path = settings.resolve(weather_cfg["long_format"])
        if long_path.exists():
            logger.info("交叉校验长表: %s", long_path)
            result["long_format"] = audit.audit_long_format(
                long_path, encoding=weather_cfg["encoding"]
            )
        else:
            logger.warning("长表不存在，跳过交叉校验: %s", long_path)

    result["primary_file"] = weather_cfg["primary"]
    result["seed"] = config["project"]["seed"]

    tables = audit.write_tables(result, settings.resolve(config["outputs"]["tables_dir"]))
    report_path = io_utils.write_text(
        settings.resolve(config["outputs"]["reports_dir"]) / "weather_data_check.md",
        audit.render_report(result, weather_cfg["primary"], config),
    )
    for path in tables:
        logger.info("table: %s", path)
    logger.info("report: %s", report_path)
    logger.info("log: %s", log_path)

    print("\n=== Weather 数据检查摘要 ===")
    for key, value in audit.summary_pairs(result):
        print(f"  {key}: {value}")
    print(f"  有效变量: {result['n_valid_variables']}/{result['n_variables']}")
    print(f"  时间列: {result['time_column']}")
    print(f"  变量列: {result['variables']}")
    print(f"  编码损伤列: {result['encoding_damaged_columns']}")
    for path in tables:
        print(f"table: {path}")
    print(f"report: {report_path}")
    print(f"log: {log_path}")


if __name__ == "__main__":
    main()
