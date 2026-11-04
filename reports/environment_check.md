# 共享环境检查报告

> 复用 BEDTime 项目实际运行的 Python 环境；未创建 .venv，未安装/升级任何依赖。

## 解释器

- Python 解释器：`C:\Users\ZhaoChenguang\AppData\Local\Programs\Python\Python310\python.exe`
- Python 版本：3.10.6 (CPython)
- `sys.prefix`：C:\Users\ZhaoChenguang\AppData\Local\Programs\Python\Python310
- 独立虚拟环境（venv/conda env）：否（全局 Python 安装）
- 操作系统：Windows-10-10.0.26200-SP0

## 已安装依赖版本（实测）

| 包 | 版本 | 第一阶段是否使用 |
|---|---|---|
| pandas | 2.2.0 | 是 |
| numpy | 1.26.4 | 是 |
| scipy | 1.15.3 | 否 |
| matplotlib | 3.10.9 | 否 |
| seaborn | 0.11.2 | 否 |
| scikit-learn | 1.1.2 | 否 |
| torch | 2.5.1+cu121 | 否 |
| transformers | 4.49.0 | 否 |
| PyYAML | 6.0.1 | 是 |
| huggingface_hub | 0.36.2 | 否 |

## 第一阶段依赖结论

- 实际需要：`numpy, pandas, PyYAML`
- 缺失项：无，全部已安装，无需任何安装动作
- 未执行 `pip install`，未执行 `pip install -U`，未修改 BEDTime 环境配置。
