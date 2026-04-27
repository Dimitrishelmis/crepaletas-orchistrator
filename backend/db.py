import sqlite3
from datetime import datetime
from security import DATA_DIR

DB_PATH = DATA_DIR / "marketing.db"


def get_connection():
    return sqlite3.connect(DB_PATH)


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS generated_posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT NOT NULL,
        topic TEXT NOT NULL,
        platform TEXT NOT NULL,
        language TEXT NOT NULL,
        content TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'draft',
        file_path TEXT
    )
    """)

    cur.execute("PRAGMA table_info(generated_posts)")
    existing_columns = {row[1] for row in cur.fetchall()}
    migrations = {
        "image_file": "ALTER TABLE generated_posts ADD COLUMN image_file TEXT",
        "image_url": "ALTER TABLE generated_posts ADD COLUMN image_url TEXT",
        "approved_at": "ALTER TABLE generated_posts ADD COLUMN approved_at TEXT",
        "published_at": "ALTER TABLE generated_posts ADD COLUMN published_at TEXT",
        "target_platform": "ALTER TABLE generated_posts ADD COLUMN target_platform TEXT",
        "publish_result": "ALTER TABLE generated_posts ADD COLUMN publish_result TEXT",
        "provider": "ALTER TABLE generated_posts ADD COLUMN provider TEXT",
    }

    for column, sql in migrations.items():
        if column not in existing_columns:
            cur.execute(sql)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT NOT NULL,
        source TEXT NOT NULL,
        message TEXT NOT NULL
    )
    """)

    conn.commit()
    conn.close()


def save_generated_post(
    topic: str,
    platform: str,
    language: str,
    content: str,
    file_path: str,
    image_file: str | None = None,
    image_url: str | None = None,
    provider: str | None = None,
):
    conn = get_connection()
    cur = conn.cursor()

    created_at = datetime.now().isoformat(timespec="seconds")

    cur.execute("""
    INSERT INTO generated_posts (
        created_at, topic, platform, language, content, status, file_path,
        image_file, image_url, provider
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        created_at, topic, platform, language, content, "draft", file_path,
        image_file, image_url, provider
    ))

    post_id = cur.lastrowid
    conn.commit()
    conn.close()

    return post_id


def list_generated_posts(limit: int = 20):
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
    SELECT id, created_at, topic, platform, language, status, file_path,
           image_file, image_url, approved_at, published_at, target_platform,
           publish_result, provider
    FROM generated_posts
    ORDER BY id DESC
    LIMIT ?
    """, (limit,))

    rows = [dict(row) for row in cur.fetchall()]
    conn.close()
    return rows


def get_generated_post(post_id: int):
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
    SELECT *
    FROM generated_posts
    WHERE id = ?
    """, (post_id,))

    row = cur.fetchone()
    conn.close()

    return dict(row) if row else None


def update_post_status(
    post_id: int,
    status: str,
    approved_at: str | None = None,
    published_at: str | None = None,
    target_platform: str | None = None,
    publish_result: str | None = None,
):
    conn = get_connection()
    cur = conn.cursor()

    updates = ["status = ?"]
    values = [status]

    if approved_at is not None:
        updates.append("approved_at = ?")
        values.append(approved_at)
    if published_at is not None:
        updates.append("published_at = ?")
        values.append(published_at)
    if target_platform is not None:
        updates.append("target_platform = ?")
        values.append(target_platform)
    if publish_result is not None:
        updates.append("publish_result = ?")
        values.append(publish_result)

    values.append(post_id)
    cur.execute(
        f"UPDATE generated_posts SET {', '.join(updates)} WHERE id = ?",
        values
    )

    changed = cur.rowcount
    conn.commit()
    conn.close()
    return changed > 0


def approve_post(post_id: int):
    approved_at = datetime.now().isoformat(timespec="seconds")
    updated = update_post_status(post_id, "approved", approved_at=approved_at)
    return get_generated_post(post_id) if updated else None


def reject_post(post_id: int):
    updated = update_post_status(post_id, "rejected")
    return get_generated_post(post_id) if updated else None


def publish_post_record(
    post_id: int,
    target_platform: str,
    publish_result: str,
    status: str = "published_mock",
):
    published_at = datetime.now().isoformat(timespec="seconds")
    updated = update_post_status(
        post_id,
        status,
        published_at=published_at,
        target_platform=target_platform,
        publish_result=publish_result,
    )
    return get_generated_post(post_id) if updated else None


def update_generated_post_content(
    post_id: int,
    content: str,
    file_path: str | None = None,
    image_file: str | None = None,
    image_url: str | None = None,
):
    conn = get_connection()
    cur = conn.cursor()

    updates = ["content = ?"]
    values = [content]

    if file_path is not None:
        updates.append("file_path = ?")
        values.append(file_path)
    if image_file is not None:
        updates.append("image_file = ?")
        values.append(image_file)
    if image_url is not None:
        updates.append("image_url = ?")
        values.append(image_url)

    values.append(post_id)
    cur.execute(
        f"UPDATE generated_posts SET {', '.join(updates)} WHERE id = ?",
        values
    )

    changed = cur.rowcount
    conn.commit()
    conn.close()
    return get_generated_post(post_id) if changed else None


def save_log(source: str, message: str):
    conn = get_connection()
    cur = conn.cursor()

    created_at = datetime.now().isoformat(timespec="seconds")

    cur.execute("""
    INSERT INTO logs (created_at, source, message)
    VALUES (?, ?, ?)
    """, (created_at, source, message))

    log_id = cur.lastrowid
    conn.commit()
    conn.close()

    return log_id
