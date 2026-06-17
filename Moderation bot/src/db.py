import os
import sqlite3
from datetime import datetime
from typing import List, Dict, Any

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, 'data', 'tokens.db')


def ensure_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        '''
        CREATE TABLE IF NOT EXISTS tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token TEXT UNIQUE NOT NULL,
            label TEXT,
            added_at TEXT NOT NULL
        )
        '''
    )
    conn.commit()
    conn.close()


def add_token_sync(token: str, label: str | None = None) -> bool:
    ensure_db()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    try:
        cur.execute('INSERT INTO tokens (token, label, added_at) VALUES (?, ?, ?)',
                    (token, label, datetime.utcnow().isoformat()))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def list_tokens_sync() -> List[Dict[str, Any]]:
    ensure_db()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('SELECT id, token, label, added_at FROM tokens ORDER BY id ASC')
    rows = cur.fetchall()
    conn.close()
    return [dict(id=r[0], token=r[1], label=r[2], added_at=r[3]) for r in rows]


def get_tokens_sync() -> List[str]:
    ensure_db()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('SELECT token FROM tokens ORDER BY id ASC')
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]


def remove_token_sync(token: str) -> bool:
    ensure_db()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('DELETE FROM tokens WHERE token = ?', (token,))
    changed = cur.rowcount
    conn.commit()
    conn.close()
    return changed > 0


def remove_token_by_id_sync(row_id: int) -> bool:
    ensure_db()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('DELETE FROM tokens WHERE id = ?', (row_id,))
    changed = cur.rowcount
    conn.commit()
    conn.close()
    return changed > 0


def export_to_config_sync(path: str = os.path.join(os.getcwd(), 'data', 'config.json')) -> None:
    # write tokens into config.json under 'tokens' key
    rows = list_tokens_sync()
    tokens = [r['token'] for r in rows]
    config = {}
    if os.path.exists(path):
        try:
            import json
            with open(path, 'r') as f:
                config = json.load(f)
        except Exception:
            config = {}
    config['tokens'] = tokens
    import json
    with open(path, 'w') as f:
        json.dump(config, f, indent=2)


def import_from_config_sync(path: str = os.path.join(os.getcwd(), 'data', 'config.json')) -> int:
    # read tokens from config and insert into DB, return number added
    if not os.path.exists(path):
        return 0
    import json
    with open(path, 'r') as f:
        cfg = json.load(f)
    toks = cfg.get('tokens', [])
    added = 0
    for t in toks:
        if add_token_sync(t, None):
            added += 1
    return added
