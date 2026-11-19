CREATE DATABASE IF NOT EXISTS job_recruitment CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE job_recruitment;

CREATE TABLE IF NOT EXISTS admin (
  admin_id INT AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(50) NOT NULL UNIQUE,
  email VARCHAR(120) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS companies (
  company_id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(150) NOT NULL,
  industry VARCHAR(100),
  website VARCHAR(200),
  location VARCHAR(120),
  description TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS recruiters (
  recruiter_id INT AUTO_INCREMENT PRIMARY KEY,
  company_id INT NULL,
  full_name VARCHAR(100) NOT NULL,
  email VARCHAR(120) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  phone VARCHAR(20),
  is_active TINYINT(1) NOT NULL DEFAULT 1,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (company_id) REFERENCES companies(company_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS job_seekers (
  seeker_id INT AUTO_INCREMENT PRIMARY KEY,
  full_name VARCHAR(100) NOT NULL,
  email VARCHAR(120) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  phone VARCHAR(20),
  location VARCHAR(120),
  skills VARCHAR(500),
  education VARCHAR(200),
  experience_years INT NOT NULL DEFAULT 0,
  about TEXT,
  is_active TINYINT(1) NOT NULL DEFAULT 1,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS resumes (
  resume_id INT AUTO_INCREMENT PRIMARY KEY,
  seeker_id INT NOT NULL,
  filename VARCHAR(120) NOT NULL,
  original_name VARCHAR(200) NOT NULL,
  uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (seeker_id) REFERENCES job_seekers(seeker_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS jobs (
  job_id INT AUTO_INCREMENT PRIMARY KEY,
  recruiter_id INT NOT NULL,
  company_id INT NOT NULL,
  title VARCHAR(150) NOT NULL,
  description TEXT NOT NULL,
  skills_required VARCHAR(500),
  location VARCHAR(120) NOT NULL,
  job_type VARCHAR(30) NOT NULL DEFAULT 'Full-time',
  salary_min DECIMAL(6,2) NULL,
  salary_max DECIMAL(6,2) NULL,
  vacancies INT NOT NULL DEFAULT 1,
  deadline DATE NULL,
  status ENUM('Open','Closed') NOT NULL DEFAULT 'Open',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (recruiter_id) REFERENCES recruiters(recruiter_id) ON DELETE CASCADE,
  FOREIGN KEY (company_id) REFERENCES companies(company_id) ON DELETE CASCADE,
  INDEX idx_jobs_status (status),
  INDEX idx_jobs_location (location)
);

CREATE TABLE IF NOT EXISTS applications (
  application_id INT AUTO_INCREMENT PRIMARY KEY,
  job_id INT NOT NULL,
  seeker_id INT NOT NULL,
  resume_id INT NULL,
  cover_letter TEXT,
  status ENUM('Applied','Shortlisted','Rejected','Selected') NOT NULL DEFAULT 'Applied',
  applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_job_seeker (job_id, seeker_id),
  FOREIGN KEY (job_id) REFERENCES jobs(job_id) ON DELETE CASCADE,
  FOREIGN KEY (seeker_id) REFERENCES job_seekers(seeker_id) ON DELETE CASCADE,
  FOREIGN KEY (resume_id) REFERENCES resumes(resume_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS interviews (
  interview_id INT AUTO_INCREMENT PRIMARY KEY,
  application_id INT NOT NULL,
  interview_date DATE NOT NULL,
  interview_time TIME NOT NULL,
  mode ENUM('Online','In-person','Phone') NOT NULL DEFAULT 'Online',
  location_link VARCHAR(255),
  details TEXT,
  status ENUM('Scheduled','Rescheduled','Completed','Cancelled') NOT NULL DEFAULT 'Scheduled',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (application_id) REFERENCES applications(application_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS notifications (
  notification_id INT AUTO_INCREMENT PRIMARY KEY,
  user_type ENUM('seeker','recruiter') NOT NULL,
  user_id INT NOT NULL,
  message VARCHAR(400) NOT NULL,
  is_read TINYINT(1) NOT NULL DEFAULT 0,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_notif_user (user_type, user_id, is_read)
);
