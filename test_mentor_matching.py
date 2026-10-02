"""
test_mentor_matching.py -- Verify the Mentor Matching algorithm and UI.
ASCII output only to prevent Windows console encoding errors.
"""
import sqlite3, sys
from app import app, calculate_skill_match
from database import init_db
from werkzeug.security import generate_password_hash

DB = "mentor_connect.db"


def seed_mentors_for_matching():
    conn = sqlite3.connect(DB)
    conn.execute("PRAGMA foreign_keys = ON")
    c = conn.cursor()

    for t in ["mentorship_sessions", "mentorship_requests", "mentor_profiles", "users"]:
        c.execute(f"DELETE FROM {t}")

    # Mentor 1: Python, AWS, Cloud, Java (Should be 100% match for "Python, AWS, Cloud")
    c.execute("INSERT INTO users (id, name, email, password_hash, role) VALUES (1, 'Dr. Cloud Expert', 'cloud@test.com', ?, 'mentor')",
              (generate_password_hash("password123"),))
    c.execute("""INSERT INTO mentor_profiles (user_id, title, company, skills, bio, availability)
                 VALUES (1, 'Cloud Architect', 'AWS', 'Python, AWS, Cloud, Java', 'Specializes in cloud infrastructure.', 'Weekends')""")

    # Mentor 2: Python, AWS (Should be 67% match for 2 out of 3 skills)
    c.execute("INSERT INTO users (id, name, email, password_hash, role) VALUES (2, 'Alex Backend', 'backend@test.com', ?, 'mentor')",
              (generate_password_hash("password123"),))
    c.execute("""INSERT INTO mentor_profiles (user_id, title, company, skills, bio, availability)
                 VALUES (2, 'Backend Engineer', 'Google', 'Python, AWS', 'Backend developer.', 'Evenings')""")

    # Mentor 3: JavaScript, React, UI/UX (0% match for "Python, AWS, Cloud")
    c.execute("INSERT INTO users (id, name, email, password_hash, role) VALUES (3, 'Frontend Pro', 'frontend@test.com', ?, 'mentor')",
              (generate_password_hash("password123"),))
    c.execute("""INSERT INTO mentor_profiles (user_id, title, company, skills, bio, availability)
                 VALUES (3, 'Frontend Lead', 'Meta', 'JavaScript, React, UI/UX', 'Frontend engineer.', 'Flexible')""")

    conn.commit()
    conn.close()
    print("1. Seeded 3 mentors with distinct skill profiles.")


def run_tests():
    init_db()
    seed_mentors_for_matching()
    errors = []

    print("\n--- [A] Algorithm Unit Tests ---")

    # 1. Exact match test from user specification
    score, matched, total = calculate_skill_match("Python, AWS, Cloud", "Python, AWS, Cloud, Java")
    is_100 = score == 100 and len(matched) == 3 and total == 3
    print(f"  [{'PASS' if is_100 else 'FAIL'}] Mentee: (Python, AWS, Cloud) vs Mentor: (Python, AWS, Cloud, Java) = {score}% (Expected 100%)")
    if not is_100: errors.append(f"Expected 100%, got {score}%")

    # 2. Partial match test (2 out of 4 = 50%)
    score50, matched50, total50 = calculate_skill_match("Python, AWS, React, Docker", "Python, AWS, Flask")
    is_50 = score50 == 50 and len(matched50) == 2 and total50 == 4
    print(f"  [{'PASS' if is_50 else 'FAIL'}] Mentee: 4 skills vs Mentor: 2 overlapping = {score50}% (Expected 50%)")
    if not is_50: errors.append(f"Expected 50%, got {score50}%")

    # 3. Case insensitivity & whitespace trimming
    score_case, matched_case, _ = calculate_skill_match("  pYtHon ,  aws  , CLOUD ", "Python, AWS, Cloud, Java")
    is_case_ok = score_case == 100 and len(matched_case) == 3
    print(f"  [{'PASS' if is_case_ok else 'FAIL'}] Case & whitespace insensitivity handles messy input = {score_case}%")
    if not is_case_ok: errors.append("Case insensitivity failed")

    # 4. Zero match test
    score0, matched0, _ = calculate_skill_match("Go, Rust", "Python, AWS, Cloud, Java")
    is_zero = score0 == 0 and len(matched0) == 0
    print(f"  [{'PASS' if is_zero else 'FAIL'}] Zero overlapping skills returns {score0}% (Expected 0%)")
    if not is_zero: errors.append(f"Expected 0%, got {score0}%")

    # 5. Empty inputs
    score_empty, _, _ = calculate_skill_match("", "Python, AWS")
    is_empty_ok = score_empty == 0
    print(f"  [{'PASS' if is_empty_ok else 'FAIL'}] Empty mentee input safely returns {score_empty}%")
    if not is_empty_ok: errors.append("Empty input should return 0")

    print("\n--- [B] Web Route & UI Tests ---")
    client = app.test_client()

    # 6. GET /match loads initial form
    res_page = client.get('/match')
    page_ok = res_page.status_code == 200 and 'Mentor Skill Matching' in res_page.data.decode('utf-8')
    print(f"  [{'PASS' if page_ok else 'FAIL'}] GET /match loads matching page (HTTP 200)")
    if not page_ok: errors.append("GET /match failed to load")

    # 7. GET /match with skills calculates and ranks mentors
    res_query = client.get('/match?skills=Python,AWS,Cloud')
    html_query = res_query.data.decode('utf-8')
    has_100_badge = '100% Match' in html_query
    has_cloud_mentor = 'Dr. Cloud Expert' in html_query
    has_matched_skill = '✓ Python' in html_query
    rank_ok = res_query.status_code == 200 and has_100_badge and has_cloud_mentor
    print(f"  [{'PASS' if rank_ok else 'FAIL'}] GET /match?skills=... displays 100% Match badge and mentor")
    if not rank_ok: errors.append("Match query did not render expected badges")

    # 8. Verify ranking order: 100% mentor appears BEFORE lower % mentor in HTML
    pos_mentor1 = html_query.find('Dr. Cloud Expert')
    pos_mentor2 = html_query.find('Alex Backend')
    pos_mentor3 = html_query.find('Frontend Pro')
    order_ok = pos_mentor1 != -1 and pos_mentor2 != -1 and pos_mentor3 != -1 and pos_mentor1 < pos_mentor2 < pos_mentor3
    print(f"  [{'PASS' if order_ok else 'FAIL'}] Mentors are sorted in descending order of matching percentage")
    if not order_ok: errors.append("Mentors not sorted by score descending")

    # 9. POST /match works
    res_post = client.post('/match', data={'skills': 'JavaScript, React'})
    html_post = res_post.data.decode('utf-8')
    post_ok = res_post.status_code == 200 and 'Frontend Pro' in html_post and '100% Match' in html_post
    print(f"  [{'PASS' if post_ok else 'FAIL'}] POST /match works and ranks 'Frontend Pro' at 100% for (JavaScript, React)")
    if not post_ok: errors.append("POST /match failed")

    # 10. Alias route /mentors/match works
    res_alias = client.get('/mentors/match')
    alias_ok = res_alias.status_code == 200
    print(f"  [{'PASS' if alias_ok else 'FAIL'}] Alias route GET /mentors/match returns HTTP 200")
    if not alias_ok: errors.append("Alias /mentors/match failed")

    print()
    if errors:
        print(f"FAILED -- {len(errors)} check(s) did not pass:")
        for e in errors:
            print(f"   * {e}")
        sys.exit(1)
    else:
        print("=" * 54)
        print("  ALL MENTOR MATCHING TESTS PASSED 100%!")
        print("=" * 54)


if __name__ == '__main__':
    run_tests()
