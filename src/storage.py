import os
import sqlite3
from typing import List

DB_PATH = os.path.join(os.getcwd(), 'data', 'tokens.db')


def init_db(path: str = DB_PATH) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS tokens (id INTEGER PRIMARY KEY AUTOINCREMENT, token TEXT UNIQUE NOT NULL)"
    )
    conn.commit()
    return conn


def add_token(token: str, path: str = DB_PATH) -> bool:
    conn = init_db(path)
    try:
        conn.execute("INSERT INTO tokens (token) VALUES (?)", (token,))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def get_tokens(path: str = DB_PATH) -> List[str]:
    conn = init_db(path)
    cursor = conn.execute("SELECT token FROM tokens ORDER BY id")
    tokens = [row[0] for row in cursor.fetchall()]
    conn.close()
    return tokens


def token_exists(token: str, path: str = DB_PATH) -> bool:
    conn = init_db(path)
    cursor = conn.execute("SELECT 1 FROM tokens WHERE token = ? LIMIT 1", (token,))
    found = cursor.fetchone() is not None
    conn.close()
    return found
