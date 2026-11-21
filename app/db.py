import os
from contextlib import contextmanager
from psycopg_pool import ConnectionPool
pool = ConnectionPool(os.getenv("DATABASE_URL", "postgresql://wallet:wallet@localhost:5432/wallet"), open=False)
def start_pool():
    if pool.closed: pool.open()
@contextmanager
def transaction():
    start_pool()
    with pool.connection() as conn:
        with conn.transaction(): yield conn
