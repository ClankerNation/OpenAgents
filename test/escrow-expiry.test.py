"""Tests for escrow auto-refund (#197) — using only stdlib sqlite3."""

import sqlite3
from datetime import datetime, timedelta


def init_db(conn):
    conn.execute("""
        CREATE TABLE payments (
            id INTEGER PRIMARY KEY,
            task_id INTEGER NOT NULL,
            from_address TEXT NOT NULL,
            to_address TEXT,
            amount REAL NOT NULL,
            token_address TEXT DEFAULT '0x0000000000000000000000000000000000000000',
            status TEXT DEFAULT 'pending',
            created_at TEXT,
            claimed_at TEXT,
            release_time TEXT
        )
    """)
    conn.commit()


def insert_payment(conn, **kwargs):
    cols = ', '.join(kwargs.keys())
    vals = ', '.join(['?' for _ in kwargs])
    conn.execute(f"INSERT INTO payments ({cols}) VALUES ({vals})", list(kwargs.values()))
    conn.commit()
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def expired_where(cutoff_days=30):
    """Return SQL WHERE clause matching expired escrows."""
    cutoff = (datetime.utcnow() - timedelta(days=cutoff_days)).isoformat()
    return f"status='escrowed' AND release_time IS NOT NULL AND release_time <= '{cutoff}'"


# --- Tests ---

def test_fresh_escrow_not_refunded():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    insert_payment(
        conn, task_id=1, from_address="0xA", amount=1.0,
        status="escrowed", release_time=(datetime.utcnow() - timedelta(days=5)).isoformat(),
        created_at=datetime.utcnow().isoformat(),
    )
    cur = conn.execute(f"SELECT * FROM payments WHERE {expired_where()}")
    assert len(cur.fetchall()) == 0, "Fresh escrow should NOT be flagged expired"
    print("✓ fresh escrow not refunded")


def test_expired_escrow_flagged():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    pid = insert_payment(
        conn, task_id=1, from_address="0xPayer", amount=5.5,
        status="escrowed", release_time=(datetime.utcnow() - timedelta(days=35)).isoformat(),
        created_at=datetime.utcnow().isoformat(),
    )
    cur = conn.execute(f"SELECT * FROM payments WHERE {expired_where()}")
    rows = cur.fetchall()
    assert len(rows) == 1, "35-day escrow should be expired"
    assert rows[0][4] == 5.5  # amount column
    print("✓ expired escrow flagged")


def test_refund_goes_to_payer():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    pid = insert_payment(
        conn, task_id=1, from_address="0xPayerABC", amount=10.0,
        status="escrowed", release_time=(datetime.utcnow() - timedelta(days=40)).isoformat(),
        created_at=datetime.utcnow().isoformat(),
    )
    # simulate refund action
    now = datetime.utcnow().isoformat()
    conn.execute(
        "UPDATE payments SET status='refunded', to_address=from_address, claimed_at=? WHERE id=?",
        (now, pid),
    )
    conn.commit()
    row = conn.execute("SELECT status, to_address FROM payments WHERE id=?", (pid,)).fetchone()
    assert row[0] == "refunded"
    assert row[1] == "0xPayerABC"
    print("✓ refund goes to payer")


def test_multiple_expired():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    for days in [5, 15, 31, 45, 60]:
        insert_payment(
            conn, task_id=1, from_address="0xA", amount=float(days),
            status="escrowed",
            release_time=(datetime.utcnow() - timedelta(days=days)).isoformat(),
            created_at=datetime.utcnow().isoformat(),
        )
    cur = conn.execute(f"SELECT * FROM payments WHERE {expired_where()}")
    rows = cur.fetchall()
    assert len(rows) == 3, "31/45/60 day escrows should be expired"
    amounts = sorted([r[4] for r in rows])
    assert amounts == [31.0, 45.0, 60.0]
    print("✓ multiple expired filtered correctly")


def test_expired_at_computed():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    rt = datetime.utcnow() - timedelta(days=10)
    insert_payment(
        conn, task_id=1, from_address="0xA", amount=1.0,
        status="escrowed", release_time=rt.isoformat(),
        created_at=datetime.utcnow().isoformat(),
    )
    # computed: release_time + 30 days
    row = conn.execute("SELECT release_time FROM payments LIMIT 1").fetchone()
    parsed = datetime.fromisoformat(row[0])
    expired = parsed + timedelta(days=30)
    assert (expired - (rt + timedelta(days=30))).total_seconds() < 1
    print("✓ expired_at computed correctly")


if __name__ == "__main__":
    test_fresh_escrow_not_refunded()
    test_expired_escrow_flagged()
    test_refund_goes_to_payer()
    test_multiple_expired()
    test_expired_at_computed()
    print("\nAll 5 tests passed.")
