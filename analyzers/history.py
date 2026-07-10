import sqlite3
import json
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "history.db"


def _get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _init_db(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audits (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            domain      TEXT    NOT NULL,
            audited_at  TEXT    NOT NULL,
            overall     REAL    NOT NULL,
            scores_json TEXT    NOT NULL
        )
    """)
    conn.commit()


def save_audit(domain: str, scores: dict):
    """Persist audit scores for a domain."""
    overall = scores.get("overall", 0)
    conn = _get_conn()
    _init_db(conn)
    conn.execute(
        "INSERT INTO audits (domain, audited_at, overall, scores_json) VALUES (?,?,?,?)",
        (domain, datetime.utcnow().isoformat(), overall, json.dumps(scores)),
    )
    conn.commit()
    conn.close()


def get_history(domain: str, limit: int = 12) -> list[dict]:
    """Return up to `limit` past audits for a domain, oldest first."""
    conn = _get_conn()
    _init_db(conn)
    rows = conn.execute(
        "SELECT audited_at, overall, scores_json FROM audits "
        "WHERE domain = ? ORDER BY audited_at DESC LIMIT ?",
        (domain, limit),
    ).fetchall()
    conn.close()

    results = []
    for row in reversed(rows):
        s = json.loads(row["scores_json"])
        results.append({
            "date": row["audited_at"][:10],
            "overall": row["overall"],
            "category_scores": s.get("category_scores", {}),
        })
    return results


def build_progress(history: list[dict]) -> dict:
    """Compare latest vs previous audit and return diff data."""
    if len(history) < 2:
        return {"has_history": False, "history": history}

    prev = history[-2]
    curr = history[-1]

    cats = list(curr["category_scores"].keys())
    category_diff = {}
    for cat in cats:
        c_score = curr["category_scores"].get(cat, {}).get("score", 0)
        p_score = prev["category_scores"].get(cat, {}).get("score", 0)
        diff = round(c_score - p_score, 1)
        category_diff[cat] = {
            "prev": round(p_score, 1),
            "curr": round(c_score, 1),
            "diff": diff,
            "arrow": "↑" if diff > 0 else ("↓" if diff < 0 else "→"),
        }

    overall_diff = round(curr["overall"] - prev["overall"], 1)

    return {
        "has_history": True,
        "history": history,
        "prev_date": prev["date"],
        "curr_date": curr["date"],
        "overall_prev": round(prev["overall"], 1),
        "overall_curr": round(curr["overall"], 1),
        "overall_diff": overall_diff,
        "overall_arrow": "↑" if overall_diff > 0 else ("↓" if overall_diff < 0 else "→"),
        "category_diff": category_diff,
        "audits_count": len(history),
    }
