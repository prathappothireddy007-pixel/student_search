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
import threading, time, json, hashlib

app = Flask(__name__)
CORS(app)

BASE          = "https://arms.sse.saveetha.com"
FACULTY_USER  = "SSETSCS262"
FACULTY_PASS  = "kumbakonam123$"

# ── Session ───────────────────────────────────────────────────────────────────
_fac_session  = None
_session_lock = threading.Lock()
_student_cache = {}          # reg_no -> {data, ts}
_list_cache    = {"data": None, "ts": 0}
CACHE_TTL      = 300         # 5 min

def get_fac_session():
    global _fac_session
    with _session_lock:
        if _fac_session is None:
            _fac_session = _login_faculty()
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
    s = get_fac_session()
    url = f"{BASE}/Handler/{handler}.ashx"
    params = {"Page": page, "Mode": mode}
    if extra: params.update(extra)
    try:
        r = s.get(url, params=params, timeout=15)
        if r.text.strip():
            data = r.json()
            return data
        return {}
    except Exception as e:
        if retry:
            global _fac_session
            with _session_lock:
                _fac_session = _login_faculty()
            return fapi(handler, page, mode, extra, False)
        return {}

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

def get_mark_breakdown(course_id, student_session=None):
    """Try to get 5-category mark breakdown for a course."""
    # Try with faculty session
    data = fapi("Testmark", "RevaluationStudent", "StudTestMark", {"CourseId": course_id})
    rows = _safe_list(data)
    if rows: return rows
    return []

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

@app.route("/api/student/<reg_no>/marks/<course_sno>")
def mark_breakdown(reg_no, course_sno):
    """Get 5-category mark breakdown for a specific course."""
    rows = get_mark_breakdown(course_sno)
    return jsonify({"marks": rows})

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
def search():
    q = request.args.get("q","").strip().upper()
    if len(q) < 2:
        return jsonify({"results": []})
    students = get_all_student_list()
    results  = []
    # Search by reg number prefix — fast
    for s in students:
        reg = str(s.get("RegId",""))
        if q in reg.upper():
            iid = str(s.get("StudentId",""))
            dec = decode_reg(reg)
            results.append({"reg_no": reg, "int_id": iid, "name": "", "decoded": dec})
            if len(results) >= 20: break
    # If query looks like a name (has letters), enrich with profile names
    if any(c.isalpha() for c in q) and len(results) < 5:
        import concurrent.futures
        def check_name(s):
            reg = str(s.get("RegId",""))
            iid = str(s.get("StudentId",""))
            prof = get_profile(iid)
            name = prof.get("FirstName","").strip().upper()
            if q in name:
                dec = decode_reg(reg)
                return {"reg_no": reg, "int_id": iid, "name": prof.get("FirstName","").strip(), "decoded": dec}
            return None
        # Check a sample of students for name match (limit to avoid timeout)
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            for r in ex.map(check_name, students[:500]):
                if r and len(results) < 20:
                    # avoid duplicates
                    if not any(x["reg_no"] == r["reg_no"] for x in results):
                        results.append(r)
    return jsonify({"results": results[:15]})

@app.route("/api/depts")
def depts():
    students = get_all_student_list()
    codes = sorted(set(str(s.get("RegId",""))[4:6] for s in students if len(str(s.get("RegId",""))) >= 6))
    return jsonify([{"code": c, "name": GROUP_MAP.get(c, f"Dept {c}")} for c in codes])

@app.route("/")
def home():
    """Serve index.html at the root URL."""
    try:
        return send_file("index.html")
    except Exception as e:
        return f"Could not find index.html. Error: {str(e)}", 404

# Pre-login only when running locally or directly
if __name__ == "__main__":
    print("[*] Connecting to ARMS...")
    try:
        get_fac_session()
        print("[OK] Server ready on http://localhost:5000")
    except Exception as e:
        print(f"[WARN] Pre-login failed: {e}")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
