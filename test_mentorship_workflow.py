from app import app
from database import get_db_connection
from werkzeug.security import generate_password_hash

def test_mentorship_request_workflow():
    client = app.test_client()

    # 1. Reset and Seed Database
    conn = get_db_connection()
    conn.execute('DELETE FROM mentorship_requests;')
    conn.execute('DELETE FROM mentor_profiles;')
    conn.execute('DELETE FROM users;')

    # Seed 1 Mentor and 2 Mentees
    conn.execute(
        'INSERT INTO users (id, name, email, password_hash, role) VALUES (?, ?, ?, ?, ?)',
        (1, 'Sarah Chen', 'sarah.mentor@example.com', generate_password_hash('pass123'), 'mentor')
    )
    conn.execute(
        'INSERT INTO mentor_profiles (user_id, title, company, skills, availability) VALUES (?, ?, ?, ?, ?)',
        (1, 'Senior Backend Engineer', 'Google Cloud', 'Python, Flask, AWS', 'Weekends')
    )
    conn.execute(
        'INSERT INTO users (id, name, email, password_hash, role) VALUES (?, ?, ?, ?, ?)',
        (2, 'Alex Mentee', 'alex.mentee@example.com', generate_password_hash('pass123'), 'mentee')
    )
    conn.execute(
        'INSERT INTO users (id, name, email, password_hash, role) VALUES (?, ?, ?, ?, ?)',
        (3, 'Chloe Mentee', 'chloe.mentee@example.com', generate_password_hash('pass123'), 'mentee')
    )
    conn.commit()
    conn.close()
    print('1. Database initialized with Mentor Sarah, Mentee Alex, and Mentee Chloe.')

    # 2. Log in as Mentee Alex
    client_alex = app.test_client()
    res_login_alex = client_alex.post('/login', data={
        'email': 'alex.mentee@example.com',
        'password': 'pass123'
    }, follow_redirects=True)
    assert res_login_alex.status_code == 200
    print('2. Mentee Alex logged in.')

    # 3. Alex views Sarah's mentor profile
    res_profile = client_alex.get('/mentors/1')
    assert res_profile.status_code == 200
    assert b'Request Mentorship' in res_profile.data
    print('3. Mentee Alex can view mentor profile and sees request form.')

    # 4. Alex submits a mentorship request with a message
    intro_message = 'Hi Sarah! I am learning Flask and would love guidance on backend architecture and placement prep.'
    res_req = client_alex.post('/mentors/1/request', data={'message': intro_message}, follow_redirects=True)
    assert res_req.status_code == 200
    assert b'Your mentorship request was sent to Sarah Chen' in res_req.data
    assert b'PENDING' in res_req.data
    print('4. Mentorship request sent successfully with message.')

    # 5. Verify request in SQLite database
    conn = get_db_connection()
    req = conn.execute('SELECT * FROM mentorship_requests WHERE mentee_id = 2 AND mentor_id = 1;').fetchone()
    conn.close()
    assert req is not None
    assert req['status'] == 'PENDING'
    assert req['message'] == intro_message
    print('5. Request verified in SQLite table with status PENDING.')

    # 6. Test duplicate pending request prevention
    res_dup = client_alex.post('/mentors/1/request', data={'message': 'Another attempt!'}, follow_redirects=True)
    assert b'already have a pending mentorship request' in res_dup.data
    print('6. Duplicate pending request blocked successfully.')

    # 7. Log in as Mentor Sarah
    client_sarah = app.test_client()
    client_sarah.post('/login', data={
        'email': 'sarah.mentor@example.com',
        'password': 'pass123'
    }, follow_redirects=True)

    # 8. Sarah views Mentor Dashboard
    res_dash = client_sarah.get('/mentor/dashboard')
    assert res_dash.status_code == 200
    assert b'Alex Mentee' in res_dash.data
    assert b'alex.mentee@example.com' in res_dash.data
    assert b'learning Flask and would love guidance' in res_dash.data
    assert b'PENDING' in res_dash.data
    assert b'Accept Request' in res_dash.data
    assert b'Reject Request' in res_dash.data
    print('8. Mentor dashboard displays incoming request details (Mentee name, message, date, status).')

    # 9. Sarah accepts Alex's request
    req_id = req['id']
    res_accept = client_sarah.post(f'/mentorship-requests/{req_id}/accept', follow_redirects=True)
    assert res_accept.status_code == 200
    assert b'You accepted the mentorship request' in res_accept.data
    assert b'ACCEPTED' in res_accept.data

    # Check database status
    conn = get_db_connection()
    updated_req = conn.execute('SELECT status FROM mentorship_requests WHERE id = ?;', (req_id,)).fetchone()
    conn.close()
    assert updated_req['status'] == 'ACCEPTED'
    print('9. Mentor accepted request: status updated to ACCEPTED in DB.')

    # 10. Alex's dashboard reflects ACCEPTED status
    res_alex_dash = client_alex.get('/mentee/dashboard')
    assert b'ACCEPTED' in res_alex_dash.data
    assert b'Request Accepted' in res_alex_dash.data
    print('10. Mentee dashboard reflects ACCEPTED status.')

    # 11. Test Reject Flow: Mentee Chloe sends a request, Sarah rejects it
    client_chloe = app.test_client()
    client_chloe.post('/login', data={'email': 'chloe.mentee@example.com', 'password': 'pass123'}, follow_redirects=True)
    client_chloe.post('/mentors/1/request', data={'message': 'Need quick advice.'}, follow_redirects=True)

    conn = get_db_connection()
    chloe_req = conn.execute('SELECT id FROM mentorship_requests WHERE mentee_id = 3 AND mentor_id = 1;').fetchone()
    conn.close()

    res_reject = client_sarah.post(f'/mentorship-requests/{chloe_req["id"]}/reject', follow_redirects=True)
    assert res_reject.status_code == 200
    assert b'The mentorship request was declined' in res_reject.data

    conn = get_db_connection()
    rejected_req = conn.execute('SELECT status FROM mentorship_requests WHERE id = ?;', (chloe_req['id'],)).fetchone()
    conn.close()
    assert rejected_req['status'] == 'REJECTED'
    print('11. Mentor rejected request: status updated to REJECTED in DB.')

    # 12. Chloe's dashboard reflects REJECTED status
    res_chloe_dash = client_chloe.get('/mentee/dashboard')
    assert b'REJECTED' in res_chloe_dash.data
    print('12. Mentee Chloe dashboard reflects REJECTED status.')

    print('\n======================================================')
    print('ALL MENTORSHIP REQUEST WORKFLOW TESTS PASSED 100%!')
    print('======================================================')

if __name__ == '__main__':
    test_mentorship_request_workflow()
