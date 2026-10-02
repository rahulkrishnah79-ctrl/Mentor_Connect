-- schema.sql
-- Database schema for MentorConnect

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('mentor', 'mentee')),
    college_name TEXT,
    college_email TEXT,
    verification_status TEXT NOT NULL DEFAULT 'Verified' CHECK(verification_status IN ('Pending', 'Verified', 'Rejected')),
    id_proof_filename TEXT,
    college_id_filename TEXT,
    verified_at TIMESTAMP,
    admin_notes TEXT,
    is_admin INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS mentor_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER UNIQUE NOT NULL,
    title TEXT,
    company TEXT,
    profile_pic_url TEXT,
    bio TEXT,
    skills TEXT,
    experience TEXT,
    education TEXT,
    availability TEXT,
    linkedin_url TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS verifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    document_type TEXT NOT NULL CHECK(document_type IN ('mentor_photo_id', 'student_college_id')),
    filename TEXT NOT NULL,
    original_filename TEXT,
    status TEXT NOT NULL DEFAULT 'Pending' CHECK(status IN ('Pending', 'Verified', 'Rejected')),
    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TIMESTAMP,
    admin_notes TEXT,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS mentorship_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mentee_id INTEGER NOT NULL,
    mentor_id INTEGER NOT NULL,
    message TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING', 'ACCEPTED', 'REJECTED')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (mentee_id) REFERENCES users (id) ON DELETE CASCADE,
    FOREIGN KEY (mentor_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS mentorship_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id INTEGER NOT NULL,
    mentee_id INTEGER NOT NULL,
    mentor_id INTEGER NOT NULL,
    session_date TEXT NOT NULL,
    session_time TEXT NOT NULL,
    topic TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'SCHEDULED' CHECK(status IN ('SCHEDULED', 'COMPLETED', 'CANCELLED')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (request_id) REFERENCES mentorship_requests (id) ON DELETE CASCADE,
    FOREIGN KEY (mentee_id) REFERENCES users (id) ON DELETE CASCADE,
    FOREIGN KEY (mentor_id) REFERENCES users (id) ON DELETE CASCADE
);
