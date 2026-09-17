"""配置管理（说明书 §6）。

所有配置都从环境变量 / .env 读取，代码里不写死密钥。
数据库默认走 SQLite —— 本机零配置就能跑起来；把 `DATABASE_URL` 换成
`postgresql+psycopg://...` 即可切到 PostgreSQL（说明书 §7/§25 的目标形态），
其余代码一行都不用动。
"""

from functools import lru_cache

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

    # ---- 认证（说明书 §12）----
    # ⚠️ 换生产环境必须改成随机值：
    #   python -c "import secrets; print(secrets.token_urlsafe(48))"
    secret_key: str = "dev-only-change-me"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 天，比赛演示期够用

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


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
