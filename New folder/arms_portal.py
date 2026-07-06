import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import requests
from bs4 import BeautifulSoup
import json

BASE_URL = "https://arms.sse.saveetha.com"

# ─── Credentials ────────────────────────────────────────────────────────────
STUDENT_USER = "192411184"
STUDENT_PASS = "Katam@1533"

# ─── Session Setup ───────────────────────────────────────────────────────────
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": BASE_URL + "/"
})

def login():
    print("\n Logging in as student...")
    r = session.get(BASE_URL + "/")
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    payload = {
        "__VIEWSTATE":          soup.find("input", {"name": "__VIEWSTATE"})["value"],
        "__VIEWSTATEGENERATOR": soup.find("input", {"name": "__VIEWSTATEGENERATOR"})["value"],
        "__EVENTVALIDATION":    soup.find("input", {"name": "__EVENTVALIDATION"})["value"],
        "txtusername":          STUDENT_USER,
        "txtpassword":          STUDENT_PASS,
        "btnlogin":             "Login",
    }
    r2 = session.post(BASE_URL + "/", data=payload, allow_redirects=True)
    r2.raise_for_status()
    if "StudentPortal" in r2.url or "Landing" in r2.url:
        print(f"   [OK] Logged in! -> {r2.url}")
        return True
    print(f"   [FAIL] Could not log in. URL: {r2.url}")
    return False

def call_api(handler, page, mode, extra_params=None):
    """Call any portal handler API."""
    url = f"{BASE_URL}/Handler/{handler}.ashx"
    params = {"Page": page, "Mode": mode}
    if extra_params:
        params.update(extra_params)
    r = session.get(url, params=params)
    try:
        return r.json()
    except Exception:
        return {"raw": r.text[:800] if r.text else "(empty)"}

def sep(title):
    print(f"\n{'='*62}")
    print(f"  {title}")
    print('='*62)

# ─────────────────────────────────────────────────────────────────────────────
def show_results():
    sep("EXAM RESULTS")
    data = call_api("Student", "CourseEnroll", "GetResult")
    if "Table" in data:
        rows = data["Table"]
        passed = [r for r in rows if r.get("FinalResult") == "PASS"]
        failed = [r for r in rows if r.get("FinalResult") == "FAIL"]
        print(f"\n  Total : {len(rows)}   Passed : {len(passed)}   Failed : {len(failed)}\n")
        print(f"  {'#':<4} {'Course Name':<52} {'Code':<8} {'Grade':<7} {'Result':<6} {'Exam Date'}")
        print(f"  {'-'*4} {'-'*52} {'-'*8} {'-'*7} {'-'*6} {'-'*15}")
        for i, r in enumerate(rows, 1):
            icon = "PASS" if r["FinalResult"] == "PASS" else "FAIL"
            month = r.get("MonthYearValue", "")[:10] if r.get("MonthYearValue") else ""
            print(f"  {i:<4} {r['CourseName']:<52} {r.get('CourseCode',''):<8} {r.get('FinalGrade',''):<7} {icon:<6} {month}")
        if failed:
            print(f"\n  !! FAILED SUBJECTS !!")
            for r in failed:
                print(f"     - {r['CourseName']} [{r.get('CourseCode','')}]")
    else:
        print(json.dumps(data, indent=2))

def show_enrollment():
    sep("COURSE ENROLLMENT STATUS")
    data = call_api("Student", "CourseEnroll", "GetCompletedStatus")
    if "Table" in data and data["Table"]:
        row = data["Table"][0]
        print(f"\n  Reg Number          : {row.get('RegNumber','')}")
        print(f"  University Core     : {row.get('UniversityCoreCompleted',0)}/{row.get('UniversityCoreRequired',0)}")
        print(f"  Program Core        : {row.get('ProgramCoreCompleted',0)}/{row.get('ProgramCoreRequired',0)}")
        print(f"  University Elective : {row.get('UniversityElectiveCompleted',0)}/{row.get('UniversityElectiveRequired',0)}")
        print(f"  Program Elective    : {row.get('ProgramElectiveCompleted',0)}/{row.get('ProgramElectiveRequired',0)}")
    else:
        print(json.dumps(data, indent=2))

def show_attendance():
    sep("ATTENDANCE REPORT")
    data = call_api("Administration", "StudentAttendance", "ATTENDANCESTUPERSENT")
    if "Table" in data:
        rows = data["Table"]
        if rows:
            print(f"\n  {'Subject':<52} {'Pres':<6} {'Total':<6} {'%'}")
            print(f"  {'-'*52} {'-'*6} {'-'*6} {'-'*8}")
            for r in rows:
                total = r.get('Total', 0) or 1
                pres  = r.get('Present', r.get('Attended', 0))
                pct   = round((pres / total) * 100, 1)
                warn  = " <LOW>" if pct < 75 else ""
                subj  = r.get('SubjectName', r.get('CourseName', str(r)))
                print(f"  {subj:<52} {pres:<6} {total:<6} {pct}%{warn}")
        else:
            print("  No attendance data available.")
    else:
        # Try percentage summary
        data2 = call_api("Administration", "StudentAttendance", "ATTENDANCEPGMPERSENT", {"Id": "0"})
        print("  Attendance summary:")
        print(json.dumps(data2, indent=2))

def show_internal_marks():
    sep("INTERNAL MARKS")
    data = call_api("NoDue", "Noduedetails", "StudentInternalMark")
    if "Table" in data:
        rows = data["Table"]
        if rows:
            print(f"\n  {'Course':<52} {'Mark':<8} {'Max'}")
            print(f"  {'-'*52} {'-'*8} {'-'*8}")
            for r in rows:
                print(f"  {r.get('CourseName', r.get('Subject','')):<52} {r.get('Mark',''):<8} {r.get('MaxMark','')}")
        else:
            print("  No internal marks data.")
    else:
        print(json.dumps(data, indent=2))

def show_assignments():
    sep("ASSIGNMENTS")
    # Get active courses first
    courses = call_api("Assignment", "StudentPublishView", "StudentActiveCourse")
    if "Table" in courses and courses["Table"]:
        for c in courses["Table"]:
            cid = c.get('CourseId', c.get('Id', 0))
            cname = c.get('CourseName', c.get('Name', f'Course {cid}'))
            print(f"\n  [Course: {cname}]")
            upcoming = call_api("Assignment", "StudentPublishView", "StudentWiseUpcoming", {"CourseId": cid})
            today    = call_api("Assignment", "StudentPublishView", "StudentWiseToday",    {"CourseId": cid})
            done     = call_api("Assignment", "StudentPublishView", "StudentWiseCompleted",{"CourseId": cid})
            for label, d in [("Upcoming", upcoming), ("Today", today), ("Completed", done)]:
                if "Table" in d and d["Table"]:
                    print(f"    {label}:")
                    for a in d["Table"]:
                        print(f"      - {a.get('Title', a.get('AssignmentTitle', str(a)))}")
    else:
        print("  No active courses / assignments found.")
        print(json.dumps(courses, indent=2))

def show_financial():
    sep("FINANCIAL RECORD / PAYMENT HISTORY")
    data = call_api("Parents", "StudentProfile", "Paymentlist")
    if "Table" in data:
        rows = data["Table"]
        if rows:
            print(f"\n  {'Description':<40} {'Amount':<12} {'Date':<12} {'Status'}")
            print(f"  {'-'*40} {'-'*12} {'-'*12} {'-'*10}")
            for r in rows:
                print(f"  {str(r.get('Description','')):<40} Rs.{str(r.get('Amount','')):<9} {str(r.get('Date','')):<12} {r.get('Status','')}")
        else:
            print("  No payment records found.")
    else:
        print(json.dumps(data, indent=2))

def show_profile():
    sep("STUDENT PROFILE / MY DETAILS")
    data = call_api("Student", "StudentView", "GETALLRECORDREGNOLIBS")
    if "Table" in data and data["Table"]:
        for key, val in data["Table"][0].items():
            if val:
                print(f"  {key:<35}: {val}")
    else:
        # Try alternate
        data2 = call_api("Student", "StudentView", "GETAPPREGNO")
        print(json.dumps(data2, indent=2))

# ─── Main Menu ───────────────────────────────────────────────────────────────
MENU = """
  ============================================================
    ARMS PORTAL -- Student Dashboard  (192411184)
  ============================================================
   [1] Exam Results
   [2] Course Enrollment Status
   [3] Attendance Report
   [4] Internal Marks
   [5] Assignments
   [6] Payment / Financial Record
   [7] Student Profile
   [8] Fetch ALL data
   [0] Exit
  ============================================================"""

if __name__ == "__main__":
    if not login():
        sys.exit(1)

    while True:
        print(MENU)
        choice = input("  Enter choice: ").strip()
        if   choice == "1": show_results()
        elif choice == "2": show_enrollment()
        elif choice == "3": show_attendance()
        elif choice == "4": show_internal_marks()
        elif choice == "5": show_assignments()
        elif choice == "6": show_financial()
        elif choice == "7": show_profile()
        elif choice == "8":
            show_results(); show_enrollment(); show_attendance()
            show_internal_marks(); show_assignments()
            show_financial(); show_profile()
        elif choice == "0":
            print("\n  Goodbye!\n")
            break
        else:
            print("  Invalid choice.")
