"""配置管理（说明书 §6）。

所有配置都从环境变量 / .env 读取，代码里不写死密钥。
数据库默认走 SQLite —— 本机零配置就能跑起来；把 `DATABASE_URL` 换成
`postgresql+psycopg://...` 即可切到 PostgreSQL（说明书 §7/§25 的目标形态），
其余代码一行都不用动。
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- 应用 ----
    app_name: str = "食时 API"
    api_prefix: str = "/api"
    debug: bool = True

    # ---- 数据库 ----
    # SQLite：本机零配置就能跑。切换 PostgreSQL 只改这一行
    # （另外要装 psycopg：pip install "psycopg[binary]"）：
    #   postgresql+psycopg://user:password@localhost:5432/shishi
    database_url: str = "sqlite:///./shishi.db"
    # auto: 检测到清洗后的六张表就直接读取，否则沿用本地演示表。
    # compact: 强制使用清洗库（缺表时启动失败，防止误连空库）。
    # legacy:  强制使用旧版演示表，主要用于测试和开发。
    content_mode: Literal["auto", "compact", "legacy"] = "auto"

    # ---- 认证（说明书 §12）----
    # ⚠️ 换生产环境必须改成随机值：
    #   python -c "import secrets; print(secrets.token_urlsafe(48))"
    secret_key: str = "dev-only-change-me"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 天，比赛演示期够用

    # ---- 验证码（邮箱 / 手机号通用）----
    # 机制和下发通道是解耦的：码本身是随机的、有有效期、有重发间隔和次数上限，
    # 通道只负责把它送出去。换通道不用动业务代码。
    code_ttl_seconds: int = 300          # 有效期 5 分钟
    code_resend_interval: int = 60       # 同一目标 60 秒内不许重发
    code_hourly_limit: int = 5           # 同一目标每小时最多发 5 条
    code_max_attempts: int = 5           # 一条码最多校验失败 5 次即作废
    # 演示保险：比赛现场万一邮箱发不出去，把它设为 true 就能用固定码。
    # 正常情况必须为 False —— 否则验证码又退化成"只认 123456"。
    allow_demo_code: bool = False
    demo_code: str = "123456"

    # ---- 邮件通道 ----
    # console: 把验证码打到服务日志（默认，零配置就能跑，算真机制但不真发信）
    # smtp:    真发邮件，需要把下面几项配全
    mail_backend: Literal["console", "smtp"] = "console"
    smtp_host: str = ""                   # 如 smtp.qq.com
    smtp_port: int = 465                  # 465 走 SSL；587 走 STARTTLS
    smtp_user: str = ""                   # 发信邮箱
    smtp_password: str = ""               # 邮箱的「SMTP 授权码」，不是登录密码
    smtp_from: str = ""                   # 留空则用 smtp_user
    # 收件人看到的发件人名字。不设的话 QQ 邮箱会直接显示 QQ 号（1218817158），
    # 设成「食时」才像一封正经的应用邮件。
    smtp_from_name: str = "食时"
    smtp_ssl: bool = True
    smtp_timeout: int = 15

    # ---- AI 大模型（DeepSeek / 任何兼容 OpenAI 协议的服务）----
    #
    # 设计原则（说明书 §14/§18 + 本次需求）：
    #   · 算法负责「选什么」—— 从我们自己的清洗库里按综合打分筛候选；
    #   · 大模型负责「怎么挑、怎么说」—— 只在候选集内做选择与解释，
    #     绝不允许它从全库自由生成菜名（会编出不存在的菜）。
    # 所以这里没有 AI 也能跑：候选与兜底理由全部由确定性算法给出，
    # `ai_api_key` 为空时自动降级，接口行为不变。
    ai_enabled: bool = True
    # ⚠️ 这里要填到「版本前缀」为止：代码是拿它拼 `{ai_base_url}/chat/completions`。
    #    DeepSeek 两种写法都认（`https://api.deepseek.com` 和 `.../v1`），
    #    但**多数兼容 OpenAI 的服务必须带 /v1**，不然会 404。
    ai_base_url: str = "https://api.deepseek.com"
    ai_api_key: str = ""                 # ⚠️ 只走环境变量 / .env，绝不写进代码
    ai_model: str = "deepseek-chat"
    # 要不要发 `response_format: {"type": "json_object"}`。
    #
    # ★ 这是换服务商时**唯一**容易翻车的地方：
    #   `json_object` 是 OpenAI 的扩展，不是所有「兼容 OpenAI」的服务都实现了。
    #   对方要是不认这个字段，通常会直接 400 —— 而我们的客户端**永不抛异常**，
    #   于是表现为「AI 悄悄退回算法」，界面照常但少了 AI 味，很难查。
    #   遇到这种服务商，把 AI_JSON_MODE 设成 false 就行（提示词里已经要求输出
    #   JSON，客户端的解析也容错 ```json 围栏），不用改代码。
    ai_json_mode: bool = True
    ai_timeout_seconds: int = 45
    ai_max_tokens: int = 1200
    ai_temperature: float = 0.6
    # 首页「每天每地区只问一次 AI」的缓存表。关掉它每次请求都会真调模型。
    ai_daily_cache_enabled: bool = True
    # 首页留给 AI 的候选数量（算法先筛出这么多，AI 在里面挑最终展示的）
    ai_home_shortlist: int = 8

    # ---- 天气（首页推荐要考虑「今天什么天气」）----
    # Open-Meteo 免费且不需要 key。取不到就退回按月份的时令气候估算，
    # 再不行就当「无天气信息」——任何情况都不能让首页挂掉。
    weather_enabled: bool = True
    weather_base_url: str = "https://api.open-meteo.com/v1/forecast"
    weather_timeout_seconds: int = 6

    # ---- CORS ----
    # Flutter Web 跑在另一个端口（flutter run -d chrome 每次端口都不同），
    # 必须在后端显式放行，否则浏览器直接拦掉请求。
    cors_origins: list[str] = [
        "http://localhost",
        "http://127.0.0.1",
        "https://aiczz.github.io",
    ]

    # CORS 允许任意来源的正则（覆盖 flutter run -d chrome 的随机端口）。
    # 仅开发期使用；.env 里设成空字符串即可关闭。
    cors_origin_regex: str = r"^http://(localhost|127\.0\.0\.1)(:\d+)?$"

    @property
    def ai_configured(self) -> bool:
        """有没有配好大模型。没配好就走确定性算法，绝不报错。"""
        return bool(self.ai_enabled and self.ai_api_key.strip() and self.ai_base_url.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
