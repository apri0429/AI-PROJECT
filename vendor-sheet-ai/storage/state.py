from __future__ import annotations

import json
from typing import Any

import pymysql
from pymysql.cursors import DictCursor

from config import settings


class StateStore:
    def __init__(self) -> None:
        self._ensure_database_exists()
        self._init_db()

    def _connect(self, *, with_db: bool = True) -> pymysql.connections.Connection:
        return pymysql.connect(
            host=settings.mysql_host,
            port=settings.mysql_port,
            user=settings.mysql_user,
            password=settings.mysql_password,
            database=settings.mysql_database if with_db else None,
            charset="utf8mb4",
            autocommit=True,
            cursorclass=DictCursor,
        )

    def _ensure_database_exists(self) -> None:
        conn = self._connect(with_db=False)
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"CREATE DATABASE IF NOT EXISTS `{settings.mysql_database}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS processed_files (
                        file_name VARCHAR(255) PRIMARY KEY,
                        processed_at DATETIME NOT NULL
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS sheet_rows (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        source VARCHAR(255) NOT NULL,
                        row_index INT NOT NULL,
                        data LONGTEXT NOT NULL,
                        updated_at DATETIME NOT NULL,
                        INDEX idx_sheet_rows_source (source)
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS linked_sheets (
                        sheet_id VARCHAR(255) NOT NULL,
                        gid VARCHAR(255) NOT NULL DEFAULT '',
                        url VARCHAR(2048) NOT NULL,
                        linked_at DATETIME NOT NULL,
                        PRIMARY KEY (sheet_id, gid)
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS conversations (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        title VARCHAR(255) NOT NULL DEFAULT 'New chat',
                        pinned TINYINT(1) NOT NULL DEFAULT 0,
                        archived TINYINT(1) NOT NULL DEFAULT 0,
                        created_at DATETIME NOT NULL,
                        updated_at DATETIME NOT NULL
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS chat_messages (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        conversation_id INT NOT NULL,
                        data LONGTEXT NOT NULL,
                        created_at DATETIME NOT NULL,
                        INDEX idx_chat_messages_conversation (conversation_id)
                    )
                    """
                )
                # chat_messages may already exist from before conversations were
                # introduced; add the column if it's missing instead of failing.
                try:
                    cursor.execute(
                        "ALTER TABLE chat_messages ADD COLUMN conversation_id INT NOT NULL DEFAULT 0"
                    )
                    cursor.execute(
                        "ALTER TABLE chat_messages ADD INDEX idx_chat_messages_conversation (conversation_id)"
                    )
                except pymysql.err.OperationalError as exc:
                    if exc.args[0] != 1060:  # 1060 = Duplicate column name
                        raise

                for column_name in ("pinned", "archived"):
                    try:
                        cursor.execute(
                            f"ALTER TABLE conversations ADD COLUMN {column_name} "
                            "TINYINT(1) NOT NULL DEFAULT 0"
                        )
                    except pymysql.err.OperationalError as exc:
                        if exc.args[0] != 1060:
                            raise

                self._create_readable_views(cursor)

    def _create_readable_views(self, cursor) -> None:
        """Plain tables store sheet rows and chat messages as one big JSON blob
        column, which is fast to work with in code but unreadable in a DB
        browser. These views pull the common fields out into real columns —
        for humans poking around in phpMyAdmin/HeidiSQL/etc, not used by the
        app itself."""
        cursor.execute(
            """
            CREATE OR REPLACE VIEW v_sheet_rows AS
            SELECT
                id,
                source,
                row_index,
                JSON_UNQUOTE(JSON_EXTRACT(data, '$.product_name')) AS product_name,
                JSON_UNQUOTE(JSON_EXTRACT(data, '$.vendor_name')) AS vendor_name,
                JSON_UNQUOTE(JSON_EXTRACT(data, '$.width')) AS width,
                JSON_UNQUOTE(JSON_EXTRACT(data, '$.height')) AS height,
                JSON_UNQUOTE(JSON_EXTRACT(data, '$.quantity')) AS quantity,
                JSON_UNQUOTE(JSON_EXTRACT(data, '$.material')) AS material,
                JSON_UNQUOTE(JSON_EXTRACT(data, '$.due_date')) AS due_date,
                updated_at,
                data AS raw_data
            FROM sheet_rows
            ORDER BY source, row_index
            """
        )
        cursor.execute(
            """
            CREATE OR REPLACE VIEW v_chat_messages AS
            SELECT
                cm.id,
                cm.conversation_id,
                c.title AS conversation_title,
                JSON_UNQUOTE(JSON_EXTRACT(cm.data, '$.role')) AS role,
                JSON_UNQUOTE(JSON_EXTRACT(cm.data, '$.type')) AS type,
                COALESCE(
                    JSON_UNQUOTE(JSON_EXTRACT(cm.data, '$.text')),
                    JSON_UNQUOTE(JSON_EXTRACT(cm.data, '$.row.product_name')),
                    CONCAT(JSON_LENGTH(JSON_EXTRACT(cm.data, '$.issues')), ' issue(s)')
                ) AS summary,
                cm.created_at,
                cm.data AS raw_data
            FROM chat_messages cm
            JOIN conversations c ON c.id = cm.conversation_id
            ORDER BY cm.id
            """
        )

    def mark_processed(self, file_name: str) -> None:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO processed_files (file_name, processed_at) VALUES (%s, NOW()) "
                    "ON DUPLICATE KEY UPDATE processed_at = NOW()",
                    (file_name,),
                )

    def list_processed_files(self) -> list[str]:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT file_name FROM processed_files ORDER BY file_name")
                rows = cursor.fetchall()
        return [row["file_name"] for row in rows]

    def save_rows(self, source: str, rows: list[dict[str, Any]]) -> None:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM sheet_rows WHERE source = %s", (source,))
                if rows:
                    cursor.executemany(
                        "INSERT INTO sheet_rows (source, row_index, data, updated_at) "
                        "VALUES (%s, %s, %s, NOW())",
                        [
                            (source, index, json.dumps(row, ensure_ascii=False))
                            for index, row in enumerate(rows)
                        ],
                    )

    def get_all_rows(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT source, row_index, data FROM sheet_rows ORDER BY source, row_index"
                )
                records = cursor.fetchall()
        return [
            {"source": record["source"], "row_index": record["row_index"], **json.loads(record["data"])}
            for record in records
        ]

    def link_sheet(self, url: str, sheet_id: str, gid: str | None) -> None:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO linked_sheets (sheet_id, gid, url, linked_at) "
                    "VALUES (%s, %s, %s, NOW()) "
                    "ON DUPLICATE KEY UPDATE url = VALUES(url), linked_at = NOW()",
                    (sheet_id, gid or "", url),
                )

    def list_linked_sheets(self) -> list[dict[str, str | None]]:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT sheet_id, gid, url FROM linked_sheets ORDER BY linked_at"
                )
                records = cursor.fetchall()
        return [
            {"sheet_id": r["sheet_id"], "gid": r["gid"] or None, "url": r["url"]}
            for r in records
        ]

    def create_conversation(self, title: str = "New chat") -> dict[str, Any]:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO conversations (title, created_at, updated_at) "
                    "VALUES (%s, NOW(), NOW())",
                    (title,),
                )
                conversation_id = cursor.lastrowid
                cursor.execute(
                    "SELECT id, title, updated_at FROM conversations WHERE id = %s",
                    (conversation_id,),
                )
                return cursor.fetchone()

    def list_conversations(self, *, archived: bool = False) -> list[dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT id, title, pinned, archived, updated_at FROM conversations "
                    "WHERE archived = %s ORDER BY pinned DESC, updated_at DESC",
                    (1 if archived else 0,),
                )
                return cursor.fetchall()

    def update_conversation(
        self,
        conversation_id: int,
        *,
        title: str | None = None,
        pinned: bool | None = None,
        archived: bool | None = None,
    ) -> dict[str, Any]:
        updates: list[str] = []
        values: list[Any] = []
        if title is not None:
            clean_title = " ".join(title.split()) or "New chat"
            updates.append("title = %s")
            values.append(clean_title[:255])
        if pinned is not None:
            updates.append("pinned = %s")
            values.append(1 if pinned else 0)
        if archived is not None:
            updates.append("archived = %s")
            values.append(1 if archived else 0)

        if not updates:
            return self.get_conversation(conversation_id)

        values.append(conversation_id)
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"UPDATE conversations SET {', '.join(updates)} WHERE id = %s",
                    values,
                )
        return self.get_conversation(conversation_id)

    def get_conversation(self, conversation_id: int) -> dict[str, Any]:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT id, title, pinned, archived, updated_at "
                    "FROM conversations WHERE id = %s",
                    (conversation_id,),
                )
                row = cursor.fetchone()
        if row is None:
            raise ValueError(f"Conversation {conversation_id} not found")
        return row

    def delete_conversation(self, conversation_id: int) -> None:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM chat_messages WHERE conversation_id = %s", (conversation_id,)
                )
                cursor.execute("DELETE FROM conversations WHERE id = %s", (conversation_id,))

    def set_initial_title(self, conversation_id: int, title: str) -> None:
        """Only rename a conversation away from its default placeholder — once a
        real title has been set (e.g. from the first message), later calls no-op,
        the same way ChatGPT locks in a thread's title after the first turn."""
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE conversations SET title = %s "
                    "WHERE id = %s AND title = 'New chat'",
                    (title[:255], conversation_id),
                )

    def append_messages(self, conversation_id: int, messages: list[dict[str, Any]]) -> None:
        if not messages:
            return
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.executemany(
                    "INSERT INTO chat_messages (conversation_id, data, created_at) "
                    "VALUES (%s, %s, NOW())",
                    [
                        (conversation_id, json.dumps(message, ensure_ascii=False))
                        for message in messages
                    ],
                )
                cursor.execute(
                    "UPDATE conversations SET updated_at = NOW() WHERE id = %s",
                    (conversation_id,),
                )

    def update_message_and_delete_after(
        self, conversation_id: int, message_id: int, message: dict[str, Any]
    ) -> None:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT data FROM chat_messages WHERE id = %s AND conversation_id = %s",
                    (message_id, conversation_id),
                )
                existing = cursor.fetchone()
                if existing is None:
                    raise ValueError(f"Message {message_id} not found")
                existing_message = json.loads(existing["data"])
                if existing_message.get("role") != "user" or existing_message.get("type") != "text":
                    raise ValueError("Only user text messages can be edited")

                cursor.execute(
                    "UPDATE chat_messages SET data = %s WHERE id = %s AND conversation_id = %s",
                    (json.dumps(message, ensure_ascii=False), message_id, conversation_id),
                )
                cursor.execute(
                    "DELETE FROM chat_messages WHERE conversation_id = %s AND id > %s",
                    (conversation_id, message_id),
                )
                cursor.execute(
                    "UPDATE conversations SET updated_at = NOW() WHERE id = %s",
                    (conversation_id,),
                )

    def list_messages(self, conversation_id: int) -> list[dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT id, data FROM chat_messages WHERE conversation_id = %s ORDER BY id",
                    (conversation_id,),
                )
                records = cursor.fetchall()
        messages = []
        for record in records:
            message = json.loads(record["data"])
            message["id"] = record["id"]
            messages.append(message)
        return messages
