"""Version 3 keeps version 1 and version 2 rows."""

import sqlite3
from pathlib import Path

from umd.storage.database import SCHEMA_VERSION, Library


def test_version_2_rows_survive_and_gain_extractor_columns(tmp_path: Path):
    database = tmp_path / "library.sqlite"
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        CREATE TABLE schema_meta (version INTEGER NOT NULL);
        INSERT INTO schema_meta(version) VALUES (2);
        CREATE TABLE jobs (
            id TEXT PRIMARY KEY,
            page_url TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            completed_at TEXT
        );
        CREATE TABLE media_items (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
            page_url TEXT NOT NULL,
            media_url TEXT NOT NULL,
            title TEXT NOT NULL,
            classification TEXT NOT NULL,
            reasons TEXT NOT NULL,
            selected INTEGER NOT NULL,
            user_override TEXT NOT NULL DEFAULT '',
            download_status TEXT NOT NULL,
            saved_path TEXT NOT NULL DEFAULT '',
            byte_size INTEGER NOT NULL DEFAULT 0,
            error TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            completed_at TEXT,
            total_size INTEGER NOT NULL DEFAULT 0,
            downloaded_bytes INTEGER NOT NULL DEFAULT 4,
            retry_count INTEGER NOT NULL DEFAULT 1,
            etag TEXT NOT NULL DEFAULT 'abc',
            last_modified TEXT NOT NULL DEFAULT '',
            resume_capable INTEGER,
            priority INTEGER NOT NULL DEFAULT 2,
            part_path TEXT NOT NULL DEFAULT '',
            last_progress_at TEXT,
            note TEXT NOT NULL DEFAULT 'keep'
        );
        """
    )
    connection.execute("PRAGMA user_version = 2")
    connection.execute(
        "INSERT INTO jobs(id, page_url, status, created_at, completed_at) VALUES ('job', 'http://127.0.0.1/a', '완료', 't', 't2')"
    )
    connection.execute(
        """
        INSERT INTO media_items (
            id, job_id, page_url, media_url, title, classification, reasons, selected,
            download_status, created_at
        ) VALUES ('item', 'job', 'http://127.0.0.1/a', 'http://127.0.0.1/dot.png', 'Dot', 'content', '본문', 1, '완료', 't')
        """
    )
    connection.commit()
    connection.close()

    library = Library(str(database))
    assert library.schema_version == SCHEMA_VERSION == 3
    item = library.items("job")[0]
    assert item["title"] == "Dot"
    assert item["download_status"] == "완료"
    assert item["retry_count"] == 1
    assert item["etag"] == "abc"
    assert item["note"] == "keep"
    assert item["media_type"] == "image"
    assert item["original_url"] == "http://127.0.0.1/dot.png"
    assert item["media_reference"] == "http://127.0.0.1/dot.png"
    assert "s3cret-token" not in str(item)
    library.close()
