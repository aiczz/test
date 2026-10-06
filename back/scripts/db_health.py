"""数据库体检：确认 shishi.db 是好的、干净收尾的。

用在两个时机：
  · 打包/拷贝这个文件夹之前（确认没有进程占着、没有遗留的 -wal/-shm）
  · 停掉后端之后（确认上次是正常关闭，不是崩溃留下的半截状态）
"""

from __future__ import annotations

import pathlib
import sqlite3
import sys

DB = pathlib.Path(__file__).resolve().parents[1] / "shishi.db"


def main() -> int:
    if not DB.exists():
        print(f"[x] 找不到 {DB}")
        return 1

    print(f"文件：{DB}")
    print(f"大小：{DB.stat().st_size / 1024 / 1024:.1f} MB")

    # 有没有残留的 WAL / SHM / 锁文件
    leftovers = sorted(
        p.name for p in DB.parent.glob("shishi.db*") if p.name != DB.name
    )
    if leftovers:
        print(f"[!] 有残留文件：{leftovers}")
        print("    正常情况下后端关闭时 SQLite 会把 WAL 合并回主库并删掉它们。")
    else:
        print("[ok] 没有残留的 -wal / -shm（上次是干净收尾）")

    # 有没有被进程占用
    try:
        with open(DB, "rb+") as handle:
            handle.seek(0)
            handle.read(64)
        print("[ok] 可以独占打开 —— 没有进程占用，可以放心压缩/拷贝")
    except PermissionError as exc:
        print(f"[x] 仍被占用：{exc}")
        print("    先停掉后端（Ctrl+C 或结束 python 进程）再打包。")
        return 1

    connection = sqlite3.connect(str(DB))
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        journal = connection.execute("PRAGMA journal_mode").fetchone()[0]
        print(f"[{'ok' if integrity == 'ok' else 'x'}] 完整性检查：{integrity}")
        print(f"    日志模式：{journal}")

        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
            )
        ]
        print(f"    表数量：{len(tables)}")
        for name in ("ingredients", "dishes", "dish_ingredients", "users",
                     "user_preferences"):
            if name in tables:
                count = connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
                print(f"      {name:<20} {count} 行")
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
