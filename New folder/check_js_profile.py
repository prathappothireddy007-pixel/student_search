import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import requests
from bs4 import BeautifulSoup

s = requests.Session()
r = s.get('https://arms.sse.saveetha.com/')
soup = BeautifulSoup(r.text, 'html.parser')
payload = {
    '__VIEWSTATE': soup.find('input', {'name': '__VIEWSTATE'})['value'],
    '__VIEWSTATEGENERATOR': soup.find('input', {'name': '__VIEWSTATEGENERATOR'})['value'],
    '__EVENTVALIDATION': soup.find('input', {'name': '__EVENTVALIDATION'})['value'],
    'txtusername': '192411184', 'txtpassword': 'Katam@1533', 'btnlogin': 'Login'
}
s.post('https://arms.sse.saveetha.com/', data=payload)

r2 = s.get('https://arms.sse.saveetha.com/StudentPortal/Landing.aspx')

# Look for JavaScript functions containing ProfilePictureUrl
lines = r2.text.split('\n')
for i, line in enumerate(lines):
    if 'ProfilePictureUrl' in line or 'avatar' in line:
        print(f"Line {i}: {line.strip()[:200]}")
        # Print surrounding lines
        for j in range(max(0, i-5), min(len(lines), i+6)):
            print(f"  [{j}]: {lines[j].strip()[:150]}")
