import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import requests
from bs4 import BeautifulSoup
import json, re

BASE = 'https://arms.sse.saveetha.com'

# Student login
s = requests.Session()
s.headers.update({'User-Agent': 'Mozilla/5.0'})
r = s.get(BASE + '/')
soup = BeautifulSoup(r.text, 'html.parser')
payload = {
    '__VIEWSTATE': soup.find('input', {'name': '__VIEWSTATE'})['value'],
    '__VIEWSTATEGENERATOR': soup.find('input', {'name': '__VIEWSTATEGENERATOR'})['value'],
    '__EVENTVALIDATION': soup.find('input', {'name': '__EVENTVALIDATION'})['value'],
    'txtusername': '192411184', 'txtpassword': 'Katam@1533', 'btnlogin': 'Login',
}
s.post(BASE + '/', data=payload, allow_redirects=True)
print("Student login OK")

# Get the internal marks page and extract JS to find exact API calls
r2 = s.get(BASE + '/StudentPortal/InternalMarks.aspx')
# Find all script content
scripts = re.findall(r'<script[^>]*>(.*?)</script>', r2.text, re.DOTALL)
for sc in scripts:
    if 'Handler' in sc or 'ashx' in sc.lower() or 'mark' in sc.lower():
        print("=== SCRIPT WITH HANDLER/MARK ===")
        # Print lines containing key terms
        for line in sc.split('\n'):
            if any(k in line.lower() for k in ['handler', 'ashx', 'mark', 'ajax', 'getjson', 'post', 'get']):
                print(f"  {line.strip()[:200]}")

# Also try the StudentInternalMark endpoint directly
print("\n=== StudentInternalMark ===")
r3 = s.get(f'{BASE}/Handler/NoDue.ashx', params={'Page':'Noduedetails','Mode':'StudentInternalMark'})
print(f"Status: {r3.status_code}, len={len(r3.text)}")
if r3.text.strip():
    try:
        data = r3.json()
        print(json.dumps(data)[:1000])
    except:
        print(r3.text[:500])

# Try with additional params
for extra in [{'Id':0}, {'Id':'15220'}, {'Id':'192411184'}, {'CourseId':0}, {}]:
    resp = s.get(f'{BASE}/Handler/NoDue.ashx',
        params={'Page':'Noduedetails','Mode':'StudentInternalMark', **extra})
    text = resp.text.strip()
    if text and text not in ('{}', '[]', 'null'):
        print(f"  PARAMS {extra}: {text[:300]}")

# Try a POST to internal marks page to see what it does  
print("\n=== POST to InternalMarks page ===")
r4 = s.post(BASE + '/StudentPortal/InternalMarks.aspx', 
    data={'__EVENTTARGET':'', '__EVENTARGUMENT':'', 'CourseId':'28871'},
    headers={'X-Requested-With':'XMLHttpRequest'})
print(f"Status: {r4.status_code}, len={len(r4.text)}, url={r4.url}")

# Check the page source for the function that loads marks
print("\n=== JS Functions in InternalMarks page ===")
# Get all function definitions
funcs = re.findall(r'function\s+\w+[^}]{0,500}', r2.text)
for f in funcs[:10]:
    print(f"\n  {f[:300]}")
