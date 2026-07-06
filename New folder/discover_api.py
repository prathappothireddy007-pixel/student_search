import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import requests
from bs4 import BeautifulSoup
import re

BASE = 'https://arms.sse.saveetha.com'
s = requests.Session()
s.headers.update({'User-Agent': 'Mozilla/5.0'})

r = s.get(BASE + '/')
soup = BeautifulSoup(r.text, 'html.parser')
payload = {
    '__VIEWSTATE': soup.find('input', {'name': '__VIEWSTATE'})['value'],
    '__VIEWSTATEGENERATOR': soup.find('input', {'name': '__VIEWSTATEGENERATOR'})['value'],
    '__EVENTVALIDATION': soup.find('input', {'name': '__EVENTVALIDATION'})['value'],
    'txtusername': '192411184',
    'txtpassword': 'Katam@1533',
    'btnlogin': 'Login',
}
s.post(BASE + '/', data=payload, allow_redirects=True)

pages_to_check = [
    '/StudentPortal/AttendanceReport.aspx',
    '/StudentPortal/MyDetails.aspx',
    '/StudentPortal/Paymenthistory.aspx',
    '/StudentPortal/InternalMarks.aspx',
    '/StudentPortal/ViewAssigment.aspx',
]

for page in pages_to_check:
    r = s.get(BASE + page)
    pattern = r'Handler/Student\.ashx[^"\'\s]+'
    matches = re.findall(pattern, r.text)
    print(f'=== {page} ===')
    seen = set()
    for m in matches:
        if m not in seen:
            seen.add(m)
            print(f'  API: {m[:120]}')
    if not matches:
        # try generic handler
        pattern2 = r'Handler/[^"\'\s]+'
        matches2 = re.findall(pattern2, r.text)
        for m in set(matches2):
            print(f'  HANDLER: {m[:120]}')
    print()
