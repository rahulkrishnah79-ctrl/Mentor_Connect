import sqlite3
import os
from werkzeug.security import generate_password_hash

DB_NAME = os.path.join(os.path.dirname(__file__), 'mentor_connect.db')
UPLOAD_BASE = os.path.join(os.path.dirname(__file__), 'secure_uploads')

def get_db_connection():
    """
    Creates and returns a connection to the SQLite database.
    Enables foreign keys and uses Row factory for dict-like access.
    """
    conn = sqlite3.connect(DB_NAME)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """
    Initializes the database using schema.sql and runs safe migrations.
    Creates secure upload directories and ensures an initial administrator exists.
    """
    # Ensure private secure upload directories exist (outside static)
    os.makedirs(os.path.join(UPLOAD_BASE, 'id_proofs'), exist_ok=True)
    os.makedirs(os.path.join(UPLOAD_BASE, 'college_ids'), exist_ok=True)

    schema_path = os.path.join(os.path.dirname(__file__), 'schema.sql')
    with open(schema_path, mode='r', encoding='utf-8') as f:
        schema_sql = f.read()

    conn = get_db_connection()
    conn.executescript(schema_sql)

    # Safe migration: Add any missing verification columns to existing users table
    cursor = conn.execute("PRAGMA table_info(users);")
    existing_cols = [row[1] for row in cursor.fetchall()]

    new_cols = [
        ("college_name", "TEXT"),
        ("college_email", "TEXT"),
        ("verification_status", "TEXT NOT NULL DEFAULT 'Verified'"),
        ("id_proof_filename", "TEXT"),
        ("college_id_filename", "TEXT"),
        ("verified_at", "TIMESTAMP"),
        ("admin_notes", "TEXT"),
        ("is_admin", "INTEGER DEFAULT 0"),
    ]

    for col_name, col_def in new_cols:
        if col_name not in existing_cols:
            conn.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_def};")

    # Ensure existing users with NULL or empty status default to 'Verified'
    conn.execute("UPDATE users SET verification_status = 'Verified' WHERE verification_status IS NULL OR verification_status = '';")

    # Seed default platform administrator account if not present
    admin_row = conn.execute("SELECT id FROM users WHERE email = 'admin@mentorconnect.com'").fetchone()
    if not admin_row:
        conn.execute("""
            INSERT INTO users (name, email, password_hash, role, is_admin, verification_status)
            VALUES ('Platform Administrator', 'admin@mentorconnect.com', ?, 'mentor', 1, 'Verified')
        """, (generate_password_hash('admin123'),))

    conn.commit()
    conn.close()
    print("Database verified and initialized successfully.")

if __name__ == '__main__':
    init_db()
