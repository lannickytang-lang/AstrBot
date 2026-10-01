#!/usr/bin/env python3
"""Export WeChat customer-service chats from AstrBot SQLite to CSV.

Usage: python3 export_chats.py [output_csv]
Default output: /root/exports/chats_<date>.csv
"""
import csv
import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

DB = Path("/root/apps/yuansheng-astrbot/data/data_v4.db")
OUT_DIR = Path("/root/exports")


def main() -> None:
    out = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else OUT_DIR / f"chats_{date.today():%Y%m%d}.csv"
    )
    out.parent.mkdir(parents=True, exist_ok=True)

    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    sessions = con.execute(
        "SELECT user_id, updated_at, content FROM conversations "
        "WHERE platform_id='wecom' ORDER BY updated_at"
    ).fetchall()
    con.close()

    n_rows = 0
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["customer_id", "role", "content", "session_updated_at"])
        for user_id, updated_at, content in sessions:
            customer = user_id.split(":")[-1]
            try:
                history = json.loads(content) if content else []
            except json.JSONDecodeError:
                continue
            for msg in history:
                role = msg.get("role", "?")
                parts = msg.get("content")
                if not isinstance(parts, list):
                    parts = [{"type": "text", "text": str(parts)}]
                for part in parts:
                    text = str(part.get("text", ""))
                    # skip RAG/system prompt injections inside user messages
                    if part.get("type") == "text" and text.startswith("<system"):
                        continue
                    if part.get("type") == "think":
                        role_out = "assistant_think"
                    else:
                        role_out = role
                    if not text.strip():
                        continue
                    w.writerow([customer, role_out, text, updated_at])
                    n_rows += 1

    print(f"exported {n_rows} rows, {len(sessions)} sessions -> {out}")


if __name__ == "__main__":
    main()
