from app import app
from database import get_db_connection
from werkzeug.security import generate_password_hash

def test_mentor_profiles_flow():
    client = app.test_client()

    # 1. Reset and Seed Database with a Mentor and Mentee
    conn = get_db_connection()
    conn.execute('DELETE FROM mentor_profiles;')
    conn.execute('DELETE FROM users;')
    conn.execute(
        'INSERT INTO users (id, name, email, password_hash, role) VALUES (?, ?, ?, ?, ?)',
        (1, 'John Doe', 'john.mentor@example.com', generate_password_hash('mentorPass123'), 'mentor')
    )
    conn.execute(
        'INSERT INTO users (id, name, email, password_hash, role) VALUES (?, ?, ?, ?, ?)',
        (2, 'Lisa Ray', 'lisa.mentee@example.com', generate_password_hash('menteePass123'), 'mentee')
    )
    conn.commit()
    conn.close()
    print('1. Database initialized and seeded with Mentor John and Mentee Lisa.')

    # 2. Login as Mentor John
    client_mentor = app.test_client()
    res_login = client_mentor.post('/login', data={
        'email': 'john.mentor@example.com',
        'password': 'mentorPass123'
    }, follow_redirects=True)
    assert res_login.status_code == 200
    print('2. Mentor logged in successfully.')

    # 3. GET /mentor/profile/edit
    res_edit_page = client_mentor.get('/mentor/profile/edit')
    assert res_edit_page.status_code == 200
    assert b'Edit Your Mentor Profile' in res_edit_page.data
    print('3. GET /mentor/profile/edit loaded successfully.')

    # 4. POST /mentor/profile/edit to save profile
    profile_data = {
        'title': 'Senior Python Engineer',
        'company': 'Google Cloud',
        'profile_pic_url': 'https://example.com/john.jpg',
        'bio': 'Passionate about distributed systems, microservices, and teaching Flask.',
        'skills': 'Python, Flask, Docker, Kubernetes, SQL',
        'experience': '8+ years backend engineering',
        'education': 'M.S. in Computer Science',
        'availability': 'Saturdays 10am - 2pm',
        'linkedin_url': 'https://linkedin.com/in/johndoe'
    }
    res_save = client_mentor.post('/mentor/profile/edit', data=profile_data, follow_redirects=True)
    assert res_save.status_code == 200
    assert b'profile has been saved' in res_save.data
    print('4. Mentor profile saved successfully.')

    # 5. Check SQLite mentor_profiles table directly
    conn = get_db_connection()
    saved = conn.execute('SELECT * FROM mentor_profiles WHERE user_id = 1;').fetchone()
    conn.close()
    assert saved is not None
    assert saved['title'] == 'Senior Python Engineer'
    assert saved['company'] == 'Google Cloud'
    assert 'Flask' in saved['skills']
    assert saved['availability'] == 'Saturdays 10am - 2pm'
    print('5. SQLite database verification: profile verified in mentor_profiles table.')

    # 6. Public mentor directory /mentors
    res_directory = client.get('/mentors')
    assert res_directory.status_code == 200
    assert b'John Doe' in res_directory.data
    assert b'Senior Python Engineer' in res_directory.data
    assert b'Google Cloud' in res_directory.data
    assert b'Docker' in res_directory.data
    print('6. Public mentor directory (/mentors) correctly lists Mentor John.')

    # 7. Search by skill: "Flask"
    res_search_flask = client.get('/mentors?skill=Flask')
    assert res_search_flask.status_code == 200
    assert b'John Doe' in res_search_flask.data
    print('7. Search by skill "Flask" successfully matches and returns Mentor John.')

    # 8. Search by skill: "Ruby" (not present)
    res_search_ruby = client.get('/mentors?skill=Ruby')
    assert res_search_ruby.status_code == 200
    assert b'No mentors found' in res_search_ruby.data
    assert b'Ruby' in res_search_ruby.data
    print('8. Search for unmatched skill "Ruby" properly shows clean empty state.')

    # 9. View detailed mentor profile page /mentors/1
    res_profile = client.get('/mentors/1')
    assert res_profile.status_code == 200
    assert b'About Me' in res_profile.data
    assert b'Passionate about distributed systems' in res_profile.data
    assert b'8+ years backend engineering' in res_profile.data
    assert b'M.S. in Computer Science' in res_profile.data
    assert b'https://linkedin.com/in/johndoe' in res_profile.data
    print('9. Detailed profile view (/mentors/1) displays all details accurately.')

    # 10. Role Security Guard: Mentee cannot access /mentor/profile/edit
    client_mentee = app.test_client()
    client_mentee.post('/login', data={
        'email': 'lisa.mentee@example.com',
        'password': 'menteePass123'
    }, follow_redirects=True)
    res_forbidden = client_mentee.get('/mentor/profile/edit', follow_redirects=True)
    assert b'Only mentors can edit mentor profiles' in res_forbidden.data
    assert b'Mentee Dashboard' in res_forbidden.data
    print('10. Security verified: Mentee blocked from editing mentor profiles.')

    print('\n======================================================')
    print('ALL MENTOR PROFILE TESTS PASSED WITH 100% SUCCESS!')
    print('======================================================')

if __name__ == '__main__':
    test_mentor_profiles_flow()
