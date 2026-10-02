from app import app
from database import get_db_connection
from werkzeug.security import generate_password_hash
from datetime import date, timedelta

def test_session_booking_workflow():
    client = app.test_client()

    # 1. Reset and Seed Database
    conn = get_db_connection()
    conn.execute('DELETE FROM mentorship_sessions;')
    conn.execute('DELETE FROM mentorship_requests;')
    conn.execute('DELETE FROM mentor_profiles;')
    conn.execute('DELETE FROM users;')

    # Seed 1 Mentor and 1 Mentee
    conn.execute(
        'INSERT INTO users (id, name, email, password_hash, role) VALUES (?, ?, ?, ?, ?)',
        (1, 'Sarah Chen', 'sarah.mentor@example.com', generate_password_hash('pass123'), 'mentor')
    )
    conn.execute(
        'INSERT INTO mentor_profiles (user_id, title, company, skills, availability) VALUES (?, ?, ?, ?, ?)',
        (1, 'Senior Backend Engineer', 'Google Cloud', 'Python, Flask, AWS', 'Weekends 2pm - 6pm')
    )
    conn.execute(
        'INSERT INTO users (id, name, email, password_hash, role) VALUES (?, ?, ?, ?, ?)',
        (2, 'Alex Mentee', 'alex.mentee@example.com', generate_password_hash('pass123'), 'mentee')
    )

    # Seed an ACCEPTED request between Alex (id 2) and Sarah (id 1)
    conn.execute('''
        INSERT INTO mentorship_requests (id, mentee_id, mentor_id, message, status)
        VALUES (10, 2, 1, 'Looking forward to learning from you!', 'ACCEPTED')
    ''')

    # Seed a PENDING request (id 11) for testing unauthorized booking
    conn.execute('''
        INSERT INTO mentorship_requests (id, mentee_id, mentor_id, message, status)
        VALUES (11, 2, 1, 'Another pending request', 'PENDING')
    ''')

    conn.commit()
    conn.close()
    print('1. Seeded users and accepted mentorship request.')

    # 2. Log in as Mentee Alex
    client_alex = app.test_client()
    res_login = client_alex.post('/login', data={'email': 'alex.mentee@example.com', 'password': 'pass123'}, follow_redirects=True)
    assert res_login.status_code == 200
    print('2. Mentee Alex logged in.')

    # 3. Test booking with non-accepted request (id 11 is PENDING) -> Must fail
    res_pending_book = client_alex.get('/sessions/book/11', follow_redirects=True)
    assert b'only be booked after your mentorship request is accepted' in res_pending_book.data
    print('3. Security check: cannot book session for non-accepted request.')

    # 4. Test booking form access for ACCEPTED request (id 10)
    res_book_page = client_alex.get('/sessions/book/10')
    assert res_book_page.status_code == 200
    assert b'Book a 1-on-1 Session' in res_book_page.data
    assert b'Sarah Chen' in res_book_page.data
    print('4. Booking form loaded successfully for accepted mentorship.')

    # 5. Test Past Date Validation
    past_date = '2020-05-15'
    res_past = client_alex.post('/sessions/book/10', data={
        'session_date': past_date,
        'session_time': '14:00',
        'topic': 'Past Review',
        'description': 'Trying to book in the past'
    }, follow_redirects=True)
    assert b'Cannot schedule a session on a past date' in res_past.data
    print('5. Past date validation passed: dates in the past are rejected.')

    # 6. Test Valid Session Booking (Future Date)
    future_date = (date.today() + timedelta(days=5)).isoformat()
    valid_payload = {
        'session_date': future_date,
        'session_time': '15:30',
        'topic': 'System Design & Code Review',
        'description': 'Going through Flask MVC structure and preparing for technical interview.'
    }
    res_book_success = client_alex.post('/sessions/book/10', data=valid_payload, follow_redirects=True)
    assert res_book_success.status_code == 200
    assert b'session with Sarah Chen has been scheduled' in res_book_success.data
    print('6. Future session booked successfully.')

    # 7. Check SQLite database table: mentorship_sessions
    conn = get_db_connection()
    session_row = conn.execute('SELECT * FROM mentorship_sessions WHERE request_id = 10;').fetchone()
    conn.close()
    assert session_row is not None
    assert session_row['session_date'] == future_date
    assert session_row['session_time'] == '15:30'
    assert session_row['topic'] == 'System Design & Code Review'
    assert session_row['status'] == 'SCHEDULED'
    print('7. SQLite database verification: session row stored with status SCHEDULED.')

    # 8. Check Mentee Dashboard
    res_mentee_dash = client_alex.get('/mentee/dashboard')
    assert res_mentee_dash.status_code == 200
    assert b'System Design' in res_mentee_dash.data
    assert b'Sarah Chen' in res_mentee_dash.data
    assert future_date.encode() in res_mentee_dash.data
    print('8. Mentee dashboard correctly displays booked session.')

    # 9. Log in as Mentor Sarah and verify Mentor Dashboard
    client_sarah = app.test_client()
    client_sarah.post('/login', data={'email': 'sarah.mentor@example.com', 'password': 'pass123'}, follow_redirects=True)
    res_mentor_dash = client_sarah.get('/mentor/dashboard')
    assert res_mentor_dash.status_code == 200
    assert b'System Design' in res_mentor_dash.data
    assert b'Alex Mentee' in res_mentor_dash.data
    assert b'Going through Flask MVC structure' in res_mentor_dash.data
    assert future_date.encode() in res_mentor_dash.data
    print('9. Mentor dashboard correctly displays upcoming session.')

    print('\n======================================================')
    print('ALL SESSION BOOKING TESTS PASSED WITH 100% SUCCESS!')
    print('======================================================')

if __name__ == '__main__':
    test_session_booking_workflow()
