"""配置加载、统一路径解析与随机种子固定。"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any

import numpy as np
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "configs" / "experiment.yaml"


def load_config(path: Path | None = None) -> dict[str, Any]:
    """读取 experiment.yaml；配置是路径与实验参数的唯一来源。"""
    target = CONFIG_PATH if path is None else Path(path)
    with target.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    if not isinstance(config, dict):
        raise ValueError(f"配置文件内容不是映射: {target}")
    return config


def resolve(relative: str | Path) -> Path:
    """把配置中的相对路径解析到项目根目录；绝对路径原样返回。"""
    path = Path(relative)
    return path if path.is_absolute() else (PROJECT_ROOT / path)


def set_seed(seed: int) -> None:
    """固定全局随机种子（本阶段不采样，但保证后续实验可复现）。"""
    random.seed(seed)
    np.random.seed(seed)
