"""PostgreSQL 연결 풀.

라우터에서는 이렇게 씁니다:
    def handler(conn: Conn):
        rows = conn.execute("SELECT ...", (값,)).fetchall()   # 각 행은 dict

요청 하나가 끝나면 자동으로 commit, 예외가 나면 rollback 됩니다.
SQL 에 값을 넣을 때는 반드시 %s 자리표시자를 쓰세요 (문자열 이어붙이기 금지 · SQL 인젝션).
"""
from typing import Annotated, Iterator

from fastapi import Depends
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import settings

pool = ConnectionPool(
    conninfo=settings.pg_dsn,
    min_size=1,
    max_size=settings.pg_pool_max,
    kwargs={"row_factory": dict_row},
    open=False,
)


def get_conn() -> Iterator[Connection]:
    with pool.connection() as conn:
        yield conn


Conn = Annotated[Connection, Depends(get_conn)]
