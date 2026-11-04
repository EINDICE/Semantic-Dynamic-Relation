"""环境检查入口：记录共享环境的 Python 解释器与依赖版本，不做任何安装动作。

用法（共享环境解释器）：
    python scripts/check_environment.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import environment, io_utils, settings  # noqa: E402


def main() -> None:
    config = settings.load_config()
    settings.set_seed(config["project"]["seed"])
    logger, log_path = io_utils.make_logger(
        settings.resolve(config["outputs"]["logs_dir"]), "check_environment"
    )

    env = environment.collect()
    logger.info("python_executable=%s", env["python_executable"])
    logger.info("python_version=%s", env["python_version"])
    logger.info("is_virtual_environment=%s", env["is_virtual_environment"])
    for package, version in env["versions"].items():
        logger.info("%s=%s", package, version or "NOT_INSTALLED")
    logger.info("phase1_required=%s", env["phase1_required"])
    logger.info("phase1_missing=%s", env["phase1_missing"] or "none")

    report_path = io_utils.write_text(
        settings.resolve(config["outputs"]["reports_dir"]) / "environment_check.md",
        environment.render_markdown(env),
    )
    versions_path = io_utils.write_json(
        settings.resolve(config["outputs"]["logs_dir"]) / "environment_versions.json", env
    )

    print("\n=== 共享环境检查 ===")
    print(f"Python: {env['python_version']} @ {env['python_executable']}")
    for package, version in env["versions"].items():
        print(f"  {package}: {version or 'NOT_INSTALLED'}")
    print(f"第一阶段所需依赖: {env['phase1_required']}")
    print(f"缺失项: {env['phase1_missing'] or '无'}")
    print(f"report: {report_path}")
    print(f"versions: {versions_path}")
    print(f"log: {log_path}")


if __name__ == "__main__":
    main()
