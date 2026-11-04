"""共享环境检查：只读取已安装分发的元数据，不 import 大型框架。"""

from __future__ import annotations

import importlib.metadata as metadata
import platform
import sys

# 第一阶段脚本中实际 import 的依赖
PHASE1_REQUIRED = ("numpy", "pandas", "PyYAML")

# 用户要求盘点、但第一阶段不使用的共享环境依赖
AUDIT_PACKAGES = (
    "pandas",
    "numpy",
    "scipy",
    "matplotlib",
    "seaborn",
    "scikit-learn",
    "torch",
    "transformers",
    "PyYAML",
    "huggingface_hub",
)


def collect() -> dict:
    versions: dict[str, str | None] = {}
    for package in AUDIT_PACKAGES:
        try:
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            versions[package] = None

    missing = [name for name in PHASE1_REQUIRED if versions.get(name) is None]
    return {
        "python_executable": sys.executable,
        "python_version": platform.python_version(),
        "implementation": platform.python_implementation(),
        "sys_prefix": sys.prefix,
        "sys_base_prefix": sys.base_prefix,
        "is_virtual_environment": sys.prefix != sys.base_prefix,
        "platform": platform.platform(),
        "versions": versions,
        "phase1_required": list(PHASE1_REQUIRED),
        "phase1_missing": missing,
    }


def render_markdown(env: dict) -> str:
    lines = [
        "# 共享环境检查报告",
        "",
        "> 复用 BEDTime 项目实际运行的 Python 环境；未创建 .venv，未安装/升级任何依赖。",
        "",
        "## 解释器",
        "",
        f"- Python 解释器：`{env['python_executable']}`",
        f"- Python 版本：{env['python_version']} ({env['implementation']})",
        f"- `sys.prefix`：{env['sys_prefix']}",
        f"- 独立虚拟环境（venv/conda env）：{'是' if env['is_virtual_environment'] else '否（全局 Python 安装）'}",
        f"- 操作系统：{env['platform']}",
        "",
        "## 已安装依赖版本（实测）",
        "",
        "| 包 | 版本 | 第一阶段是否使用 |",
        "|---|---|---|",
    ]
    for package, version in env["versions"].items():
        used = "是" if package in PHASE1_REQUIRED else "否"
        lines.append(f"| {package} | {version or '未安装'} | {used} |")
    lines += [
        "",
        "## 第一阶段依赖结论",
        "",
        f"- 实际需要：`{', '.join(PHASE1_REQUIRED)}`",
        f"- 缺失项：{'无，全部已安装，无需任何安装动作' if not env['phase1_missing'] else ', '.join(env['phase1_missing'])}",
        "- 未执行 `pip install`，未执行 `pip install -U`，未修改 BEDTime 环境配置。",
        "",
    ]
    return "\n".join(lines)
