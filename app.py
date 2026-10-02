import os
import secrets
from functools import wraps
from datetime import datetime, date
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from database import get_db_connection, init_db

# Initialize the Flask application
app = Flask(__name__)

# ---------- Security & Upload Configuration ----------
app.config['SECRET_KEY'] = os.environ.get('MC_SECRET_KEY') or secrets.token_hex(32)
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # Max 10MB overall request limit

# Secure upload directory outside static (confidential verification documents)
UPLOAD_BASE = os.path.join(app.root_path, 'secure_uploads')
ALLOWED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.pdf'}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB max per document

# Ensure SQLite database, tables, and secure storage exist
init_db()

# ========================================================
# Helper Decorators: Login Required & Admin Required
# ========================================================
def login_required(f):
    """
    Decorator to protect routes from unauthenticated access.
    If the user does not have an active session, redirects to the login page.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """
    Decorator to restrict access strictly to platform administrators.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in with administrator credentials.', 'warning')
            return redirect(url_for('login'))
        if not session.get('is_admin') and session.get('user_role') != 'admin':
            flash('Unauthorized access: Administrator privileges required.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function


def save_secure_upload(file_obj, subfolder):
    """
    Validates file presence, allowed extensions, and file size (<= 5MB).
    Saves document securely with a random unguessable filename inside UPLOAD_BASE/<subfolder>.
    Returns (saved_filename, error_message).
    """
    if not file_obj or not file_obj.filename:
        return None, 'Please choose a file to upload.'

    ext = os.path.splitext(file_obj.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return None, f'Invalid file type ({ext}). Allowed formats: PNG, JPG, JPEG, PDF.'

    file_bytes = file_obj.read()
    if len(file_bytes) == 0:
        return None, 'Uploaded file is empty.'
    if len(file_bytes) > MAX_FILE_SIZE:
        return None, f'File exceeds 5MB size limit ({round(len(file_bytes)/(1024*1024), 2)}MB).'

    unique_filename = f"{secrets.token_hex(16)}{ext}"
    target_dir = os.path.join(UPLOAD_BASE, subfolder)
    os.makedirs(target_dir, exist_ok=True)
    file_path = os.path.join(target_dir, unique_filename)

    with open(file_path, 'wb') as f:
        f.write(file_bytes)

    return unique_filename, None


# ========================================================
# Public & Directory Routes
# ========================================================
@app.route('/')
def home():
    """
    Landing page for MentorConnect.
    """
    return render_template('index.html')


@app.route('/mentors')
def mentor_list():
    """
    Dedicated public listing of mentors with search by skill or name.
    Only mentors with 'Verified' status are displayed.
    """
    search_query = request.args.get('skill', '').strip()
    conn = get_db_connection()

    if search_query:
        sql = '''
            SELECT u.id as user_id, u.name, u.email, u.verification_status,
                   p.title, p.company, p.profile_pic_url, p.bio, p.skills,
                   p.experience, p.education, p.availability, p.linkedin_url
            FROM users u
            LEFT JOIN mentor_profiles p ON u.id = p.user_id
            WHERE u.role = 'mentor' AND u.verification_status = 'Verified'
              AND (p.skills LIKE ? OR p.title LIKE ? OR u.name LIKE ?)
            ORDER BY u.id DESC
        '''
        wildcard = f'%{search_query}%'
        mentors = conn.execute(sql, (wildcard, wildcard, wildcard)).fetchall()
    else:
        sql = '''
            SELECT u.id as user_id, u.name, u.email, u.verification_status,
                   p.title, p.company, p.profile_pic_url, p.bio, p.skills,
                   p.experience, p.education, p.availability, p.linkedin_url
            FROM users u
            LEFT JOIN mentor_profiles p ON u.id = p.user_id
            WHERE u.role = 'mentor' AND u.verification_status = 'Verified'
            ORDER BY u.id DESC
        '''
        mentors = conn.execute(sql).fetchall()

    conn.close()
    return render_template('mentors/index.html', mentors=mentors, search_query=search_query)


def calculate_skill_match(mentee_skills_raw, mentor_skills_raw):
    """
    Explainable Skill Matching Algorithm:
    1. Splits and normalizes mentee skills and mentor skills into lowercase trimmed sets.
    2. Determines the set intersection (overlapping skills).
    3. Calculates matching percentage:
       Matching Score = (len(overlapping_skills) / len(mentee_skills)) * 100%
    4. Returns:
       - score: integer from 0 to 100
       - matched_display: list of matched skills preserving mentor's original casing
       - total_mentee_count: number of skills desired by the mentee
    """
    if not mentee_skills_raw or not mentor_skills_raw:
        return 0, [], 0

    mentee_skills = [s.strip().lower() for s in mentee_skills_raw.split(',') if s.strip()]
    mentee_set = set(mentee_skills)
    if not mentee_set:
        return 0, [], 0

    # Map normalized lowercase to mentor's original token casing
    mentor_tokens = [s.strip() for s in mentor_skills_raw.split(',') if s.strip()]
    mentor_map = {s.lower(): s for s in mentor_tokens}
    mentor_set = set(mentor_map.keys())

    # Find common skills
    overlap = mentee_set.intersection(mentor_set)
    matched_display = [mentor_map[k] for k in overlap]

    score = round((len(overlap) / len(mentee_set)) * 100)
    return score, matched_display, len(mentee_set)


@app.route('/match', methods=['GET', 'POST'])
@app.route('/mentors/match', methods=['GET', 'POST'])
def mentor_match():
    """
    Smart Mentor Matching Route:
    Compares mentee desired skills with mentor skills in SQLite and ranks mentors
    by overlapping skill score percentage.
    """
    popular_skills = [
        'Python', 'Flask', 'JavaScript', 'React', 'Node.js', 
        'AWS', 'Cloud', 'SQL', 'Docker', 'Machine Learning', 'Java', 'UI/UX'
    ]

    skills_query = request.values.get('skills', '').strip()
    mentee_skills_list = [s.strip() for s in skills_query.split(',') if s.strip()]

    conn = get_db_connection()
    sql = '''
        SELECT u.id as user_id, u.name, u.email, u.verification_status,
               p.title, p.company, p.profile_pic_url, p.bio, p.skills,
               p.experience, p.education, p.availability, p.linkedin_url
        FROM users u
        LEFT JOIN mentor_profiles p ON u.id = p.user_id
        WHERE u.role = 'mentor' AND u.verification_status = 'Verified'
        ORDER BY u.id DESC
    '''
    mentors = conn.execute(sql).fetchall()
    conn.close()

    results = []
    for m in mentors:
        score, matched_skills, total_desired = calculate_skill_match(skills_query, m['skills'] or '')
        all_skills = [s.strip() for s in (m['skills'] or '').split(',') if s.strip()]
        results.append({
            'mentor': m,
            'score': score,
            'matched_skills': matched_skills,
            'all_skills': all_skills,
            'overlap_count': len(matched_skills)
        })

    # Sort mentors by:
    # 1. Matching score descending
    # 2. Number of overlapping skills descending
    # 3. Name alphabetically
    if skills_query:
        results.sort(key=lambda x: (-x['score'], -x['overlap_count'], x['mentor']['name']))

    return render_template(
        'mentors/match.html',
        results=results,
        skills_query=skills_query,
        mentee_skills_list=mentee_skills_list,
        popular_skills=popular_skills
    )


@app.route('/mentors/<int:mentor_id>')
def mentor_profile(mentor_id):
    """
    Detailed profile view of a mentor.
    Checks if the currently logged-in mentee has an existing request
    and provides verification context.
    """
    conn = get_db_connection()
    sql = '''
        SELECT u.id as user_id, u.name, u.email, u.verification_status,
               p.title, p.company, p.profile_pic_url, p.bio, p.skills,
               p.experience, p.education, p.availability, p.linkedin_url
        FROM users u
        LEFT JOIN mentor_profiles p ON u.id = p.user_id
        WHERE u.id = ? AND u.role = 'mentor'
    '''
    mentor = conn.execute(sql, (mentor_id,)).fetchone()

    if mentor is None:
        conn.close()
        flash('Mentor not found or profile does not exist.', 'warning')
        return redirect(url_for('mentor_list'))

    # Check for existing request from current logged-in mentee & mentee verification status
    existing_request = None
    mentee_verification_status = None
    if session.get('user_role') == 'mentee':
        mentee_user = conn.execute('SELECT verification_status FROM users WHERE id = ?', (session['user_id'],)).fetchone()
        if mentee_user:
            mentee_verification_status = mentee_user['verification_status']

        existing_request = conn.execute('''
            SELECT * FROM mentorship_requests 
            WHERE mentee_id = ? AND mentor_id = ?
            ORDER BY id DESC LIMIT 1
        ''', (session['user_id'], mentor_id)).fetchone()

    conn.close()
    return render_template('mentors/profile.html', mentor=mentor, existing_request=existing_request, mentee_verification_status=mentee_verification_status)


# ========================================================
# Authentication Routes
# ========================================================
@app.route('/register', methods=['GET', 'POST'])
def register():
    """
    User registration for Mentors and Mentees with mandatory ID verification documents.
    Mentors provide professional info and photo ID proof.
    Students provide college info and college student ID card.
    """
    if 'user_id' in session and request.method == 'GET':
        return redirect(url_for('dashboard'))

    selected_role = request.args.get('role', 'mentee').lower()

    if request.method == 'POST':
        name     = request.form.get('name', '').strip()[:120]   # cap at 120 chars
        email    = request.form.get('email', '').strip().lower()[:254]
        password = request.form.get('password', '')
        role     = request.form.get('role', '').strip().lower()

        selected_role = role

        # Additional fields
        title         = request.form.get('title', '').strip()[:150]
        company       = request.form.get('company', '').strip()[:150]
        skills        = request.form.get('skills', '').strip()[:300]
        experience    = request.form.get('experience', '').strip()[:300]
        bio           = request.form.get('bio', '').strip()[:2000]
        college_name  = request.form.get('college_name', '').strip()[:150]
        college_email = request.form.get('college_email', '').strip().lower()[:254]

        template_kwargs = dict(
            name=name, email=email, selected_role=selected_role,
            title=title, company=company, skills=skills,
            experience=experience, bio=bio,
            college_name=college_name, college_email=college_email
        )

        if not name or not email or not password or not role:
            flash('All core fields (Name, Email, Password, Role) are required.', 'danger')
            return render_template('register.html', **template_kwargs)

        if role not in ('mentor', 'mentee'):
            flash('Invalid role selected. Please choose Mentor or Mentee.', 'danger')
            return render_template('register.html', **template_kwargs)

        # Password must be at least 8 characters
        if len(password) < 8:
            flash('Password must be at least 8 characters long.', 'danger')
            return render_template('register.html', **template_kwargs)

        # Basic email format check
        email_parts = email.split('@')
        if len(email_parts) != 2 or not email_parts[0] or '.' not in email_parts[1]:
            flash('Please enter a valid email address (e.g. name@example.com).', 'danger')
            return render_template('register.html', **template_kwargs)

        # Role-specific validations & secure file processing
        id_proof_filename = None
        college_id_filename = None

        if role == 'mentor':
            if not title:
                flash('Professional title is required for mentors.', 'danger')
                return render_template('register.html', **template_kwargs)
            if not skills:
                flash('Key skills are required for mentors.', 'danger')
                return render_template('register.html', **template_kwargs)

            file_obj = request.files.get('id_proof')
            filename, err = save_secure_upload(file_obj, 'id_proofs')
            if err:
                flash(f'Photo ID proof error: {err}', 'danger')
                return render_template('register.html', **template_kwargs)
            id_proof_filename = filename

        elif role == 'mentee':
            if not college_name:
                flash('College / University name is required for student verification.', 'danger')
                return render_template('register.html', **template_kwargs)

            if college_email:
                c_parts = college_email.split('@')
                if len(c_parts) != 2 or not c_parts[0] or '.' not in c_parts[1]:
                    flash('Please enter a valid college email address.', 'danger')
                    return render_template('register.html', **template_kwargs)

            file_obj = request.files.get('college_id_proof')
            filename, err = save_secure_upload(file_obj, 'college_ids')
            if err:
                flash(f'College ID card upload error: {err}', 'danger')
                return render_template('register.html', **template_kwargs)
            college_id_filename = filename

        conn = get_db_connection()
        existing_user = conn.execute(
            'SELECT id FROM users WHERE email = ?', (email,)
        ).fetchone()

        if existing_user:
            conn.close()
            flash('An account with this email address already exists. Please log in.', 'danger')
            return render_template('register.html', **template_kwargs)

        password_hash = generate_password_hash(password)
        cursor = conn.execute('''
            INSERT INTO users (
                name, email, password_hash, role, verification_status,
                college_name, college_email, id_proof_filename, college_id_filename
            ) VALUES (?, ?, ?, ?, 'Pending', ?, ?, ?, ?)
        ''', (name, email, password_hash, role,
              college_name if role == 'mentee' else None,
              college_email if role == 'mentee' else None,
              id_proof_filename,
              college_id_filename))
        new_user_id = cursor.lastrowid

        # Record verification audit entry
        doc_type = 'mentor_photo_id' if role == 'mentor' else 'student_college_id'
        saved_file = id_proof_filename if role == 'mentor' else college_id_filename
        conn.execute('''
            INSERT INTO verifications (user_id, document_type, filename, status)
            VALUES (?, ?, ?, 'Pending')
        ''', (new_user_id, doc_type, saved_file))

        # Create mentor profile record if role is mentor
        if role == 'mentor':
            conn.execute('''
                INSERT INTO mentor_profiles (user_id, title, company, skills, experience, bio)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (new_user_id, title, company, skills, experience, bio))

        conn.commit()
        conn.close()

        session.clear()
        session['user_id'] = new_user_id
        session['user_name'] = name
        session['user_email'] = email
        session['user_role'] = role
        session['verification_status'] = 'Pending'
        session['is_admin'] = False

        if role == 'mentor':
            flash(f'Registration submitted! Welcome, {name}. Your mentor account and photo ID proof are pending verification by administrators.', 'success')
        else:
            flash(f'Registration submitted! Welcome, {name}. Your student account and college ID card are pending verification by administrators.', 'success')
        return redirect(url_for('dashboard'))

    return render_template('register.html', selected_role=selected_role)


@app.route('/login', methods=['GET', 'POST'])
def login():
    """
    User login route. Sets session state for regular users and administrators.
    """
    if 'user_id' in session and request.method == 'GET':
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        if not email or not password:
            flash('Please provide both email and password.', 'danger')
            return render_template('login.html', email=email)

        conn = get_db_connection()
        user = conn.execute(
            'SELECT * FROM users WHERE email = ?', (email,)
        ).fetchone()
        conn.close()

        if user is None or not check_password_hash(user['password_hash'], password):
            flash('Invalid email or password. Please try again.', 'danger')
            return render_template('login.html', email=email)

        session.clear()
        session['user_id'] = user['id']
        session['user_name'] = user['name']
        session['user_email'] = user['email']
        session['user_role'] = user['role']

        # Admin & verification status session flags
        user_keys = user.keys()
        is_admin = bool(user['is_admin']) if 'is_admin' in user_keys and user['is_admin'] else False
        v_status = user['verification_status'] if 'verification_status' in user_keys and user['verification_status'] else 'Verified'
        
        session['is_admin'] = is_admin
        session['verification_status'] = v_status
        if is_admin:
            session['user_role'] = 'admin'

        flash(f'Welcome back, {user["name"]}!', 'success')
        if is_admin:
            return redirect(url_for('admin_verifications'))
        return redirect(url_for('dashboard'))

    return render_template('login.html')


@app.route('/logout', methods=['GET', 'POST'])
def logout():
    """
    Logs out the user by clearing the session.
    Accepts POST (from navbar logout button) and GET (from direct URL/tests).
    Protected against cross-site CSRF by SameSite=Lax session cookie policy.
    """
    session.clear()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('home'))


# ========================================================
# Dashboard Routes
# ========================================================
@app.route('/dashboard')
@login_required
def dashboard():
    """
    Routes users to their role-specific dashboard or admin portal.
    """
    if session.get('is_admin'):
        return redirect(url_for('admin_verifications'))
    if session.get('user_role') == 'mentor':
        return redirect(url_for('mentor_dashboard'))
    return redirect(url_for('mentee_dashboard'))


@app.route('/mentor/dashboard')
@login_required
def mentor_dashboard():
    """
    Improved Mentor Dashboard with profile completion, pending requests,
    accepted mentees, upcoming sessions, and quick actions.
    """
    if session.get('user_role') != 'mentor':
        flash('Unauthorized access: This area is restricted to Mentors only.', 'danger')
        return redirect(url_for('mentee_dashboard'))

    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    if not user:
        conn.close()
        session.clear()
        flash('Account not found. Please log in again.', 'warning')
        return redirect(url_for('login'))

    profile = conn.execute('SELECT * FROM mentor_profiles WHERE user_id = ?', (session['user_id'],)).fetchone()

    # Calculate profile completion percentage
    completion_pct = 0
    if profile:
        profile_fields = [
            profile['title'], profile['company'], profile['profile_pic_url'],
            profile['bio'], profile['skills'], profile['experience'],
            profile['education'], profile['availability'], profile['linkedin_url']
        ]
        filled_count = sum(1 for field in profile_fields if field and str(field).strip())
        completion_pct = int((filled_count / len(profile_fields)) * 100)

    # Query incoming mentorship requests for this mentor
    requests = conn.execute('''
        SELECT r.id, r.mentee_id, r.message, r.status, r.created_at,
               u.name as mentee_name, u.email as mentee_email
        FROM mentorship_requests r
        JOIN users u ON r.mentee_id = u.id
        WHERE r.mentor_id = ?
        ORDER BY r.created_at DESC
    ''', (session['user_id'],)).fetchall()

    # Query upcoming scheduled mentorship sessions for this mentor
    sessions_list = conn.execute('''
        SELECT s.id, s.session_date, s.session_time, s.topic, s.description, s.status, s.created_at,
               u.name as mentee_name, u.email as mentee_email
        FROM mentorship_sessions s
        JOIN users u ON s.mentee_id = u.id
        WHERE s.mentor_id = ?
        ORDER BY s.session_date ASC, s.session_time ASC
    ''', (session['user_id'],)).fetchall()

    conn.close()

    pending_count = sum(1 for r in requests if r['status'] == 'PENDING')
    accepted_count = sum(1 for r in requests if r['status'] == 'ACCEPTED')

    return render_template(
        'mentor/dashboard.html',
        user=user,
        profile=profile,
        completion_pct=completion_pct,
        requests=requests,
        sessions=sessions_list,
        pending_count=pending_count,
        accepted_count=accepted_count
    )


@app.route('/mentee/dashboard')
@login_required
def mentee_dashboard():
    """
    Improved Mentee Dashboard showing sent requests, accepted mentors,
    upcoming sessions, quick actions, and recommended mentors.
    """
    if session.get('user_role') != 'mentee':
        flash('Unauthorized access: This area is restricted to Mentees only.', 'danger')
        return redirect(url_for('mentor_dashboard'))

    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    if not user:
        conn.close()
        session.clear()
        flash('Account not found. Please log in again.', 'warning')
        return redirect(url_for('login'))

    # Query mentorship requests sent by this mentee
    requests = conn.execute('''
        SELECT r.id, r.mentor_id, r.message, r.status, r.created_at,
               u.name as mentor_name, p.title as mentor_title, p.company as mentor_company
        FROM mentorship_requests r
        JOIN users u ON r.mentor_id = u.id
        LEFT JOIN mentor_profiles p ON u.id = p.user_id
        WHERE r.mentee_id = ?
        ORDER BY r.created_at DESC
    ''', (session['user_id'],)).fetchall()

    # Query booked sessions for this mentee
    sessions_list = conn.execute('''
        SELECT s.id, s.session_date, s.session_time, s.topic, s.description, s.status, s.created_at,
               u.name as mentor_name, p.title as mentor_title, p.company as mentor_company
        FROM mentorship_sessions s
        JOIN users u ON s.mentor_id = u.id
        LEFT JOIN mentor_profiles p ON u.id = p.user_id
        WHERE s.mentee_id = ?
        ORDER BY s.session_date ASC, s.session_time ASC
    ''', (session['user_id'],)).fetchall()

    # Query 3 recommended mentors with active profiles
    recommended_mentors = conn.execute('''
        SELECT u.id as user_id, u.name, p.title, p.company, p.skills, p.availability, p.profile_pic_url
        FROM users u
        JOIN mentor_profiles p ON u.id = p.user_id
        WHERE u.role = 'mentor' AND u.verification_status = 'Verified' AND p.skills IS NOT NULL AND p.skills != ''
        ORDER BY u.id DESC LIMIT 3
    ''').fetchall()

    conn.close()

    sent_count = len(requests)
    pending_count = sum(1 for r in requests if r['status'] == 'PENDING')
    accepted_count = sum(1 for r in requests if r['status'] == 'ACCEPTED')

    return render_template(
        'mentee/dashboard.html',
        user=user,
        requests=requests,
        sessions=sessions_list,
        recommended_mentors=recommended_mentors,
        sent_count=sent_count,
        pending_count=pending_count,
        accepted_count=accepted_count
    )


@app.route('/mentor/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_mentor_profile():
    """
    Allows a mentor to create or update their profile.
    """
    if session.get('user_role') != 'mentor':
        flash('Unauthorized access: Only mentors can edit mentor profiles.', 'danger')
        return redirect(url_for('mentee_dashboard'))

    def safe_url(value):
        """
        Only allow http:// and https:// URLs.
        A 'javascript:' or 'data:' URL can execute code in the browser
        when placed inside an <a href> or <img src>.
        If the URL is invalid we simply treat it as empty (no link shown).
        """
        v = (value or '').strip()
        if v and not v.lower().startswith(('http://', 'https://')):
            return ''
        return v

    conn = get_db_connection()

    if request.method == 'POST':
        title           = request.form.get('title', '').strip()[:150]
        company         = request.form.get('company', '').strip()[:150]
        profile_pic_url = safe_url(request.form.get('profile_pic_url', ''))
        bio             = request.form.get('bio', '').strip()[:2000]
        skills          = request.form.get('skills', '').strip()[:300]
        experience      = request.form.get('experience', '').strip()[:300]
        education       = request.form.get('education', '').strip()[:300]
        availability    = request.form.get('availability', '').strip()[:200]
        linkedin_url    = safe_url(request.form.get('linkedin_url', ''))

        if not skills:
            flash('Please enter at least one skill to help mentees find you.', 'danger')
            profile = conn.execute('SELECT * FROM mentor_profiles WHERE user_id = ?', (session['user_id'],)).fetchone()
            conn.close()
            return render_template('mentor/edit_profile.html', profile=profile)

        conn.execute('''
            INSERT INTO mentor_profiles (
                user_id, title, company, profile_pic_url, bio, skills,
                experience, education, availability, linkedin_url, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                title = excluded.title,
                company = excluded.company,
                profile_pic_url = excluded.profile_pic_url,
                bio = excluded.bio,
                skills = excluded.skills,
                experience = excluded.experience,
                education = excluded.education,
                availability = excluded.availability,
                linkedin_url = excluded.linkedin_url,
                updated_at = CURRENT_TIMESTAMP;
        ''', (session['user_id'], title, company, profile_pic_url, bio, skills,
              experience, education, availability, linkedin_url))

        conn.commit()
        conn.close()

        flash('Your mentor profile has been saved successfully!', 'success')
        return redirect(url_for('mentor_dashboard'))

    profile = conn.execute('SELECT * FROM mentor_profiles WHERE user_id = ?', (session['user_id'],)).fetchone()
    conn.close()
    return render_template('mentor/edit_profile.html', profile=profile)


# ========================================================
# Mentorship Request Workflow Routes
# ========================================================
@app.route('/mentors/<int:mentor_id>/request', methods=['POST'])
@login_required
def send_mentorship_request(mentor_id):
    """
    Allows a mentee to send a mentorship request to a mentor with a message.
    Prevents duplicate PENDING requests to the same mentor.
    Requires both mentee and mentor to have 'Verified' status.
    """
    if session.get('user_role') != 'mentee':
        flash('Only mentees can send mentorship requests.', 'danger')
        return redirect(url_for('mentor_profile', mentor_id=mentor_id))

    conn = get_db_connection()

    # Check mentee verification status
    mentee = conn.execute('SELECT verification_status FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    if not mentee or mentee['verification_status'] != 'Verified':
        conn.close()
        status_text = mentee['verification_status'] if mentee else 'Pending'
        flash(f'Your student account verification is currently "{status_text}". Only verified students can send mentorship requests.', 'warning')
        return redirect(url_for('mentor_profile', mentor_id=mentor_id))

    mentor = conn.execute(
        'SELECT name, verification_status FROM users WHERE id = ? AND role = "mentor"', (mentor_id,)
    ).fetchone()

    if not mentor:
        conn.close()
        flash('Mentor not found.', 'warning')
        return redirect(url_for('mentor_list'))

    if mentor['verification_status'] != 'Verified':
        conn.close()
        flash('This mentor is not yet verified and cannot receive mentorship requests at this time.', 'warning')
        return redirect(url_for('mentor_profile', mentor_id=mentor_id))

    message = request.form.get('message', '').strip()[:1000]   # cap at 1000 chars
    if not message:
        conn.close()
        flash('Please include a short message explaining your learning goals.', 'danger')
        return redirect(url_for('mentor_profile', mentor_id=mentor_id))

    # Duplicate check: prevent sending another request if one is already PENDING or ACCEPTED
    existing_request = conn.execute('''
        SELECT id, status FROM mentorship_requests 
        WHERE mentee_id = ? AND mentor_id = ? AND status IN ('PENDING', 'ACCEPTED')
    ''', (session['user_id'], mentor_id)).fetchone()

    if existing_request:
        conn.close()
        if existing_request['status'] == 'PENDING':
            flash('You already have a pending mentorship request with this mentor. Please wait for their response.', 'warning')
        else:
            flash('You already have an accepted mentorship request with this mentor.', 'info')
        return redirect(url_for('mentor_profile', mentor_id=mentor_id))

    conn.execute('''
        INSERT INTO mentorship_requests (mentee_id, mentor_id, message, status)
        VALUES (?, ?, ?, 'PENDING')
    ''', (session['user_id'], mentor_id, message))
    conn.commit()
    conn.close()

    flash(f'Your mentorship request was sent to {mentor["name"]}!', 'success')
    return redirect(url_for('mentee_dashboard'))


@app.route('/mentorship-requests/<int:request_id>/accept', methods=['POST'])
@login_required
def accept_request(request_id):
    """
    Allows a mentor to accept an incoming mentorship request.
    """
    if session.get('user_role') != 'mentor':
        flash('Unauthorized access: Only mentors can accept requests.', 'danger')
        return redirect(url_for('dashboard'))

    conn = get_db_connection()
    req = conn.execute(
        'SELECT * FROM mentorship_requests WHERE id = ? AND mentor_id = ?',
        (request_id, session['user_id'])
    ).fetchone()

    if not req:
        conn.close()
        flash('Request not found or access denied.', 'danger')
        return redirect(url_for('mentor_dashboard'))

    if req['status'] != 'PENDING':
        conn.close()
        flash(f'This request has already been marked as {req["status"]}.', 'info')
        return redirect(url_for('mentor_dashboard'))

    conn.execute('''
        UPDATE mentorship_requests 
        SET status = 'ACCEPTED', updated_at = CURRENT_TIMESTAMP 
        WHERE id = ?
    ''', (request_id,))
    conn.commit()
    conn.close()

    flash('You accepted the mentorship request!', 'success')
    return redirect(url_for('mentor_dashboard'))


@app.route('/mentorship-requests/<int:request_id>/reject', methods=['POST'])
@login_required
def reject_request(request_id):
    """
    Allows a mentor to reject an incoming mentorship request.
    """
    if session.get('user_role') != 'mentor':
        flash('Unauthorized access: Only mentors can reject requests.', 'danger')
        return redirect(url_for('dashboard'))

    conn = get_db_connection()
    req = conn.execute(
        'SELECT * FROM mentorship_requests WHERE id = ? AND mentor_id = ?',
        (request_id, session['user_id'])
    ).fetchone()

    if not req:
        conn.close()
        flash('Request not found or access denied.', 'danger')
        return redirect(url_for('mentor_dashboard'))

    if req['status'] != 'PENDING':
        conn.close()
        flash(f'This request has already been marked as {req["status"]}.', 'info')
        return redirect(url_for('mentor_dashboard'))

    conn.execute('''
        UPDATE mentorship_requests 
        SET status = 'REJECTED', updated_at = CURRENT_TIMESTAMP 
        WHERE id = ?
    ''', (request_id,))
    conn.commit()
    conn.close()

    flash('The mentorship request was declined.', 'info')
    return redirect(url_for('mentor_dashboard'))


# ========================================================
# Session Booking Routes
# ========================================================
@app.route('/sessions/book/<int:request_id>', methods=['GET', 'POST'])
@login_required
def book_session(request_id):
    """
    Allows a mentee to schedule a 1-on-1 session after their mentorship request is accepted.
    Validates date to prevent bookings in the past.
    """
    if session.get('user_role') != 'mentee':
        flash('Only mentees can book mentorship sessions.', 'danger')
        return redirect(url_for('dashboard'))

    conn = get_db_connection()

    req = conn.execute('''
        SELECT * FROM mentorship_requests 
        WHERE id = ? AND mentee_id = ? AND status = 'ACCEPTED'
    ''', (request_id, session['user_id'])).fetchone()

    if not req:
        conn.close()
        flash('Invalid request: A session can only be booked after your mentorship request is accepted.', 'danger')
        return redirect(url_for('mentee_dashboard'))

    mentor = conn.execute('''
        SELECT u.id as user_id, u.name, u.email, p.title, p.company, p.availability 
        FROM users u 
        LEFT JOIN mentor_profiles p ON u.id = p.user_id 
        WHERE u.id = ?
    ''', (req['mentor_id'],)).fetchone()

    today_str = date.today().isoformat()

    if request.method == 'POST':
        session_date = request.form.get('session_date', '').strip()
        session_time = request.form.get('session_time', '').strip()
        topic        = request.form.get('topic', '').strip()[:200]       # cap at 200 chars
        description  = request.form.get('description', '').strip()[:1000] # cap at 1000 chars

        if not session_date or not session_time or not topic:
            flash('Date, preferred time, and topic are required to schedule a session.', 'danger')
            conn.close()
            return render_template('sessions/book.html', mentor=mentor, request_record=req, today=today_str)

        try:
            booking_date = datetime.strptime(session_date, '%Y-%m-%d').date()
            if booking_date < date.today():
                flash('Cannot schedule a session on a past date. Please select today or a future date.', 'danger')
                conn.close()
                return render_template('sessions/book.html', mentor=mentor, request_record=req, today=today_str)
        except ValueError:
            flash('Invalid date selected. Please use a valid calendar date.', 'danger')
            conn.close()
            return render_template('sessions/book.html', mentor=mentor, request_record=req, today=today_str)

        # Validate time is a proper HH:MM value to prevent arbitrary strings in the DB.
        try:
            datetime.strptime(session_time, '%H:%M')
        except ValueError:
            flash('Invalid time selected. Please use a valid HH:MM time format.', 'danger')
            conn.close()
            return render_template('sessions/book.html', mentor=mentor, request_record=req, today=today_str)

        conn.execute('''
            INSERT INTO mentorship_sessions (
                request_id, mentee_id, mentor_id, session_date, session_time, topic, description, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'SCHEDULED')
        ''', (request_id, session['user_id'], req['mentor_id'], session_date, session_time, topic, description))
        conn.commit()
        conn.close()

        flash(f'Your mentorship session with {mentor["name"]} has been scheduled for {session_date} at {session_time}!', 'success')
        return redirect(url_for('mentee_dashboard'))

    conn.close()
    return render_template('sessions/book.html', mentor=mentor, request_record=req, today=today_str)


# ========================================================
# Administrator Verification Management Routes
# ========================================================
@app.route('/admin/verifications')
@admin_required
def admin_verifications():
    """
    Admin verification dashboard displaying mentors and students.
    Only authorized administrators can access.
    """
    conn = get_db_connection()
    mentors = conn.execute('''
        SELECT u.id, u.name, u.email, u.verification_status, u.id_proof_filename,
               u.verified_at, u.admin_notes, u.created_at,
               p.title, p.company, p.skills, p.experience, p.bio
        FROM users u
        LEFT JOIN mentor_profiles p ON u.id = p.user_id
        WHERE u.role = 'mentor'
        ORDER BY CASE u.verification_status
            WHEN 'Pending' THEN 1
            WHEN 'Rejected' THEN 2
            WHEN 'Verified' THEN 3
            ELSE 4 END, u.id DESC
    ''').fetchall()

    students = conn.execute('''
        SELECT u.id, u.name, u.email, u.verification_status, u.college_name,
               u.college_email, u.college_id_filename, u.verified_at,
               u.admin_notes, u.created_at
        FROM users u
        WHERE u.role = 'mentee'
        ORDER BY CASE u.verification_status
            WHEN 'Pending' THEN 1
            WHEN 'Rejected' THEN 2
            WHEN 'Verified' THEN 3
            ELSE 4 END, u.id DESC
    ''').fetchall()
    conn.close()

    pending_mentors = [m for m in mentors if m['verification_status'] == 'Pending']
    pending_students = [s for s in students if s['verification_status'] == 'Pending']

    return render_template(
        'admin/verifications.html',
        mentors=mentors,
        students=students,
        pending_mentors=pending_mentors,
        pending_students=pending_students
    )


@app.route('/admin/verifications/document/<int:user_id>')
@admin_required
def view_verification_document(user_id):
    """
    Securely serves private verification document to authorized administrators.
    Never exposes internal filesystem paths or serves through static folder.
    """
    conn = get_db_connection()
    user = conn.execute(
        'SELECT id, role, id_proof_filename, college_id_filename FROM users WHERE id = ?',
        (user_id,)
    ).fetchone()
    conn.close()

    if not user:
        flash('User record not found.', 'danger')
        return redirect(url_for('admin_verifications'))

    filename = None
    subfolder = None
    if user['role'] == 'mentor' and user['id_proof_filename']:
        filename = user['id_proof_filename']
        subfolder = 'id_proofs'
    elif user['role'] == 'mentee' and user['college_id_filename']:
        filename = user['college_id_filename']
        subfolder = 'college_ids'
    elif user['id_proof_filename']:
        filename = user['id_proof_filename']
        subfolder = 'id_proofs'
    elif user['college_id_filename']:
        filename = user['college_id_filename']
        subfolder = 'college_ids'

    if not filename or not subfolder:
        flash('No verification document file was found for this user.', 'warning')
        return redirect(url_for('admin_verifications'))

    doc_dir = os.path.join(UPLOAD_BASE, subfolder)
    return send_from_directory(doc_dir, filename)


@app.route('/admin/verifications/mentor/<int:user_id>/approve', methods=['POST'])
@admin_required
def approve_mentor_verification(user_id):
    """
    Approves mentor ID proof and makes mentor active in public directory.
    """
    conn = get_db_connection()
    user = conn.execute('SELECT id, name, role FROM users WHERE id = ? AND role = "mentor"', (user_id,)).fetchone()
    if not user:
        conn.close()
        flash('Mentor not found.', 'danger')
        return redirect(url_for('admin_verifications'))

    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn.execute('''
        UPDATE users 
        SET verification_status = 'Verified', verified_at = ? 
        WHERE id = ?
    ''', (now_str, user_id))
    conn.execute('''
        UPDATE verifications 
        SET status = 'Verified', reviewed_at = ? 
        WHERE user_id = ?
    ''', (now_str, user_id))
    conn.commit()
    conn.close()

    flash(f'Mentor "{user["name"]}" has been approved and verified! They are now discoverable for mentorship.', 'success')
    return redirect(url_for('admin_verifications'))


@app.route('/admin/verifications/mentor/<int:user_id>/reject', methods=['POST'])
@admin_required
def reject_mentor_verification(user_id):
    """
    Rejects mentor ID proof. Mentor is not discoverable and cannot receive requests.
    """
    conn = get_db_connection()
    user = conn.execute('SELECT id, name, role FROM users WHERE id = ? AND role = "mentor"', (user_id,)).fetchone()
    if not user:
        conn.close()
        flash('Mentor not found.', 'danger')
        return redirect(url_for('admin_verifications'))

    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn.execute('''
        UPDATE users 
        SET verification_status = 'Rejected', verified_at = ? 
        WHERE id = ?
    ''', (now_str, user_id))
    conn.execute('''
        UPDATE verifications 
        SET status = 'Rejected', reviewed_at = ? 
        WHERE user_id = ?
    ''', (now_str, user_id))
    conn.commit()
    conn.close()

    flash(f'Mentor "{user["name"]}" verification was marked as Rejected.', 'info')
    return redirect(url_for('admin_verifications'))


@app.route('/admin/verifications/student/<int:user_id>/approve', methods=['POST'])
@admin_required
def approve_student_verification(user_id):
    """
    Approves student college ID card and allows student to send mentorship requests.
    """
    conn = get_db_connection()
    user = conn.execute('SELECT id, name, role FROM users WHERE id = ? AND role = "mentee"', (user_id,)).fetchone()
    if not user:
        conn.close()
        flash('Student not found.', 'danger')
        return redirect(url_for('admin_verifications'))

    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn.execute('''
        UPDATE users 
        SET verification_status = 'Verified', verified_at = ? 
        WHERE id = ?
    ''', (now_str, user_id))
    conn.execute('''
        UPDATE verifications 
        SET status = 'Verified', reviewed_at = ? 
        WHERE user_id = ?
    ''', (now_str, user_id))
    conn.commit()
    conn.close()

    flash(f'Student "{user["name"]}" has been approved and verified! They can now send mentorship requests.', 'success')
    return redirect(url_for('admin_verifications'))


@app.route('/admin/verifications/student/<int:user_id>/reject', methods=['POST'])
@admin_required
def reject_student_verification(user_id):
    """
    Rejects student college ID card. Student cannot send mentorship requests.
    """
    conn = get_db_connection()
    user = conn.execute('SELECT id, name, role FROM users WHERE id = ? AND role = "mentee"', (user_id,)).fetchone()
    if not user:
        conn.close()
        flash('Student not found.', 'danger')
        return redirect(url_for('admin_verifications'))

    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn.execute('''
        UPDATE users 
        SET verification_status = 'Rejected', verified_at = ? 
        WHERE id = ?
    ''', (now_str, user_id))
    conn.execute('''
        UPDATE verifications 
        SET status = 'Rejected', reviewed_at = ? 
        WHERE user_id = ?
    ''', (now_str, user_id))
    conn.commit()
    conn.close()

    flash(f'Student "{user["name"]}" verification was marked as Rejected.', 'info')
    return redirect(url_for('admin_verifications'))


if __name__ == '__main__':
    app.run(debug=True, port=5000)
