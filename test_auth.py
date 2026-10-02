from app import app
from database import get_db_connection
from werkzeug.security import generate_password_hash

def run_auth_tests():
    client = app.test_client()

    # Seed the database with known test users
    conn = get_db_connection()
    conn.execute('DELETE FROM users;')
    conn.execute(
        'INSERT INTO users (id, name, email, password_hash, role) VALUES (?, ?, ?, ?, ?)',
        (1, 'Mentor John', 'mentor.john@example.com', generate_password_hash('mentorPass123'), 'mentor')
    )
    conn.execute(
        'INSERT INTO users (id, name, email, password_hash, role) VALUES (?, ?, ?, ?, ?)',
        (2, 'Mentee Lisa', 'mentee.lisa@example.com', generate_password_hash('menteePass123'), 'mentee')
    )
    conn.commit()
    conn.close()

    print('Database seeded with test mentor and test mentee.')

    # Test 5: Trying to access dashboard without login
    res_unauth = client.get('/dashboard', follow_redirects=True)
    assert res_unauth.status_code == 200
    assert b'Please log in to access this page' in res_unauth.data
    assert b'Log In' in res_unauth.data
    print('Test 5 PASSED: Accessing dashboard without login is blocked and redirects to /login with warning.')

    # Test 5b: Trying to access mentor dashboard directly without login
    res_unauth_mentor = client.get('/mentor/dashboard', follow_redirects=True)
    assert res_unauth_mentor.status_code == 200
    assert b'Please log in to access this page' in res_unauth_mentor.data
    print('Test 5b PASSED: Accessing /mentor/dashboard directly without login is blocked.')

    # Test 3: Wrong password
    res_wrong_pw = client.post('/login', data={
        'email': 'mentor.john@example.com',
        'password': 'incorrectPassword'
    }, follow_redirects=True)
    assert res_wrong_pw.status_code == 200
    assert b'Invalid email or password' in res_wrong_pw.data
    print('Test 3 PASSED: Wrong password rejected with error alert.')

    # Test 1: Mentor login -> redirected to Mentor Dashboard
    client_mentor = app.test_client()
    res_mentor_login = client_mentor.post('/login', data={
        'email': 'mentor.john@example.com',
        'password': 'mentorPass123'
    }, follow_redirects=True)
    assert res_mentor_login.status_code == 200
    assert b'Mentor Dashboard' in res_mentor_login.data
    assert b'Welcome back, Mentor John' in res_mentor_login.data
    assert b'Incoming Mentorship Requests' in res_mentor_login.data
    print('Test 1 PASSED: Mentor login successfully directs to Mentor Dashboard.')

    # Test 2: Mentee login -> redirected to Mentee Dashboard
    client_mentee = app.test_client()
    res_mentee_login = client_mentee.post('/login', data={
        'email': 'mentee.lisa@example.com',
        'password': 'menteePass123'
    }, follow_redirects=True)
    assert res_mentee_login.status_code == 200
    assert b'Mentee Dashboard' in res_mentee_login.data
    assert b'Welcome, Mentee Lisa' in res_mentee_login.data
    assert b'My Mentorship Requests' in res_mentee_login.data
    print('Test 2 PASSED: Mentee login successfully directs to Mentee Dashboard.')

    # Test 2b: Mentee trying to access Mentor Dashboard (Role protection)
    res_forbidden = client_mentee.get('/mentor/dashboard', follow_redirects=True)
    assert b'restricted to Mentors only' in res_forbidden.data
    assert b'Mentee Dashboard' in res_forbidden.data
    print('Test 2b PASSED: Cross-role protection verified (Mentee cannot access Mentor area).')

    # Test 4: Logout
    res_logout = client_mentor.get('/logout', follow_redirects=True)
    assert res_logout.status_code == 200
    assert b'logged out successfully' in res_logout.data
    # Check that mentor cannot access dashboard anymore
    res_post_logout = client_mentor.get('/dashboard', follow_redirects=True)
    assert b'Please log in to access this page' in res_post_logout.data
    print('Test 4 PASSED: Logout successfully clears session and revokes dashboard access.')

    print('\n==========================================')
    print('ALL AUTHENTICATION TESTS PASSED WITH 100% SUCCESS!')
    print('==========================================')

if __name__ == '__main__':
    run_auth_tests()
