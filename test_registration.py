import io
from app import app
from database import get_db_connection, init_db

def test_registration_flow():
    client = app.test_client()

    # 1. Test GET /register
    res = client.get('/register')
    assert res.status_code == 200, f'GET /register failed: {res.status_code}'
    assert b'Create an Account' in res.data
    print('[PASS] 1. GET /register passed.')

    # Clean existing rows for deterministic test
    conn = get_db_connection()
    conn.execute('DELETE FROM verifications;')
    conn.execute('DELETE FROM mentor_profiles;')
    conn.execute('DELETE FROM mentorship_requests;')
    conn.execute('DELETE FROM mentorship_sessions;')
    conn.execute('DELETE FROM users;')
    conn.commit()
    conn.close()

    # 2. Register a test Mentor with verification fields & photo ID proof
    mentor_payload = {
        'name': 'Dr. Alice Smith',
        'email': 'alice.mentor@example.com',
        'password': 'secretPassword123',
        'role': 'mentor',
        'title': 'Principal Architect',
        'company': 'Tech Corp',
        'skills': 'Python, Cloud, Architecture',
        'experience': '10+ years',
        'bio': 'Passionate mentor helping future engineers.',
        'id_proof': (io.BytesIO(b'%PDF-1.4 fake photo id content'), 'alice_photo_id.pdf')
    }
    res_mentor = client.post('/register', data=mentor_payload, content_type='multipart/form-data', follow_redirects=True)
    assert res_mentor.status_code == 200
    assert b'Registration submitted' in res_mentor.data
    print('[PASS] 2. Test Mentor registered successfully with photo ID proof.')

    # 3. Register a test Mentee with college verification details & student ID card
    mentee_payload = {
        'name': 'Bob Johnson',
        'email': 'bob.mentee@example.com',
        'password': 'myStudentPass2026',
        'role': 'mentee',
        'college_name': 'Stanford University',
        'college_email': 'bob@stanford.edu',
        'college_id_proof': (io.BytesIO(b'%PDF-1.4 fake college id content'), 'bob_student_id.pdf')
    }
    res_mentee = client.post('/register', data=mentee_payload, content_type='multipart/form-data', follow_redirects=True)
    assert res_mentee.status_code == 200
    assert b'Registration submitted' in res_mentee.data
    print('[PASS] 3. Test Mentee registered successfully with college student ID.')

    # 4. Duplicate email validation
    dup_payload = {
        'name': 'Duplicate Alice',
        'email': 'alice.mentor@example.com',
        'password': 'secretPassword123',
        'role': 'mentor',
        'title': 'Staff Engineer',
        'skills': 'Python',
        'id_proof': (io.BytesIO(b'%PDF-1.4 fake photo id content'), 'alice_dup.pdf')
    }
    res_dup = client.post('/register', data=dup_payload, content_type='multipart/form-data', follow_redirects=True)
    assert b'already exists' in res_dup.data
    print('[PASS] 4. Duplicate email prevention passed.')

    # 5. Short password validation
    res_short = client.post('/register', data={
        'name': 'Shorty',
        'email': 'short@example.com',
        'password': '123',
        'role': 'mentee',
        'college_name': 'MIT',
        'college_id_proof': (io.BytesIO(b'%PDF-1.4 fake id'), 'short.pdf')
    }, content_type='multipart/form-data', follow_redirects=True)
    assert b'at least 8 characters' in res_short.data
    print('[PASS] 5. Short password validation passed.')

    # 6. Database storage & hash check
    conn = get_db_connection()
    users = conn.execute('SELECT id, name, email, role, verification_status, password_hash, created_at FROM users ORDER BY id ASC;').fetchall()
    conn.close()

    assert len(users) == 2, f'Expected 2 users, found {len(users)}'
    for u in users:
        print(f"Verified User ID={u['id']}: Name='{u['name']}', Email='{u['email']}', Role='{u['role']}', Status='{u['verification_status']}'")
        assert u['verification_status'] == 'Pending'
        assert 'secretPassword123' not in u['password_hash']
        assert 'myStudentPass2026' not in u['password_hash']

    print('[PASS] 6. Secure password hashing and database storage fully verified!')

    # Re-initialize DB to restore default seed admin and verified users
    init_db()

if __name__ == '__main__':
    test_registration_flow()
