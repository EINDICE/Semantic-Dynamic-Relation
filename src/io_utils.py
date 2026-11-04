"""SHA256 校验、只读复制、绝不覆盖的写入与日志归档工具。"""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Sequence


def sha256_file(path: str | Path, chunk_size: int = 1 << 20) -> str:
    path = Path(path)
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def unique_path(path: str | Path) -> Path:
    """若目标已存在则追加时间戳，保证任何写入都不会覆盖已有文件。"""
    path = Path(path)
    if not path.exists():
        return path
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    candidate = path.with_name(f"{path.stem}_{stamp}{path.suffix}")
    counter = 1
    while candidate.exists():
        candidate = path.with_name(f"{path.stem}_{stamp}_{counter}{path.suffix}")
        counter += 1
    return candidate


def write_text(path: str | Path, text: str) -> Path:
    target = unique_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target


def write_csv(path: str | Path, header: Sequence[str], rows: Iterable[Sequence[Any]]) -> Path:
    target = unique_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)
    return target


def write_json(path: str | Path, payload: Any) -> Path:
    target = unique_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    return target


def ingest_copy(source: str | Path, target: str | Path) -> dict[str, Any]:
    """把外部只读来源复制进项目；目标已存在时跳过复制，只做一致性校验。

    复制前后各计算一次源文件 SHA256，用于确认原始文件未被改动。
    """
    source, target = Path(source), Path(target)
    record: dict[str, Any] = {
        "source": str(source),
        "target": str(target),
        "source_exists": source.exists(),
    }
    if not source.exists():
        record.update({"action": "source_missing", "sha256_match": False})
        return record

    before = sha256_file(source)
    src_size = source.stat().st_size
    if target.exists():
        action = "skipped_target_exists"
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        action = "copied"
    after = sha256_file(source)
    dst_hash = sha256_file(target) if target.exists() else ""

    record.update(
        {
            "action": action,
            "source_bytes": src_size,
            "target_bytes": target.stat().st_size if target.exists() else 0,
            "source_sha256_before": before,
            "source_sha256_after": after,
            "source_unchanged": before == after,
            "target_sha256": dst_hash,
            "sha256_match": bool(dst_hash) and before == dst_hash,
            "checked_at": datetime.now().isoformat(timespec="seconds"),
        }
    )
    return record


def make_logger(logs_dir: str | Path, name: str) -> tuple[logging.Logger, Path]:
    """每次运行生成带时间戳的独立日志文件，归档到 logs/。"""
    logs_dir = Path(logs_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = unique_path(logs_dir / f"{name}_{stamp}.log")

    logger = logging.getLogger(f"sdr.{name}")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    logger.propagate = False
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    return logger, log_path
