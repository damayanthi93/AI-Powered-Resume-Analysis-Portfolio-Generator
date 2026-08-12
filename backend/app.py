from flask import Flask, request, send_file, send_from_directory, session, jsonify, g
import pdfplumber
from docx import Document
import json
import os
import zipfile
import io
import sqlite3
import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from groq import Groq
from dotenv import load_dotenv

# ------------------ CONFIG ------------------

# Groq API Client Setup

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

client = Groq(api_key=GROQ_API_KEY)

app = Flask(__name__)
app.secret_key = "career_dashboard_super_secret_key_12345"
app.permanent_session_lifetime = datetime.timedelta(days=7)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_FOLDER = os.path.abspath(os.path.join(BASE_DIR, "..", "frontend"))
DATABASE = os.path.join(BASE_DIR, "database.db")

# ------------------ DATABASE SETUP ------------------

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = get_db()
        cursor = db.cursor()
        
        # Users Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Resumes (ATS Analyses) Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS resumes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                filename TEXT NOT NULL,
                upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                parsed_data TEXT NOT NULL,
                ats_score INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            )
        """)
        
        # Generated Portfolios Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS portfolios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                resume_id INTEGER,
                template_id TEXT NOT NULL,
                html_content TEXT NOT NULL,
                css_content TEXT NOT NULL,
                deployed_slug TEXT UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
                FOREIGN KEY (resume_id) REFERENCES resumes (id) ON DELETE SET NULL
            )
        """)
        
        db.commit()

# Initialize tables
init_db()

# ------------------ TEXT EXTRACTION ------------------

def extract_text(file):
    filename = file.filename.lower()
    try:
        if filename.endswith(".pdf"):
            text = ""
            with pdfplumber.open(file) as pdf:
                for page in pdf.pages:
                    if page.extract_text():
                        text += page.extract_text() + "\n"
            return text if text.strip() else "Error: Empty PDF"

        elif filename.endswith(".docx"):
            doc = Document(file)
            return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
            
    except Exception as e:
        return f"Error: Text extraction failed ({str(e)})"

    return "Error: Upload PDF or DOCX only."

# ------------------ GROQ AI PARSE ------------------

def ai_parse_and_analyze(text):
    prompt = f"""
You are an expert ATS (Applicant Tracking System) recruiter and resume optimization AI.
Analyze the following resume text. Determine its ATS suitability, extract profile elements, and generate career growth recommendations.

Return ONLY a valid JSON object matching this structure EXACTLY:
{{
  "candidate": {{
    "name": "Extract full name, fallback to empty string if not found",
    "email": "Extract email, fallback to empty string if not found",
    "phone": "Extract phone, fallback to empty string if not found",
    "location": "Extract location, fallback to empty string if not found",
    "objective": "A compelling, modern summary/objective statement summarizing the candidate's career",
    "education": ["List of schools, degrees, and graduation years/majors"],
    "skills": ["List of core technical skills / tools"],
    "experience": ["List of companies, roles, and bullet points of key contributions"],
    "projects": ["List of projects, repositories, or description of things built"]
  }},
  "ats_score": 85,
  "missing_keywords": ["Keyword1", "Keyword2"],
  "strengths": ["Strength 1", "Strength 2"],
  "weaknesses": ["Weakness 1", "Weakness 2"],
  "suggestions": ["Actionable improvement suggestion 1", "Actionable improvement suggestion 2"],
  "career_recommendations": {{
    "skills": ["Skill to learn 1", "Skill to learn 2"],
    "projects": ["Project suggestion 1 with suggested tech stack", "Project suggestion 2"],
    "suggestions": ["Career pathway advice 1", "Career pathway advice 2"]
  }}
}}

Ensure all fields in the "candidate" dictionary exist. If any fields are missing in the resume text, represent them as empty strings or empty arrays.
Return ONLY the raw JSON output. Do not include markdown formatting or backticks (like ```json ... ```).

Resume Text:
{text}
"""
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": "You extract structured resume analytics and return raw JSON data only."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.2
    )
    
    response_text = response.choices[0].message.content.strip()
    return extract_json_from_response(response_text)

def extract_json_from_response(text):
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    
    try:
        start_idx = text.find("{")
        end_idx = text.rfind("}")
        if start_idx != -1 and end_idx != -1:
            text = text[start_idx:end_idx+1]
        return json.loads(text)
    except Exception as e:
        raise ValueError(f"Failed to parse JSON. Error: {e}. Output text was: {text}")

# ------------------ PORTFOLIO TEMPLATE GENERATORS ------------------

def format_list_to_html(lst):
    if not lst:
        return "<li>Information not specified</li>"
    
    html = ""
    for item in lst:
        item_str = str(item).strip()
        if not item_str:
            continue
        parts = item_str.split(":", 1)
        if len(parts) == 2 and len(parts[0]) < 80:
            title = parts[0].strip()
            desc = parts[1].strip()
            html += f"""
            <div class="card">
                <div class="item-title">{title}</div>
                <p style="margin-top: 8px; font-size: 0.95rem; opacity: 0.85;">{desc}</p>
            </div>
            """
        else:
            html += f"""
            <div class="card">
                <p style="font-size: 0.95rem; line-height: 1.5; margin: 0;">{item_str}</p>
            </div>
            """
    return html

def generate_portfolio_html_css(data, template_id, slug=None):
    candidate = data.get("candidate", {})
    name = candidate.get("name") or "Professional Candidate"
    objective = candidate.get("objective") or "Results-oriented professional."
    email = candidate.get("email") or ""
    phone = candidate.get("phone") or ""
    location = candidate.get("location") or ""
    
    email_html = f'<span>✉ {email}</span>' if email else ''
    phone_html = f'<span>📞 {phone}</span>' if phone else ''
    location_html = f'<span>📍 {location}</span>' if location else ''
    
    skills = candidate.get("skills", [])
    skills_html = "".join(f'<span class="skill-tag">{s}</span>' for s in skills) if skills else '<span class="skill-tag">Professional Skills</span>'
    
    experience_html = format_list_to_html(candidate.get("experience", []))
    projects_html = format_list_to_html(candidate.get("projects", []))
    education_html = format_list_to_html(candidate.get("education", []))
    
    year = datetime.datetime.now().year
    
    if template_id == "minimalist":
        css = """
body { font-family: 'Inter', sans-serif; background-color: #fafafa; color: #1f2937; line-height: 1.6; margin: 0; padding: 0; }
.container { max-width: 800px; margin: 60px auto; padding: 0 20px; }
header { margin-bottom: 40px; border-bottom: 1px solid #e5e7eb; padding-bottom: 30px; }
h1 { font-family: 'Playfair Display', Georgia, serif; font-size: 3rem; margin: 0 0 10px 0; color: #111827; }
.subtitle { font-size: 1.25rem; color: #4b5563; margin-bottom: 15px; font-weight: 300; }
.contact-info { display: flex; flex-wrap: wrap; gap: 20px; font-size: 0.9rem; color: #6b7280; }
.contact-info span { display: flex; align-items: center; gap: 5px; }
h2 { font-family: 'Playfair Display', Georgia, serif; font-size: 1.8rem; margin: 40px 0 20px 0; color: #111827; border-bottom: 1px solid #f3f4f6; padding-bottom: 8px; }
.section { margin-bottom: 30px; }
.skills-list { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 10px; }
.skill-tag { background-color: #f3f4f6; color: #374151; padding: 6px 12px; border-radius: 4px; font-size: 0.85rem; font-weight: 500; border: 1px solid #e5e7eb; }
.card { background: #fff; padding: 15px; border-radius: 6px; border: 1px solid #e5e7eb; margin-bottom: 15px; }
.item-title { font-weight: 600; font-size: 1.1rem; color: #111827; }
footer { margin-top: 80px; border-top: 1px solid #e5e7eb; padding-top: 20px; text-align: center; font-size: 0.85rem; color: #9ca3af; }
"""
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{name} | Portfolio</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&family=Playfair+Display:ital,wght@0,600;1,400&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="portfolio.css">
</head>
<body>
    <div class="container">
        <header>
            <h1>{name}</h1>
            <div class="subtitle">{objective}</div>
            <div class="contact-info">
                {email_html}
                {phone_html}
                {location_html}
            </div>
        </header>
        
        <section class="section">
            <h2>Skills</h2>
            <div class="skills-list">
                {skills_html}
            </div>
        </section>

        <section class="section">
            <h2>Experience</h2>
            {experience_html}
        </section>

        <section class="section">
            <h2>Projects</h2>
            {projects_html}
        </section>

        <section class="section">
            <h2>Education</h2>
            {education_html}
        </section>

        <footer>
            <p>&copy; {year} {name}. All rights reserved.</p>
        </footer>
    </div>
</body>
</html>"""

    elif template_id == "glassmorphism":
        css = """
body { font-family: 'Outfit', sans-serif; background-color: #080A10; background-image: radial-gradient(circle at 10% 20%, rgba(59, 130, 246, 0.12) 0%, transparent 45%), radial-gradient(circle at 90% 80%, rgba(139, 92, 246, 0.12) 0%, transparent 45%); color: #f3f4f6; line-height: 1.6; margin: 0; padding: 0; min-height: 100vh; }
.container { max-width: 900px; margin: 60px auto; padding: 0 20px; }
header { background: rgba(17, 24, 39, 0.45); backdrop-filter: blur(16px); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 24px; padding: 40px; margin-bottom: 40px; box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.3); }
h1 { font-size: 3.5rem; font-weight: 800; margin: 0 0 10px 0; background: linear-gradient(135deg, #60a5fa, #c084fc); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.subtitle { font-size: 1.3rem; color: #cbd5e1; margin-bottom: 20px; font-weight: 300; }
.contact-info { display: flex; flex-wrap: wrap; gap: 20px; font-size: 0.95rem; color: #94a3b8; }
.contact-info span { display: flex; align-items: center; gap: 8px; background: rgba(255, 255, 255, 0.05); padding: 5px 12px; border-radius: 30px; border: 1px solid rgba(255, 255, 255, 0.05); }
h2 { font-size: 2.0rem; font-weight: 700; margin: 40px 0 20px 0; color: #fff; display: flex; align-items: center; gap: 10px; }
h2::after { content: ''; flex-grow: 1; height: 1px; background: linear-gradient(90deg, rgba(96, 165, 250, 0.5), transparent); margin-left: 15px; }
.card { background: rgba(17, 24, 39, 0.25); backdrop-filter: blur(10px); border: 1px solid rgba(255, 255, 255, 0.05); border-radius: 16px; padding: 25px; margin-bottom: 20px; transition: transform 0.3s, border-color 0.3s, box-shadow 0.3s; }
.card:hover { transform: translateY(-3px); border-color: rgba(96, 165, 250, 0.3); box-shadow: 0 10px 25px -5px rgba(59, 130, 246, 0.15); }
.skills-list { display: flex; flex-wrap: wrap; gap: 10px; }
.skill-tag { background: linear-gradient(135deg, rgba(59, 130, 246, 0.15), rgba(139, 92, 246, 0.15)); border: 1px solid rgba(255, 255, 255, 0.08); color: #e2e8f0; padding: 8px 16px; border-radius: 50px; font-size: 0.9rem; font-weight: 500; transition: all 0.3s; }
.skill-tag:hover { border-color: rgba(96, 165, 250, 0.5); transform: scale(1.05); }
.item-title { font-weight: 700; font-size: 1.2rem; color: #fff; }
footer { margin-top: 80px; text-align: center; font-size: 0.9rem; color: #64748b; padding-bottom: 40px; }
"""
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{name} | Portfolio</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="portfolio.css">
</head>
<body>
    <div class="container">
        <header>
            <h1>{name}</h1>
            <div class="subtitle">{objective}</div>
            <div class="contact-info">
                {email_html}
                {phone_html}
                {location_html}
            </div>
        </header>
        
        <section class="section">
            <h2>Skills</h2>
            <div class="skills-list">
                {skills_html}
            </div>
        </section>

        <section class="section">
            <h2>Experience</h2>
            {experience_html}
        </section>

        <section class="section">
            <h2>Projects</h2>
            {projects_html}
        </section>

        <section class="section">
            <h2>Education</h2>
            {education_html}
        </section>

        <footer>
            <p>&copy; {year} {name}. Powered by AI Career Hub.</p>
        </footer>
    </div>
</body>
</html>"""

    else:  # creative
        css = """
body { font-family: 'Poppins', sans-serif; background-color: #f7fafc; color: #2d3748; line-height: 1.6; margin: 0; padding: 0; }
.header-bg { background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%); color: #fff; padding: 80px 0 60px 0; text-align: center; border-radius: 0 0 40px 40px; box-shadow: 0 10px 30px rgba(79, 70, 229, 0.15); }
.container { max-width: 900px; margin: 0 auto; padding: 0 20px; }
.header-content { max-width: 800px; margin: 0 auto; }
h1 { font-size: 3.5rem; font-weight: 800; margin: 0; letter-spacing: -1px; }
.subtitle { font-size: 1.3rem; opacity: 0.95; margin-top: 15px; font-weight: 300; }
.contact-info { display: flex; justify-content: center; flex-wrap: wrap; gap: 15px; font-size: 0.95rem; margin-top: 25px; }
.contact-info span { background: rgba(255, 255, 255, 0.18); padding: 6px 18px; border-radius: 30px; backdrop-filter: blur(6px); border: 1px solid rgba(255,255,255,0.1); }
.main-content { margin-top: 40px; }
h2 { font-size: 1.8rem; font-weight: 700; color: #1e1b4b; margin: 40px 0 20px 0; display: inline-block; position: relative; }
h2::after { content: ''; display: block; width: 45px; height: 4px; background: #4f46e5; border-radius: 2px; margin-top: 6px; }
.card { background: #fff; border-radius: 16px; padding: 25px; margin-bottom: 20px; box-shadow: 0 4px 20px rgba(0, 0, 0, 0.03); border-left: 5px solid #4f46e5; transition: transform 0.3s; }
.card:hover { transform: translateY(-3px); box-shadow: 0 10px 25px rgba(0, 0, 0, 0.06); }
.skills-list { display: flex; flex-wrap: wrap; gap: 10px; background: #fff; padding: 25px; border-radius: 16px; box-shadow: 0 4px 20px rgba(0, 0, 0, 0.03); }
.skill-tag { background: #f1f5f9; color: #4f46e5; padding: 8px 18px; border-radius: 10px; font-size: 0.9rem; font-weight: 600; border: 1px solid #e2e8f0; transition: all 0.3s; }
.skill-tag:hover { background: #4f46e5; color: #fff; transform: translateY(-2px); }
.item-title { font-weight: 700; font-size: 1.15rem; color: #1e293b; }
footer { margin-top: 80px; text-align: center; font-size: 0.9rem; color: #94a3b8; padding: 40px 0; }
"""
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{name} | Portfolio</title>
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="portfolio.css">
</head>
<body>
    <div class="header-bg">
        <div class="container header-content">
            <h1>{name}</h1>
            <div class="subtitle">{objective}</div>
            <div class="contact-info">
                {email_html}
                {phone_html}
                {location_html}
            </div>
        </div>
    </div>
    
    <div class="container main-content">
        <section class="section">
            <h2>Core Skills</h2>
            <div class="skills-list">
                {skills_html}
            </div>
        </section>

        <section class="section">
            <h2>Professional Experience</h2>
            {experience_html}
        </section>

        <section class="section">
            <h2>Key Projects</h2>
            {projects_html}
        </section>

        <section class="section">
            <h2>Education</h2>
            {education_html}
        </section>

        <footer>
            <p>&copy; {year} {name} • Designed Creatively.</p>
        </footer>
    </div>
</body>
</html>"""

    return html, css

# ------------------ AUTHENTICATION ENDPOINTS ------------------

@app.route("/api/auth/signup", methods=["POST"])
def auth_signup():
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    
    if not name or not email or not password:
        return jsonify({"error": "Missing name, email, or password"}), 400
        
    db = get_db()
    cursor = db.cursor()
    
    try:
        password_hash = generate_password_hash(password)
        cursor.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (name, email, password_hash)
        )
        db.commit()
        
        # Get user ID
        user_id = cursor.lastrowid
        session.permanent = True
        session["user_id"] = user_id
        session["user_name"] = name
        session["user_email"] = email
        
        return jsonify({
            "success": True,
            "message": "User registered successfully",
            "user": {"name": name, "email": email}
        })
        
    except sqlite3.IntegrityError:
        return jsonify({"error": "An account with this email already exists"}), 409
    except Exception as e:
        return jsonify({"error": f"Registration failed: {str(e)}"}), 500

@app.route("/api/auth/login", methods=["POST"])
def auth_login():
    data = request.get_json() or {}
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    
    if not email or not password:
        return jsonify({"error": "Missing email or password"}), 400
        
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT id, name, email, password_hash FROM users WHERE email = ?", (email,))
    user = cursor.fetchone()
    
    if user and check_password_hash(user["password_hash"], password):
        session.permanent = True
        session["user_id"] = user["id"]
        session["user_name"] = user["name"]
        session["user_email"] = user["email"]
        
        return jsonify({
            "success": True,
            "message": "Logged in successfully",
            "user": {"name": user["name"], "email": user["email"]}
        })
    else:
        return jsonify({"error": "Invalid email or password"}), 401

@app.route("/api/auth/logout", methods=["POST", "GET"])
def auth_logout():
    session.clear()
    return jsonify({"success": True, "message": "Logged out successfully"})

@app.route("/api/auth/status", methods=["GET"])
def auth_status():
    if "user_id" in session:
        return jsonify({
            "authenticated": True,
            "user": {
                "name": session.get("user_name"),
                "email": session.get("user_email")
            }
        })
    return jsonify({"authenticated": False})

# ------------------ PROFILE & ANALYTICS ENDPOINTS ------------------

@app.route("/api/dashboard/summary", methods=["GET"])
def get_dashboard_summary():
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
        
    user_id = session["user_id"]
    db = get_db()
    cursor = db.cursor()
    
    # Get total resume uploads
    cursor.execute("SELECT COUNT(*) FROM resumes WHERE user_id = ?", (user_id,))
    resume_count = cursor.fetchone()[0]
    
    # Get total portfolios generated
    cursor.execute("SELECT COUNT(*) FROM portfolios WHERE user_id = ?", (user_id,))
    portfolio_count = cursor.fetchone()[0]
    
    # Get latest ATS score & average score
    cursor.execute("SELECT ats_score FROM resumes WHERE user_id = ? ORDER BY upload_time DESC", (user_id,))
    scores = [row[0] for row in cursor.fetchall()]
    
    avg_score = round(sum(scores) / len(scores)) if scores else 0
    latest_score = scores[0] if scores else 0
    
    return jsonify({
        "resume_uploads": resume_count,
        "portfolios_generated": portfolio_count,
        "latest_ats_score": latest_score,
        "average_ats_score": avg_score
    })

@app.route("/api/analytics/history", methods=["GET"])
def get_analytics_history():
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
        
    user_id = session["user_id"]
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute(
        "SELECT id, filename, upload_time, ats_score FROM resumes WHERE user_id = ? ORDER BY upload_time ASC",
        (user_id,)
    )
    history = []
    for r in cursor.fetchall():
        history.append({
            "id": r["id"],
            "filename": r["filename"],
            "upload_time": r["upload_time"],
            "ats_score": r["ats_score"]
        })
        
    return jsonify(history)

@app.route("/api/profile/details", methods=["GET", "POST"])
def profile_details():
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
        
    user_id = session["user_id"]
    db = get_db()
    cursor = db.cursor()
    
    if request.method == "POST":
        data = request.get_json() or {}
        name = data.get("name", "").strip()
        email = data.get("email", "").strip().lower()
        password = data.get("password", "")
        
        if not name or not email:
            return jsonify({"error": "Name and email are required"}), 400
            
        try:
            if password:
                password_hash = generate_password_hash(password)
                cursor.execute(
                    "UPDATE users SET name = ?, email = ?, password_hash = ? WHERE id = ?",
                    (name, email, password_hash, user_id)
                )
            else:
                cursor.execute(
                    "UPDATE users SET name = ?, email = ? WHERE id = ?",
                    (name, email, user_id)
                )
            db.commit()
            session["user_name"] = name
            session["user_email"] = email
            return jsonify({"success": True, "message": "Profile updated successfully"})
        except sqlite3.IntegrityError:
            return jsonify({"error": "An account with this email already exists"}), 409
            
    # GET method
    cursor.execute("SELECT name, email, created_at FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    
    # Get portfolio history
    cursor.execute(
        "SELECT p.id, p.template_id, p.deployed_slug, p.created_at, r.filename FROM portfolios p LEFT JOIN resumes r ON p.resume_id = r.id WHERE p.user_id = ? ORDER BY p.created_at DESC",
        (user_id,)
    )
    portfolios = []
    for p in cursor.fetchall():
        portfolios.append({
            "id": p["id"],
            "template_id": p["template_id"],
            "deployed_slug": p["deployed_slug"],
            "created_at": p["created_at"],
            "resume_name": p["filename"] or "N/A"
        })
        
    # Get resume history
    cursor.execute(
        "SELECT id, filename, upload_time, ats_score FROM resumes WHERE user_id = ? ORDER BY upload_time DESC",
        (user_id,)
    )
    resumes = []
    for r in cursor.fetchall():
        resumes.append({
            "id": r["id"],
            "filename": r["filename"],
            "upload_time": r["upload_time"],
            "ats_score": r["ats_score"]
        })
        
    return jsonify({
        "name": user["name"],
        "email": user["email"],
        "created_at": user["created_at"],
        "resumes": resumes,
        "portfolios": portfolios
    })

@app.route("/api/resume/details/<int:resume_id>", methods=["GET"])
def resume_details(resume_id):
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
        
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "SELECT filename, parsed_data FROM resumes WHERE id = ? AND user_id = ?",
        (resume_id, session["user_id"])
    )
    row = cursor.fetchone()
    if not row:
        return jsonify({"error": "Resume not found"}), 404
        
    return jsonify({
        "filename": row["filename"],
        "parsed_data": json.loads(row["parsed_data"])
    })

# ------------------ ATS ANALYZER ROUTE ------------------

@app.route("/api/ats/analyze", methods=["POST"])
def ats_analyze():
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
        
    file = request.files.get("resume")
    if not file:
        return jsonify({"error": "No file uploaded"}), 400
        
    text = extract_text(file)
    if text.startswith("Error"):
        return jsonify({"error": text}), 400
        
    try:
        # AI parsing, ATS scoring and SWOTS in one single Groq call
        analysis = ai_parse_and_analyze(text)
        ats_score = int(analysis.get("ats_score", 70))
        
        # Save to database
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            "INSERT INTO resumes (user_id, filename, parsed_data, ats_score) VALUES (?, ?, ?, ?)",
            (session["user_id"], file.filename, json.dumps(analysis), ats_score)
        )
        db.commit()
        resume_id = cursor.lastrowid
        
        return jsonify({
            "success": True,
            "resume_id": resume_id,
            "filename": file.filename,
            "analysis": analysis
        })
        
    except Exception as e:
        return jsonify({"error": f"AI Parsing failed: {str(e)}"}), 500

# ------------------ PORTFOLIO ROUTE & ACTIONS ------------------

@app.route("/api/portfolio/generate", methods=["POST"])
def portfolio_generate():
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
        
    data = request.get_json() or {}
    resume_id = data.get("resume_id")
    template_id = data.get("template_id", "minimalist")
    
    db = get_db()
    cursor = db.cursor()
    
    # Retrieve parsed data of this resume
    cursor.execute(
        "SELECT parsed_data FROM resumes WHERE id = ? AND user_id = ?",
        (resume_id, session["user_id"])
    )
    row = cursor.fetchone()
    if not row:
        return jsonify({"error": "Resume profile not found. Please upload a resume first."}), 404
        
    parsed_resume = json.loads(row["parsed_data"])
    
    # Generate HTML/CSS
    html, css = generate_portfolio_html_css(parsed_resume, template_id)
    
    # Insert new or update portfolio
    cursor.execute(
        "SELECT id, deployed_slug FROM portfolios WHERE user_id = ? AND resume_id = ? AND template_id = ?",
        (session["user_id"], resume_id, template_id)
    )
    existing = cursor.fetchone()
    
    if existing:
        portfolio_id = existing["id"]
        deployed_slug = existing["deployed_slug"]
        cursor.execute(
            "UPDATE portfolios SET html_content = ?, css_content = ? WHERE id = ?",
            (html, css, portfolio_id)
        )
    else:
        # Generate clean unique deployed slug
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        candidate_name = parsed_resume.get("candidate", {}).get("name", "candidate").lower().replace(" ", "-")
        # sanitize slug
        deployed_slug = f"{candidate_name}-{timestamp}"
        
        cursor.execute(
            "INSERT INTO portfolios (user_id, resume_id, template_id, html_content, css_content, deployed_slug) VALUES (?, ?, ?, ?, ?, ?)",
            (session["user_id"], resume_id, template_id, html, css, deployed_slug)
        )
        db.commit()
        portfolio_id = cursor.lastrowid
        
    db.commit()
    
    return jsonify({
        "success": True,
        "portfolio_id": portfolio_id,
        "deployed_slug": deployed_slug,
        "preview_html": html
    })

@app.route("/api/portfolio/download/<int:portfolio_id>", methods=["GET"])
def portfolio_download(portfolio_id):
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
        
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "SELECT html_content, css_content FROM portfolios WHERE id = ? AND user_id = ?",
        (portfolio_id, session["user_id"])
    )
    row = cursor.fetchone()
    if not row:
        return "Portfolio not found", 404
        
    html = row["html_content"]
    css = row["css_content"]
    
    # Zip in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.writestr("portfolio.html", html)
        zip_file.writestr("portfolio.css", css)
        
    zip_buffer.seek(0)
    
    return send_file(
        zip_buffer,
        mimetype="application/zip",
        as_attachment=True,
        download_name="portfolio.zip"
    )

@app.route("/api/portfolio/deploy/<int:portfolio_id>", methods=["POST"])
def portfolio_deploy(portfolio_id):
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
        
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "SELECT deployed_slug FROM portfolios WHERE id = ? AND user_id = ?",
        (portfolio_id, session["user_id"])
    )
    row = cursor.fetchone()
    if not row:
        return jsonify({"error": "Portfolio not found"}), 404
        
    slug = row["deployed_slug"]
    live_url = f"{request.host_url}portfolio/{slug}"
    
    return jsonify({
        "success": True,
        "deployed_url": live_url
    })

# ------------------ DYNAMIC PORTFOLIO HOSTING ROUTES ------------------

@app.route("/portfolio/<slug>")
def host_portfolio(slug):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT html_content FROM portfolios WHERE deployed_slug = ?", (slug,))
    row = cursor.fetchone()
    if not row:
        return "Portfolio not found. Please verify the link.", 404
    return row["html_content"]

@app.route("/portfolio/<slug>/portfolio.css")
def host_portfolio_css(slug):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT css_content FROM portfolios WHERE deployed_slug = ?", (slug,))
    row = cursor.fetchone()
    if not row:
        return "Style sheet not found", 404
    return row["css_content"], 200, {"Content-Type": "text/css"}

# ------------------ STATIC FRONTEND ROUTING ------------------

@app.route("/")
def home():
    if "user_id" in session:
        return send_from_directory(FRONTEND_FOLDER, "dashboard.html")
    return send_from_directory(FRONTEND_FOLDER, "login.html")

@app.route("/login.html")
def login_page():
    if "user_id" in session:
        return send_from_directory(FRONTEND_FOLDER, "dashboard.html")
    return send_from_directory(FRONTEND_FOLDER, "login.html")

@app.route("/signup.html")
def signup_page():
    if "user_id" in session:
        return send_from_directory(FRONTEND_FOLDER, "dashboard.html")
    return send_from_directory(FRONTEND_FOLDER, "signup.html")

@app.route("/dashboard.html")
def dashboard_page():
    if "user_id" not in session:
        return send_from_directory(FRONTEND_FOLDER, "login.html")
    return send_from_directory(FRONTEND_FOLDER, "dashboard.html")

@app.route("/<path:path>")
def serve_static(path):
    return send_from_directory(FRONTEND_FOLDER, path)

# ------------------ RUN SERVER ------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)