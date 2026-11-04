"""数据接入入口：只读复制 Weather 原始文件、校验 SHA256、生成清单与通道描述模板。

用法（共享环境解释器）：
    python scripts/ingest_data.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import audit, io_utils, settings  # noqa: E402

MANIFEST_FIELDS = (
    "name",
    "source",
    "target",
    "action",
    "source_bytes",
    "target_bytes",
    "source_sha256_before",
    "source_sha256_after",
    "source_unchanged",
    "target_sha256",
    "sha256_match",
    "checked_at",
)
TEMPLATE_FIELDS = (
    "channel_id",
    "channel_name",
    "description",
    "unit",
    "source",
    "provenance",
    "verified",
)


def build_description_template(
    primary: Path, template_path: Path, time_column: str, encoding: str
) -> tuple[Path, str]:
    """仅从原始表头抄录真实通道名，描述与来源字段一律留空，不生成任何语义文本。"""
    if template_path.exists():
        return template_path, "skipped_target_exists"
    columns = audit.read_header(primary, encoding)
    variables = [col for col in columns if col != time_column]
    rows = [
        (index, name, "", "", "", "", "pending")
        for index, name in enumerate(variables)
    ]
    path = io_utils.write_csv(template_path, TEMPLATE_FIELDS, rows)
    return path, "created"


def main() -> None:
    config = settings.load_config()
    settings.set_seed(config["project"]["seed"])
    logger, log_path = io_utils.make_logger(
        settings.resolve(config["outputs"]["logs_dir"]), "ingest_data"
    )
    weather_cfg = config["data"]["weather"]
    encoding = weather_cfg["encoding"]

    pairs = (
        ("weather_wide", config["data"]["source"]["weather_wide"], weather_cfg["primary"]),
        ("weather_long_tfb", config["data"]["source"]["weather_long"], weather_cfg["long_format"]),
    )
    records = []
    for name, source, target in pairs:
        record = io_utils.ingest_copy(settings.resolve(source), settings.resolve(target))
        record["name"] = name
        records.append(record)
        logger.info(
            "%s | %s | %s -> %s | sha256_match=%s | source_unchanged=%s",
            name,
            record["action"],
            record["source"],
            record["target"],
            record["sha256_match"],
            record.get("source_unchanged"),
        )

    manifest_path = io_utils.write_csv(
        settings.resolve(config["data"]["manifest"]),
        MANIFEST_FIELDS,
        [[record.get(field, "") for field in MANIFEST_FIELDS] for record in records],
    )

    template_path = settings.resolve(config["data"]["channel_descriptions_template"])
    template_written, template_action = build_description_template(
        settings.resolve(weather_cfg["primary"]),
        template_path,
        weather_cfg["time_column"],
        encoding,
    )

    logger.info("manifest: %s", manifest_path)
    logger.info("channel description template (%s): %s", template_action, template_written)
    logger.info("log: %s", log_path)

    print("\n=== 数据接入摘要 ===")
    for record in records:
        print(
            f"{record['name']}: {record['action']} | "
            f"source={record.get('source_bytes')} bytes | "
            f"sha256={record.get('source_sha256_before')} | "
            f"target_sha256={record.get('target_sha256')} | "
            f"match={record['sha256_match']} | source_unchanged={record.get('source_unchanged')}"
        )
    print(f"manifest: {manifest_path}")
    print(f"template ({template_action}): {template_written}")
    print(f"log: {log_path}")


if __name__ == "__main__":
    main()
