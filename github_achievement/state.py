import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


class RunLock:
    """An OS lock is released automatically if the process exits or crashes."""
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "run.lock"

    def __enter__(self):
        self.file = self.path.open("a+b")
        self.file.seek(0, 2)
        if self.file.tell() == 0:
            self.file.write(b"0")
            self.file.flush()
        self.file.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            raise ValueError("Another run is using this state directory. Wait for it to finish.") from None
        return self

    def __exit__(self, *args):
        self.file.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_UN)
        finally:
            self.file.close()


class StateStore:
    """Durable operation journal, scoped to the authenticated account and repo."""
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute("""CREATE TABLE IF NOT EXISTS operations (
            id TEXT PRIMARY KEY, account TEXT NOT NULL, repo TEXT NOT NULL,
            workflow TEXT NOT NULL, status TEXT NOT NULL, started_at TEXT NOT NULL,
            updated_at TEXT NOT NULL, detail TEXT NOT NULL
        )""")
        self.db.commit()

    def close(self):
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    @staticmethod
    def now():
        return datetime.now(timezone.utc).isoformat()

    def start(self, account: str, repo: str, workflow: str) -> str:
        operation_id = uuid.uuid4().hex
        now = self.now()
        with self.db:
            self.db.execute("INSERT INTO operations VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                            (operation_id, account.lower(), repo.lower(), workflow,
                             "running", now, now, "{}"))
        return operation_id

    def checkpoint(self, operation_id, **detail):
        row = self.db.execute("SELECT detail FROM operations WHERE id=?", (operation_id,)).fetchone()
        existing = json.loads(row[0])
        existing.update(detail)
        with self.db:
            self.db.execute("UPDATE operations SET detail=?, updated_at=? WHERE id=?",
                            (json.dumps(existing), self.now(), operation_id))

    def finish(self, operation_id, status="completed", **detail):
        self.checkpoint(operation_id, **detail)
        with self.db:
            self.db.execute("UPDATE operations SET status=?, updated_at=? WHERE id=?",
                            (status, self.now(), operation_id))

    def count(self, account, repo, workflow):
        return self.db.execute("""SELECT COUNT(*) FROM operations
            WHERE account=? AND repo=? AND workflow=? AND status='completed'""",
            (account.lower(), repo.lower(), workflow)).fetchone()[0]

    def history(self, *, account=None, repo=None, limit=25):
        filters, params = [], []
        for column, value in (("account", account), ("repo", repo)):
            if value:
                filters.append(f"{column}=?")
                params.append(value.lower())
        where = " WHERE " + " AND ".join(filters) if filters else ""
        rows = self.db.execute("SELECT * FROM operations" + where + " ORDER BY started_at DESC LIMIT ?",
                               (*params, limit)).fetchall()
        columns = ("id", "account", "repo", "workflow", "status", "started_at", "updated_at", "detail")
        results = [dict(zip(columns, row)) for row in rows]
        for result in results:
            result["detail"] = json.loads(result["detail"])
        return results

    def summary(self, *, account=None, repo=None):
        filters, params = [], []
        for column, value in (("account", account), ("repo", repo)):
            if value:
                filters.append(f"{column}=?")
                params.append(value.lower())
        where = " WHERE " + " AND ".join(filters) if filters else ""
        rows = self.db.execute("""SELECT account, repo, workflow, status, COUNT(*)
            FROM operations""" + where + " GROUP BY account, repo, workflow, status ORDER BY account, repo, workflow, status",
            params).fetchall()
        return [dict(zip(("account", "repo", "workflow", "status", "count"), row)) for row in rows]
