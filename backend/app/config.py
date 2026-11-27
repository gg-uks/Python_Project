"""환경 변수에서 설정을 읽습니다 (omm-api.env).

개발할 때:   set -a; . ./omm-api.env; set +a
서비스로:    systemd 의 EnvironmentFile= 이 같은 파일을 읽음
"""
import os
from dataclasses import dataclass, field


def _list(name: str) -> list[str]:
    return [x.strip() for x in os.getenv(name, "").split(",") if x.strip()]


@dataclass(frozen=True)
class Settings:
    pg_host: str = os.getenv("PGHOST", "10.0.56.101")
    pg_port: str = os.getenv("PGPORT", "5432")
    pg_db: str = os.getenv("PGDATABASE", "omm")
    pg_user: str = os.getenv("PGUSER", "omm_api")
    pg_password: str = os.getenv("PGPASSWORD", "")
    pg_pool_max: int = int(os.getenv("PG_POOL_MAX", "5"))

    jwt_secret: str = os.getenv("JWT_SECRET", "")
    jwt_expire_min: int = int(os.getenv("JWT_EXPIRE_MIN", "720"))

    admin_emails: list[str] = field(default_factory=lambda: [e.lower() for e in _list("ADMIN_EMAILS")])
    cors_origins: list[str] = field(default_factory=lambda: _list("CORS_ORIGINS"))

    # Redis: Sentinel 주소들 (있으면 이걸로) 또는 REDIS_URL (Redis 1대일 때). 둘 다 비우면 Redis 없이 동작
    redis_sentinels: list[tuple[str, int]] = field(default_factory=lambda: [
        (h, int(p)) for h, _, p in (x.partition(":") for x in _list("REDIS_SENTINELS"))])
    redis_master: str = os.getenv("REDIS_MASTER_NAME", "omm-redis")
    redis_url: str = os.getenv("REDIS_URL", "")
    redis_password: str = os.getenv("REDIS_PASSWORD", "")
    cache_ttl: int = int(os.getenv("CACHE_TTL", "21600"))       # 응답 캐시 최대 보관 (초, 기본 6시간)

    @property
    def pg_dsn(self) -> str:
        return (f"host={self.pg_host} port={self.pg_port} dbname={self.pg_db} "
                f"user={self.pg_user} password={self.pg_password} application_name=omm-api")


settings = Settings()

if len(settings.jwt_secret) < 32:
    raise RuntimeError("JWT_SECRET 이 비었거나 너무 짧아요 (32자 이상). omm-api.env 를 확인하세요.")
