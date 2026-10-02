import io
import os
from app import app, UPLOAD_BASE
from database import get_db_connection, init_db

def test_full_verification_workflow():
    init_db()
    client = app.test_client()

    # Clean up test accounts to ensure idempotency across runs
    conn = get_db_connection()
    test_emails = ('evelyn.reed@example.com', 'lucas.vance@college.edu', 'bad.mentor@example.com', 'hacker@example.com', 'bigfile@example.com')
    placeholders = ','.join('?' * len(test_emails))
    conn.execute(f"DELETE FROM mentorship_requests WHERE mentee_id IN (SELECT id FROM users WHERE email IN ({placeholders})) OR mentor_id IN (SELECT id FROM users WHERE email IN ({placeholders}))", test_emails + test_emails)
    conn.execute(f"DELETE FROM verifications WHERE user_id IN (SELECT id FROM users WHERE email IN ({placeholders}))", test_emails)
    conn.execute(f"DELETE FROM mentor_profiles WHERE user_id IN (SELECT id FROM users WHERE email IN ({placeholders}))", test_emails)
    conn.execute(f"DELETE FROM users WHERE email IN ({placeholders})", test_emails)
    conn.commit()
    conn.close()

    print("\n--- Starting Comprehensive Verification & Security Workflow Tests ---")

    # -------------------------------------------------------------
    # 1. Non-admin Access Protection
    # -------------------------------------------------------------
    res_unauth = client.get('/admin/verifications', follow_redirects=False)
    assert res_unauth.status_code == 302, f"Expected redirect for unauthenticated admin access, got {res_unauth.status_code}"
    print("[PASS] 1. Unauthenticated users cannot access /admin/verifications.")

    # -------------------------------------------------------------
    # 2. Mentor Registration & Discovery Isolation
    # -------------------------------------------------------------
    mentor_pdf = (io.BytesIO(b"%PDF-1.4 Fake Gov Photo ID Content"), "gov_photo_id.pdf")
    mentor_data = {
        'name': 'Prof. Evelyn Reed',
        'email': 'evelyn.reed@example.com',
        'password': 'mentorPassword2026',
        'role': 'mentor',
        'title': 'AI Research Director',
        'company': 'DeepLab',
        'skills': 'Python, PyTorch, Machine Learning',
        'experience': '12 years',
        'bio': 'Guiding students in AI and distributed systems.',
        'id_proof': mentor_pdf
    }

    res_reg_mentor = client.post('/register', data=mentor_data, content_type='multipart/form-data', follow_redirects=True)
    assert res_reg_mentor.status_code == 200
    assert b"pending verification" in res_reg_mentor.data

    conn = get_db_connection()
    evelyn = conn.execute("SELECT * FROM users WHERE email = 'evelyn.reed@example.com'").fetchone()
    assert evelyn is not None
    assert evelyn['verification_status'] == 'Pending'
    assert evelyn['id_proof_filename'] is not None
    mentor_id = evelyn['id']
    mentor_id_file = evelyn['id_proof_filename']
    conn.close()
    print(f"[PASS] 2. Mentor registered with Pending status. Document: {mentor_id_file}")

    # Verify unverified mentor does NOT appear in /mentors public listing
    client.get('/logout')  # Log out so navbar doesn't contain current user name
    res_mentors_list = client.get('/mentors')
    assert b"Prof. Evelyn Reed" not in res_mentors_list.data
    print("[PASS] 3. Pending mentor is strictly HIDDEN from public /mentors discovery.")

    # -------------------------------------------------------------
    # 3. Student Registration & Connection Restriction
    # -------------------------------------------------------------
    student_png = (io.BytesIO(b"\x89PNG\r\n\x1a\nFake Student ID Card"), "student_card.png")
    student_data = {
        'name': 'Lucas Vance',
        'email': 'lucas.vance@college.edu',
        'password': 'studentPassword2026',
        'role': 'mentee',
        'college_name': 'Columbia University',
        'college_email': 'lucas.vance@columbia.edu',
        'college_id_proof': student_png
    }

    res_reg_student = client.post('/register', data=student_data, content_type='multipart/form-data', follow_redirects=True)
    assert res_reg_student.status_code == 200
    assert b"pending verification" in res_reg_student.data

    conn = get_db_connection()
    lucas = conn.execute("SELECT * FROM users WHERE email = 'lucas.vance@college.edu'").fetchone()
    assert lucas is not None
    assert lucas['verification_status'] == 'Pending'
    assert lucas['college_name'] == 'Columbia University'
    assert lucas['college_id_filename'] is not None
    student_id = lucas['id']
    student_id_file = lucas['college_id_filename']
    conn.close()
    print(f"[PASS] 4. Student registered with Pending status. Document: {student_id_file}")

    # Student cannot send mentorship request while Pending
    res_req_fail = client.post(f'/mentors/{mentor_id}/request', data={'message': 'I would love your guidance!'}, follow_redirects=True)
    assert b"Only verified students can send mentorship requests" in res_req_fail.data
    print("[PASS] 5. Pending student blocked from sending mentorship requests.")

    # -------------------------------------------------------------
    # 4. Confidential Document Storage & Access Control
    # -------------------------------------------------------------
    # Verify file is in secure_uploads, not in static
    file_on_disk = os.path.join(UPLOAD_BASE, 'id_proofs', mentor_id_file)
    assert os.path.exists(file_on_disk), f"File {file_on_disk} should exist in secure storage"
    assert not os.path.exists(os.path.join(app.root_path, 'static', mentor_id_file))
    print("[PASS] 6. Uploaded document stored securely outside static directory.")

    # Ordinary student cannot view mentor's document
    res_doc_unauth = client.get(f'/admin/verifications/document/{mentor_id}')
    assert res_doc_unauth.status_code == 302
    print("[PASS] 7. Unauthorized user cannot access /admin/verifications/document/<id>.")

    # -------------------------------------------------------------
    # 5. Administrator Login & Verification Portal
    # -------------------------------------------------------------
    res_login_admin = client.post('/login', data={'email': 'admin@mentorconnect.com', 'password': 'admin123'}, follow_redirects=True)
    assert res_login_admin.status_code == 200
    assert b"Member Verification Management" in res_login_admin.data
    assert b"Prof. Evelyn Reed" in res_login_admin.data
    assert b"Lucas Vance" in res_login_admin.data
    print("[PASS] 8. Admin logged in and accessed /admin/verifications.")

    # Admin CAN view confidential document
    res_admin_doc = client.get(f'/admin/verifications/document/{mentor_id}')
    assert res_admin_doc.status_code == 200
    assert b"Fake Gov Photo ID Content" in res_admin_doc.data
    print("[PASS] 9. Admin successfully inspected confidential document.")

    # -------------------------------------------------------------
    # 6. Admin Approves Mentor & Student
    # -------------------------------------------------------------
    # Approve Mentor
    res_app_mentor = client.post(f'/admin/verifications/mentor/{mentor_id}/approve', follow_redirects=True)
    assert res_app_mentor.status_code == 200
    assert b"has been approved and verified" in res_app_mentor.data

    conn = get_db_connection()
    evelyn_updated = conn.execute("SELECT verification_status FROM users WHERE id = ?", (mentor_id,)).fetchone()
    assert evelyn_updated['verification_status'] == 'Verified'
    conn.close()
    print("[PASS] 10. Mentor Evelyn approved to Verified status.")

    # Verify mentor now appears in public /mentors directory!
    res_mentors_after = client.get('/mentors')
    assert b"Prof. Evelyn Reed" in res_mentors_after.data
    assert b"AI Research Director" in res_mentors_after.data
    assert b"View Profile" in res_mentors_after.data
    # Crucial requirement: No direct "Connect" or "Send Request" buttons on cards
    assert b"Send Request" not in res_mentors_after.data
    print("[PASS] 11. Verified mentor visible on /mentors with View Profile button (no Connect button on cards).")

    # Approve Student
    res_app_student = client.post(f'/admin/verifications/student/{student_id}/approve', follow_redirects=True)
    assert res_app_student.status_code == 200
    assert b"has been approved and verified" in res_app_student.data

    conn = get_db_connection()
    lucas_updated = conn.execute("SELECT verification_status FROM users WHERE id = ?", (student_id,)).fetchone()
    assert lucas_updated['verification_status'] == 'Verified'
    conn.close()
    print("[PASS] 12. Student Lucas approved to Verified status.")

    # -------------------------------------------------------------
    # 7. Mentorship Request Workflow Between Verified Users
    # -------------------------------------------------------------
    # Log in as verified student Lucas
    client.post('/login', data={'email': 'lucas.vance@college.edu', 'password': 'studentPassword2026'}, follow_redirects=True)

    # Check mentor profile page shows verified badge and request form
    res_profile = client.get(f'/mentors/{mentor_id}')
    assert res_profile.status_code == 200
    assert b"Prof. Evelyn Reed" in res_profile.data
    assert b"Send Mentorship Request" in res_profile.data

    # Send mentorship request
    res_send_req = client.post(f'/mentors/{mentor_id}/request', data={'message': 'I would love to learn ML research under your mentorship.'}, follow_redirects=True)
    assert res_send_req.status_code == 200
    assert b"Your mentorship request was sent" in res_send_req.data

    conn = get_db_connection()
    req = conn.execute("SELECT * FROM mentorship_requests WHERE mentee_id = ? AND mentor_id = ?", (student_id, mentor_id)).fetchone()
    assert req is not None
    assert req['status'] == 'PENDING'
    conn.close()
    print("[PASS] 13. Verified student successfully sent mentorship request to verified mentor.")

    # -------------------------------------------------------------
    # 8. Rejection Workflows
    # -------------------------------------------------------------
    # Register rejected mentor
    client.post('/register', data={
        'name': 'Bad Mentor',
        'email': 'bad.mentor@example.com',
        'password': 'password12345',
        'role': 'mentor',
        'title': 'Suspicious',
        'skills': 'Hacking',
        'id_proof': (io.BytesIO(b"%PDF-1.4 Fake"), "bad.pdf")
    }, content_type='multipart/form-data', follow_redirects=True)

    conn = get_db_connection()
    bad_m = conn.execute("SELECT id FROM users WHERE email = 'bad.mentor@example.com'").fetchone()
    bad_m_id = bad_m['id']
    conn.close()

    # Admin rejects bad mentor
    client.post('/login', data={'email': 'admin@mentorconnect.com', 'password': 'admin123'}, follow_redirects=True)
    res_rej_m = client.post(f'/admin/verifications/mentor/{bad_m_id}/reject', follow_redirects=True)
    assert res_rej_m.status_code == 200
    assert b"marked as Rejected" in res_rej_m.data

    # Verify rejected mentor does not appear in /mentors
    res_mentors_rej = client.get('/mentors')
    assert b"Bad Mentor" not in res_mentors_rej.data

    # Verified student Lucas cannot request rejected mentor
    client.post('/login', data={'email': 'lucas.vance@college.edu', 'password': 'studentPassword2026'}, follow_redirects=True)
    res_req_rej = client.post(f'/mentors/{bad_m_id}/request', data={'message': 'Hello'}, follow_redirects=True)
    assert b"not yet verified and cannot receive mentorship requests" in res_req_rej.data
    print("[PASS] 14. Rejected mentor cannot be discovered or requested.")

    # -------------------------------------------------------------
    # 9. File Upload Validation & Security Constraints
    # -------------------------------------------------------------
    # Invalid extension (.exe)
    res_bad_ext = client.post('/register', data={
        'name': 'Hacker',
        'email': 'hacker@example.com',
        'password': 'password12345',
        'role': 'mentor',
        'title': 'Engineer',
        'skills': 'C++',
        'id_proof': (io.BytesIO(b"malicious executable"), "malware.exe")
    }, content_type='multipart/form-data', follow_redirects=True)
    assert b"Invalid file type (.exe)" in res_bad_ext.data
    print("[PASS] 15. Disallowed file extension (.exe) rejected.")

    # Oversized file (> 5MB)
    big_file = io.BytesIO(b"0" * (6 * 1024 * 1024))
    res_big_file = client.post('/register', data={
        'name': 'Big File User',
        'email': 'bigfile@example.com',
        'password': 'password12345',
        'role': 'mentor',
        'title': 'Engineer',
        'skills': 'C++',
        'id_proof': (big_file, "oversized.pdf")
    }, content_type='multipart/form-data', follow_redirects=True)
    assert b"exceeds 5MB size limit" in res_big_file.data
    print("[PASS] 16. Oversized file (> 5MB) rejected.")

    print("\n--- ALL VERIFICATION & SECURITY WORKFLOW TESTS PASSED ---")

if __name__ == '__main__':
    test_full_verification_workflow()
