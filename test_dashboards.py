"""
test_dashboards.py -- Verify improved Mentor and Mentee dashboard UI elements.
"""
import sqlite3, sys
from datetime import date, timedelta
from app import app
from database import init_db
from werkzeug.security import generate_password_hash

DB = "mentor_connect.db"

def seed():
    conn = sqlite3.connect(DB)
    conn.execute("PRAGMA foreign_keys = ON")
    c = conn.cursor()

    for t in ["mentorship_sessions", "mentorship_requests", "mentor_profiles", "users"]:
        c.execute(f"DELETE FROM {t}")

    c.execute("INSERT INTO users (id, name, email, password_hash, role) VALUES (1, 'Dr. Sarah Chen', 'sarah@test.com', ?, 'mentor')",
              (generate_password_hash("pass123"),))
    c.execute("INSERT INTO users (id, name, email, password_hash, role) VALUES (2, 'Alex Mentee', 'alex@test.com', ?, 'mentee')",
              (generate_password_hash("pass123"),))

    c.execute("""INSERT INTO mentor_profiles (user_id, title, company, bio, skills, experience)
                 VALUES (1, 'Senior Engineer', 'Google', 'Passionate about teaching.', 'Python, ML', '5 years')""")

    c.execute("""INSERT INTO mentorship_requests (id, mentee_id, mentor_id, message, status)
                 VALUES (1, 2, 1, 'I would love your guidance!', 'ACCEPTED')""")
    c.execute("""INSERT INTO mentorship_requests (id, mentee_id, mentor_id, message, status)
                 VALUES (2, 2, 1, 'Another request', 'PENDING')""")

    future = (date.today() + timedelta(days=7)).strftime("%Y-%m-%d")
    c.execute("""INSERT INTO mentorship_sessions (request_id, mentee_id, mentor_id, session_date, session_time, topic, status)
                 VALUES (1, 2, 1, ?, '14:00', 'Career Growth', 'SCHEDULED')""", (future,))

    conn.commit()
    conn.close()
    print("1. Seeded mentor, mentee, profile, requests, and session.")


def run_tests():
    init_db()
    seed()
    client = app.test_client()
    errors = []

    # --- MENTOR DASHBOARD ---
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["user_name"] = "Dr. Sarah Chen"
        sess["user_email"] = "sarah@test.com"
        sess["user_role"] = "mentor"

    resp = client.get("/mentor/dashboard")
    html = resp.data.decode("utf-8")

    mentor_checks = [
        ("Mentor dashboard status 200",         resp.status_code == 200),
        ("Welcome banner present",              "dashboard-welcome-banner" in html),
        ("Welcome shows mentor name",           "Dr. Sarah Chen" in html),
        ("Quick actions bar present",           "quick-actions-bar" in html),
        ("Profile completion card present",     "Profile Completion" in html or "profile-progress-card" in html),
        ("Completion percentage shown",         "%" in html),
        ("Pending requests shown",              "Pending" in html),
        ("Accepted mentees shown",              "Accepted" in html or "Mentees" in html),
        ("Upcoming sessions panel shown",       "Career Growth" in html or "Upcoming Sessions" in html),
        ("Requests panel shown",                "Requests" in html),
    ]

    print("\n--- Mentor Dashboard ---")
    for label, result in mentor_checks:
        mark = "PASS" if result else "FAIL"
        print(f"  [{mark}] {label}")
        if not result:
            errors.append(f"MENTOR: {label}")
    print(f"  INFO: Mentor dashboard loaded ({len(html)} bytes)")

    # --- MENTEE DASHBOARD ---
    with client.session_transaction() as sess:
        sess["user_id"] = 2
        sess["user_name"] = "Alex Mentee"
        sess["user_email"] = "alex@test.com"
        sess["user_role"] = "mentee"

    resp = client.get("/mentee/dashboard")
    html = resp.data.decode("utf-8")

    mentee_checks = [
        ("Mentee dashboard status 200",         resp.status_code == 200),
        ("Welcome banner present",              "dashboard-welcome-banner" in html),
        ("Welcome shows mentee name",           "Alex Mentee" in html),
        ("Quick actions bar present",           "quick-actions-bar" in html),
        ("Requests count section shown",        "Request" in html),
        ("Accepted mentors shown",              "Accepted" in html),
        ("Upcoming sessions panel shown",       "Career Growth" in html or "Upcoming Sessions" in html),
        ("Recommended mentors section shown",   "Recommended" in html or "recommended" in html.lower()),
        ("Book session button shown",           "Book" in html),
    ]

    print("\n--- Mentee Dashboard ---")
    for label, result in mentee_checks:
        mark = "PASS" if result else "FAIL"
        print(f"  [{mark}] {label}")
        if not result:
            errors.append(f"MENTEE: {label}")
    print(f"  INFO: Mentee dashboard loaded ({len(html)} bytes)")

    print()
    if errors:
        print(f"FAILED - {len(errors)} check(s) did not pass:")
        for e in errors:
            print(f"   * {e}")
        sys.exit(1)
    else:
        print("=" * 54)
        print("  ALL DASHBOARD TESTS PASSED!")
        print("=" * 54)


if __name__ == "__main__":
    run_tests()
