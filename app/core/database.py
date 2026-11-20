import sqlite3
from contextlib import contextmanager
from pathlib import Path
from app.core.config import DB_PATH


@contextmanager
def connect():
    path = Path(DB_PATH)

    if not path.is_absolute():
        path = Path(__file__).resolve().parents[2] / path

    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")

    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def ensure_column(db: sqlite3.Connection, table: str, col_name: str, col_def: str):
    info = db.execute(f"PRAGMA table_info({table})").fetchall()
    existing_cols = [r["name"] for r in info]
    if col_name not in existing_cols:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}")


def init_extensions(db: sqlite3.Connection):
    # Safe migrations on existing tables
    ensure_column(db, "sources", "user_id", "TEXT")
    ensure_column(db, "sources", "is_demo", "INTEGER DEFAULT 0")

    ensure_column(db, "tips", "user_id", "TEXT")
    ensure_column(db, "tips", "stock_name", "TEXT")
    ensure_column(db, "tips", "is_demo", "INTEGER DEFAULT 0")

    # New tables
    db.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        is_demo INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS conversations (
        conversation_id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        stage TEXT NOT NULL DEFAULT 'intake',
        questions_asked INTEGER NOT NULL DEFAULT 0,
        questions_max INTEGER NOT NULL DEFAULT 6,
        tip_id TEXT,
        asked_question_keys TEXT NOT NULL DEFAULT '[]',
        current_question_key TEXT,
        is_demo INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS messages (
        id TEXT PRIMARY KEY,
        conversation_id TEXT NOT NULL,
        role TEXT NOT NULL,
        blocks TEXT NOT NULL,
        image_url TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(conversation_id) REFERENCES conversations(conversation_id)
    );

    CREATE TABLE IF NOT EXISTS decisions (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        tip_id TEXT NOT NULL,
        action TEXT,
        timeframe_days INTEGER,
        exit_target REAL,
        max_loss_pct REAL,
        confidence INTEGER,
        thesis TEXT,
        gaps_count INTEGER DEFAULT 0,
        locked INTEGER DEFAULT 0,
        locked_at TEXT,
        is_demo INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id),
        FOREIGN KEY(tip_id) REFERENCES tips(tip_id)
    );

    CREATE TABLE IF NOT EXISTS investments (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        ticker TEXT NOT NULL,
        stock_name TEXT NOT NULL,
        quantity REAL NOT NULL,
        avg_price REAL NOT NULL,
        purchase_date TEXT NOT NULL,
        current_price REAL,
        current_value REAL,
        linked_tip_id TEXT,
        is_demo INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS investment_drafts (
        confirm_token TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        draft TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS alerts (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        type TEXT NOT NULL,
        title TEXT NOT NULL,
        body TEXT NOT NULL,
        tip_id TEXT NOT NULL,
        source_name TEXT NOT NULL,
        results TEXT NOT NULL,
        read INTEGER DEFAULT 0,
        is_demo INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS thesis_links (
        id TEXT PRIMARY KEY,
        conversation_id TEXT NOT NULL,
        tip_id TEXT NOT NULL,
        text TEXT NOT NULL,
        status TEXT NOT NULL,
        evidence TEXT,
        link_order INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        FOREIGN KEY(conversation_id) REFERENCES conversations(conversation_id)
    );

    CREATE INDEX IF NOT EXISTS idx_conversations_user ON conversations(user_id);
    CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id);
    CREATE INDEX IF NOT EXISTS idx_decisions_user ON decisions(user_id);
    CREATE INDEX IF NOT EXISTS idx_investments_user ON investments(user_id);
    CREATE INDEX IF NOT EXISTS idx_alerts_user ON alerts(user_id);
    CREATE INDEX IF NOT EXISTS idx_thesis_links_conv ON thesis_links(conversation_id);
    """)


def init_db():
    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS sources (
            source_id TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            source_type TEXT NOT NULL,
            sebi_registered INTEGER,
            data_origin TEXT NOT NULL CHECK(data_origin IN ('real', 'synthetic'))
        );

        CREATE TABLE IF NOT EXISTS tips (
            tip_id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL,
            posted_at TEXT NOT NULL,
            raw_text TEXT NOT NULL,
            language TEXT,
            ticker TEXT NOT NULL,
            direction TEXT NOT NULL,
            target_price REAL,
            horizon_days INTEGER,
            confidence_words TEXT NOT NULL DEFAULT '[]',
            extraction_conf REAL,
            data_origin TEXT NOT NULL,
            FOREIGN KEY(source_id) REFERENCES sources(source_id)
        );

        CREATE TABLE IF NOT EXISTS scored_tips (
            tip_id TEXT PRIMARY KEY,
            outcome TEXT,
            entry_price REAL,
            exit_price REAL,
            return_pct REAL,
            cost_pct REAL,
            benchmark_return_pct REAL,
            excess_return REAL,
            hit INTEGER,
            scored_at TEXT,
            FOREIGN KEY(tip_id) REFERENCES tips(tip_id)
        );

        CREATE TABLE IF NOT EXISTS source_stats (
            source_id TEXT PRIMARY KEY,
            n_tips INTEGER DEFAULT 0,
            n_hits INTEGER DEFAULT 0,
            post_mean REAL,
            ci_low REAL,
            ci_high REAL,
            evidence_level TEXT,
            avg_excess_return REAL,
            brier REAL,
            raw_hit_rate REAL,
            shrunk_hit_rate REAL,
            overconfidence_gap REAL,
            FOREIGN KEY(source_id) REFERENCES sources(source_id)
        );

        CREATE TABLE IF NOT EXISTS coord_edges (
            edge_id TEXT PRIMARY KEY,
            ticker TEXT,
            source_a TEXT,
            source_b TEXT,
            delta_hours REAL,
            window_id TEXT
        );

        CREATE TABLE IF NOT EXISTS coord_flags (
            flag_id TEXT PRIMARY KEY,
            ticker TEXT,
            window_start TEXT,
            window_end TEXT,
            n_sources INTEGER,
            volume_z REAL,
            price_move_pct REAL,
            post_window_move_pct REAL,
            data_origin TEXT
        );

        CREATE TABLE IF NOT EXISTS archive_chain (
            seq INTEGER PRIMARY KEY,
            tip_id TEXT,
            tip_hash TEXT,
            prev_hash TEXT,
            chain_hash TEXT,
            ts TEXT,
            anchor_tx TEXT
        );

        CREATE TABLE IF NOT EXISTS eval_sessions (
            session_id TEXT PRIMARY KEY,
            arm TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS eval_items (
            item_id TEXT PRIMARY KEY,
            session_id TEXT,
            tip_id TEXT,
            item_order INTEGER
        );

        CREATE TABLE IF NOT EXISTS eval_decisions (
            session_id TEXT,
            item_id TEXT,
            decision TEXT,
            confidence INTEGER,
            position_pct REAL,
            decided_at TEXT,
            PRIMARY KEY(session_id, item_id)
        );

        CREATE INDEX IF NOT EXISTS idx_tips_source ON tips(source_id);
        CREATE INDEX IF NOT EXISTS idx_tips_ticker ON tips(ticker);
        CREATE INDEX IF NOT EXISTS idx_tips_posted_at ON tips(posted_at);
        CREATE INDEX IF NOT EXISTS idx_coord_edges_ticker ON coord_edges(ticker);
        CREATE INDEX IF NOT EXISTS idx_coord_flags_window ON coord_flags(window_start);
        CREATE INDEX IF NOT EXISTS idx_eval_items_session ON eval_items(session_id);
        CREATE INDEX IF NOT EXISTS idx_archive_chain_tip ON archive_chain(tip_id);
        """)

        init_extensions(db)
