"""SQLite storage for crawled posts and crawl run history."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from .config import DB_FILE

SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    shortcode    TEXT PRIMARY KEY,
    target_type  TEXT NOT NULL,
    target_name  TEXT NOT NULL,
    owner        TEXT,
    caption      TEXT,
    date_utc     TEXT NOT NULL,
    is_video     INTEGER NOT NULL DEFAULT 0,
    media        TEXT NOT NULL DEFAULT '[]',
    likes        INTEGER,
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_posts_target ON posts(target_type, target_name, date_utc DESC);
CREATE INDEX IF NOT EXISTS idx_posts_date ON posts(date_utc DESC);

CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    trigger     TEXT NOT NULL,
    status      TEXT NOT NULL,
    new_posts   INTEGER NOT NULL DEFAULT 0,
    message     TEXT
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect():
    conn = sqlite3.connect(DB_FILE, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as c:
        c.executescript(SCHEMA)
        # A previous process may have died mid-run.
        c.execute("UPDATE runs SET status='aborted', finished_at=? WHERE status='running'", (now_iso(),))


def post_exists(shortcode: str) -> bool:
    with connect() as c:
        return c.execute("SELECT 1 FROM posts WHERE shortcode=?", (shortcode,)).fetchone() is not None


def upsert_post(p: dict) -> None:
    with connect() as c:
        c.execute(
            """INSERT INTO posts (shortcode, target_type, target_name, owner, caption, date_utc,
                                  is_video, media, likes, created_at)
               VALUES (:shortcode, :target_type, :target_name, :owner, :caption, :date_utc,
                       :is_video, :media, :likes, :created_at)
               ON CONFLICT(shortcode) DO UPDATE SET
                   caption=excluded.caption, media=excluded.media, likes=excluded.likes""",
            {**p, "media": json.dumps(p["media"]), "created_at": now_iso()},
        )


def _row_to_post(r: sqlite3.Row) -> dict:
    d = dict(r)
    d["media"] = json.loads(d["media"] or "[]")
    return d


def list_posts(target_type: str | None = None, target_name: str | None = None,
               limit: int = 50, offset: int = 0) -> list[dict]:
    sql = "SELECT * FROM posts"
    args: list = []
    if target_type:
        sql += " WHERE target_type=? AND lower(target_name)=lower(?)"
        args += [target_type, target_name]
    sql += " ORDER BY date_utc DESC LIMIT ? OFFSET ?"
    args += [limit, offset]
    with connect() as c:
        return [_row_to_post(r) for r in c.execute(sql, args)]


def count_posts() -> int:
    with connect() as c:
        return c.execute("SELECT COUNT(*) FROM posts").fetchone()[0]


def target_counts() -> list[dict]:
    with connect() as c:
        return [dict(r) for r in c.execute(
            "SELECT target_type, target_name, COUNT(*) AS n, MAX(date_utc) AS latest "
            "FROM posts GROUP BY target_type, target_name ORDER BY target_type, target_name")]


def start_run(trigger: str) -> int:
    with connect() as c:
        cur = c.execute("INSERT INTO runs (started_at, trigger, status) VALUES (?, ?, 'running')",
                        (now_iso(), trigger))
        return cur.lastrowid


def finish_run(run_id: int, status: str, new_posts: int, message: str) -> None:
    with connect() as c:
        c.execute("UPDATE runs SET finished_at=?, status=?, new_posts=?, message=? WHERE id=?",
                  (now_iso(), status, new_posts, message, run_id))


def recent_runs(limit: int = 10) -> list[dict]:
    with connect() as c:
        return [dict(r) for r in c.execute("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,))]
