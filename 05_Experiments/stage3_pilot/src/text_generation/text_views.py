"""Text views for the Weather multimodal alignment pilot.

Compliance (see task book):
- The global Prompt is kept INTACT as a single text (no split into 21 prompts).
- `EXISTING_DESCRIPTION` = the verbatim global Prompt V1 (source: Stage 2 report).
- `DYNAMIC_TEXT` = rule-based incremental description (dynamic_text.py).
- No physical meaning is invented for uncertain channels.
"""
GLOBAL_PROMPT_V1 = (
    "2020 年全年采样间隔为 10 分钟的气象指标数据，共包含 21 个变量："
    "气压 (Air Pressure)、气温 (Air Temperature)、位温 (Potential Temperature)、"
    "露点温度 (Dew Point Temperature)、相对湿度 (Relative Humidity)、"
    "饱和水汽压 (Saturation Water Vapor Pressure)、实际水汽压 (Actual Water Vapor Pressure)、"
    "水汽压亏缺 (Water Vapor Pressure Deficit)、比湿 (Specific Humidity)、"
    "水汽浓度 (Water Vapor Concentration)、空气密度 (Air Density)、"
    "风速 (Wind Velocity)、最大风速 (Maximum Wind Velocity)、风向 (Wind Direction)、"
    "降水量 (Precipitation)、降水持续时间 (Precipitation Duration)、"
    "短波向下辐射 (Shortwave Downward Radiation)、光合有效辐射 (Photosynthetically Active Radiation)、"
    "最大光合有效辐射 (Maximum Photosynthetically Active Radiation)、"
    "记录仪内部温度 (Internal Logger Temperature)、二氧化碳浓度 (CO2 concentration)。"
    "我们将每个变量的完整序列视为一个词元 (Token)。"
)
PROMPT_V1_SHA256 = "55aba83346bb7a5d7f07dab48302e4cd36609bafb2a2c3e517fa28e6a9b6e43e"
VIEW_NAMES = ["none", "existing", "dynamic", "both"]


def get_view_text(view: str, dynamic_text: str) -> str:
    if view == "none":
        return ""
    if view == "existing":
        return GLOBAL_PROMPT_V1
    if view == "dynamic":
        return dynamic_text
    if view == "both":
        return GLOBAL_PROMPT_V1 + " " + dynamic_text
    raise ValueError(f"unknown view: {view}")
