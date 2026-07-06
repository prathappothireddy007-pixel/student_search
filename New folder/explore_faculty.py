import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import requests
from bs4 import BeautifulSoup
import re, json

BASE = 'https://arms.sse.saveetha.com'
s = requests.Session()
s.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})

# Faculty Login
r = s.get(BASE + '/')
soup = BeautifulSoup(r.text, 'html.parser')
payload = {
    '__VIEWSTATE':          soup.find('input', {'name': '__VIEWSTATE'})['value'],
    '__VIEWSTATEGENERATOR': soup.find('input', {'name': '__VIEWSTATEGENERATOR'})['value'],
    '__EVENTVALIDATION':    soup.find('input', {'name': '__EVENTVALIDATION'})['value'],
    'txtusername':          'SSETSCS262',
    'txtpassword':          'kumbakonam123$',
    'btnlogin':             'Login',
}
s.post(BASE + '/', data=payload, allow_redirects=True)
print("Faculty login OK")

# Pages to scan for student APIs
pages = [
    '/FacultyPortal/Student360View.aspx',
    '/FacultyPortal/StudentAttendance.aspx',
    '/FacultyPortal/ViewResult.aspx',
    '/FacultyPortal/ViewResultNew.aspx',
    '/FacultyPortal/ResultAnalytics.aspx',
    '/FacultyPortal/Grade.aspx',
    '/FacultyPortal/Programstatistics.aspx',
]

for page in pages:
    r = s.get(BASE + page)
    handlers = re.findall(r'Handler/[^\s"\']+', r.text)
    print(f'\n=== {page} (status={r.status_code}) ===')
    seen = set()
    for h in handlers:
        if h not in seen:
            seen.add(h)
            print(f'  {h[:130]}')
