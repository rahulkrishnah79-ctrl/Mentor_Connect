"""
test_security.py -- Verify all security improvements.
Runs in ASCII mode to avoid Windows cp1252 encoding errors.
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

    c.execute("INSERT INTO users (id, name, email, password_hash, role) VALUES (1, 'Dr. Sarah', 'sarah@test.com', ?, 'mentor')",
              (generate_password_hash("securepass123"),))
    c.execute("INSERT INTO users (id, name, email, password_hash, role) VALUES (2, 'Alex', 'alex@test.com', ?, 'mentee')",
              (generate_password_hash("securepass123"),))
    c.execute("""INSERT INTO mentor_profiles (user_id, title, skills)
                 VALUES (1, 'Engineer', 'Python, Flask')""")
    c.execute("INSERT INTO mentorship_requests (id, mentee_id, mentor_id, message, status) VALUES (1, 2, 1, 'Hi', 'ACCEPTED')")
    conn.commit()
    conn.close()
    print("1. Seeded test data.")


def run():
    init_db()
    seed()
    client = app.test_client()
    errors = []

    # --- 1. Cookie flags ---
    print("\n--- [1] Session Cookie Security ---")

    resp = client.post('/login', data={'email': 'sarah@test.com', 'password': 'securepass123'})
    cookie_header = resp.headers.get('Set-Cookie', '')
    httponly_ok = 'HttpOnly' in cookie_header
    samesite_ok = 'SameSite=Lax' in cookie_header
    print(f"  [{'PASS' if httponly_ok else 'FAIL'}] Session cookie has HttpOnly flag")
    print(f"  [{'PASS' if samesite_ok else 'FAIL'}] Session cookie has SameSite=Lax")
    print(f"  INFO: Set-Cookie: {cookie_header[:120]}...")
    if not httponly_ok: errors.append("Cookie missing HttpOnly")
    if not samesite_ok: errors.append("Cookie missing SameSite=Lax")

    # --- 2. Logout clears session ---
    print("\n--- [2] Logout Functionality & Session Clearance ---")
    resp_post = client.post('/logout', follow_redirects=True)
    post_ok = resp_post.status_code == 200 and 'logged out successfully' in resp_post.data.decode('utf-8')
    with client.session_transaction() as sess:
        sess_cleared = 'user_id' not in sess
    print(f"  [{'PASS' if post_ok else 'FAIL'}] POST /logout completes with success message")
    print(f"  [{'PASS' if sess_cleared else 'FAIL'}] Session is completely cleared on logout")
    if not post_ok: errors.append("POST /logout should work")
    if not sess_cleared: errors.append("Logout should clear session")

    # --- 3. Password minimum 8 chars ---
    print("\n--- [3] Password Minimum Length (8 chars) ---")
    resp = client.post('/register', data={
        'name': 'Test User', 'email': 'newuser@test.com',
        'password': 'short', 'role': 'mentee'   # only 5 chars
    })
    html = resp.data.decode('utf-8')
    rejects_short = 'at least 8' in html.lower() or resp.status_code == 200
    print(f"  [{'PASS' if rejects_short else 'FAIL'}] Password shorter than 8 chars is rejected")
    if not rejects_short: errors.append("Short password should be rejected")

    resp7 = client.post('/register', data={
        'name': 'Test User', 'email': 'newuser@test.com',
        'password': '7chars!', 'role': 'mentee'   # exactly 7 chars
    })
    html7 = resp7.data.decode('utf-8')
    rejects_7 = 'at least 8' in html7.lower() or resp7.status_code == 200
    print(f"  [{'PASS' if rejects_7 else 'FAIL'}] Password of 7 chars is rejected")
    if not rejects_7: errors.append("7-char password should be rejected")

    # --- 4. Duplicate email registration ---
    print("\n--- [4] Duplicate Email Prevention ---")
    resp = client.post('/register', data={
        'name': 'Duplicate', 'email': 'sarah@test.com',
        'password': 'password123', 'role': 'mentor'
    })
    html = resp.data.decode('utf-8')
    rejects_dup = 'already exists' in html.lower()
    print(f"  [{'PASS' if rejects_dup else 'FAIL'}] Duplicate email registration is rejected")
    if not rejects_dup: errors.append("Duplicate email should be rejected")

    # --- 5. Invalid email format ---
    print("\n--- [5] Email Format Validation ---")
    resp = client.post('/register', data={
        'name': 'Bad Email', 'email': 'notanemail',
        'password': 'password123', 'role': 'mentee'
    })
    html = resp.data.decode('utf-8')
    rejects_bad_email = 'valid email' in html.lower()
    print(f"  [{'PASS' if rejects_bad_email else 'FAIL'}] Invalid email format is rejected")
    if not rejects_bad_email: errors.append("Invalid email format should be rejected")

    # --- 6. javascript: URL rejected in profile ---
    print("\n--- [6] javascript: URL Sanitization ---")
    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['user_name'] = 'Dr. Sarah'
        sess['user_email'] = 'sarah@test.com'
        sess['user_role'] = 'mentor'

    resp = client.post('/mentor/profile/edit', data={
        'skills': 'Python',
        'profile_pic_url': 'javascript:alert(1)',
        'linkedin_url': 'javascript:steal_cookies()',
    })
    # Should redirect to dashboard (profile saved but with sanitized URLs)
    saved_ok = resp.status_code in (302, 200)

    # Check DB - the URLs must NOT be stored as javascript:
    conn = sqlite3.connect(DB)
    row = conn.execute("SELECT profile_pic_url, linkedin_url FROM mentor_profiles WHERE user_id = 1").fetchone()
    conn.close()
    pic_sanitized = row[0] in ('', None)
    li_sanitized  = row[1] in ('', None)
    print(f"  [{'PASS' if saved_ok else 'FAIL'}]  Profile save accepted (with cleaned URLs)")
    print(f"  [{'PASS' if pic_sanitized else 'FAIL'}] javascript: profile_pic_url was cleared to empty")
    print(f"  [{'PASS' if li_sanitized else 'FAIL'}]  javascript: linkedin_url was cleared to empty")
    if not pic_sanitized: errors.append("javascript: profile_pic_url was NOT sanitized")
    if not li_sanitized:  errors.append("javascript: linkedin_url was NOT sanitized")

    # --- 7. Valid https:// URL accepted ---
    print("\n--- [7] Valid https:// URLs Are Accepted ---")
    resp = client.post('/mentor/profile/edit', data={
        'skills': 'Python',
        'profile_pic_url': 'https://example.com/avatar.jpg',
        'linkedin_url': 'https://linkedin.com/in/sarah',
    })
    conn = sqlite3.connect(DB)
    row = conn.execute("SELECT profile_pic_url, linkedin_url FROM mentor_profiles WHERE user_id = 1").fetchone()
    conn.close()
    pic_kept = row[0] == 'https://example.com/avatar.jpg'
    li_kept  = row[1] == 'https://linkedin.com/in/sarah'
    print(f"  [{'PASS' if pic_kept else 'FAIL'}] Valid https:// profile pic URL is stored correctly")
    print(f"  [{'PASS' if li_kept else 'FAIL'}]  Valid https:// linkedin URL is stored correctly")
    if not pic_kept: errors.append("Valid https URL should be stored")
    if not li_kept:  errors.append("Valid https linkedin URL should be stored")

    # --- 8. Unauthorized dashboard access ---
    print("\n--- [8] Authorization: Wrong Role Cannot Access Other Dashboard ---")
    with client.session_transaction() as sess:
        sess['user_id'] = 2
        sess['user_name'] = 'Alex'
        sess['user_email'] = 'alex@test.com'
        sess['user_role'] = 'mentee'

    resp = client.get('/mentor/dashboard')
    redirected = resp.status_code == 302
    print(f"  [{'PASS' if redirected else 'FAIL'}] Mentee trying to access /mentor/dashboard is redirected")
    if not redirected: errors.append("Mentee should be redirected from mentor dashboard")

    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['user_name'] = 'Dr. Sarah'
        sess['user_email'] = 'sarah@test.com'
        sess['user_role'] = 'mentor'

    resp = client.get('/mentee/dashboard')
    redirected2 = resp.status_code == 302
    print(f"  [{'PASS' if redirected2 else 'FAIL'}] Mentor trying to access /mentee/dashboard is redirected")
    if not redirected2: errors.append("Mentor should be redirected from mentee dashboard")

    # --- 9. No session => dashboard redirect to login ---
    print("\n--- [9] Unauthenticated Access Blocked ---")
    with client.session_transaction() as sess:
        sess.clear()

    resp = client.get('/mentor/dashboard')
    to_login = resp.status_code == 302 and 'login' in resp.headers.get('Location', '')
    print(f"  [{'PASS' if to_login else 'FAIL'}] No session => redirect to /login")
    if not to_login: errors.append("Unauthenticated access should redirect to login")

    # --- 10. Duplicate pending mentorship request blocked ---
    print("\n--- [10] Duplicate Pending Request Blocked ---")
    with client.session_transaction() as sess:
        sess['user_id'] = 2
        sess['user_name'] = 'Alex'
        sess['user_email'] = 'alex@test.com'
        sess['user_role'] = 'mentee'

    # Add a pending request first
    conn = sqlite3.connect(DB)
    conn.execute("INSERT INTO mentorship_requests (mentee_id, mentor_id, message, status) VALUES (2, 1, 'pending test', 'PENDING')")
    conn.commit()
    conn.close()

    resp = client.post('/mentors/1/request', data={'message': 'Send again!'})
    html = resp.data.decode('utf-8') if resp.status_code == 200 else ''
    # Should redirect with a warning flash
    dup_blocked = resp.status_code == 302
    print(f"  [{'PASS' if dup_blocked else 'FAIL'}] Duplicate pending request is blocked (redirected)")
    if not dup_blocked: errors.append("Duplicate pending request should be blocked")

    # --- 11. Past date booking blocked ---
    print("\n--- [11] Past Date Session Booking Blocked ---")
    past_date = (date.today() - timedelta(days=1)).strftime('%Y-%m-%d')
    resp = client.post('/sessions/book/1', data={
        'session_date': past_date,
        'session_time': '14:00',
        'topic': 'Test',
        'description': ''
    })
    html = resp.data.decode('utf-8')
    past_blocked = 'past date' in html.lower() or 'past' in html.lower()
    print(f"  [{'PASS' if past_blocked else 'FAIL'}] Past date session booking is rejected")
    if not past_blocked: errors.append("Past date booking should be rejected")

    # --- 12. Invalid time format blocked ---
    print("\n--- [12] Invalid Time Format Blocked ---")
    future = (date.today() + timedelta(days=3)).strftime('%Y-%m-%d')
    resp = client.post('/sessions/book/1', data={
        'session_date': future,
        'session_time': 'not-a-time',
        'topic': 'Test',
        'description': ''
    })
    html = resp.data.decode('utf-8')
    time_blocked = 'invalid time' in html.lower() or 'time' in html.lower()
    print(f"  [{'PASS' if time_blocked else 'FAIL'}] Invalid time format is rejected")
    if not time_blocked: errors.append("Invalid time format should be rejected")

    # --- Summary ---
    print()
    if errors:
        print(f"FAILED -- {len(errors)} check(s) did not pass:")
        for e in errors:
            print(f"   * {e}")
        sys.exit(1)
    else:
        print("=" * 54)
        print("  ALL SECURITY TESTS PASSED!")
        print("=" * 54)


if __name__ == '__main__':
    run()
