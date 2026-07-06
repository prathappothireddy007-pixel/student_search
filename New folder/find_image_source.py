import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import requests
from bs4 import BeautifulSoup
import re

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

# Load profile / student pages to check picture paths
pages = [
    'StudentPortal/Landing.aspx',
    'StudentPortal/StudentProfile.aspx',
    'StudentPortal/Profile.aspx',
    'StudentPortal/InternalMarks.aspx',
]

for p in pages:
    url = f'https://arms.sse.saveetha.com/{p}'
    resp = s.get(url)
    print(f"=== Page {p} status={resp.status_code} ===")
    if resp.status_code == 200:
        # Search for any img tags, scripts, CSS background-image
        soup_p = BeautifulSoup(resp.text, 'html.parser')
        for img in soup_p.find_all('img'):
            print('  IMG src:', img.get('src'))
        
        # Search for ProfilePictureUrl or any references to the image filename
        matches = re.findall(r'[^\s"\'\>]+?ProfilePictureUrl[^\s"\'\<]+', resp.text)
        if matches:
            print('  Matches ProfilePictureUrl:', matches)
        
        # Search for file extensions in page
        exts = re.findall(r'/[^\s"\'\>]+?\.(?:jpg|png|gif|jpeg)', resp.text, re.I)
        if exts:
            print('  Extensions found:', list(set(exts))[:10])
