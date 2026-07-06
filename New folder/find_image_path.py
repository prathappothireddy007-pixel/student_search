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

filename = 'dd611875-afb3-42d8-9462-49340f5415fc192411184.JPG'
paths = [
    f'UploadedFiles/StudentImage/{filename}',
    f'UploadedFiles/StudentImages/{filename}',
    f'UploadedFiles/Student/{filename}',
    f'UploadedFiles/Profile/{filename}',
    f'UploadedFiles/ProfilePicture/{filename}',
    f'UploadedFiles/Images/{filename}',
    f'UploadedFiles/Photo/{filename}',
    f'UploadedFiles/Photos/{filename}',
    f'UploadedFiles/{filename}',
    f'StudentImage/{filename}',
    f'StudentImages/{filename}',
    f'images/{filename}',
    f'UploadedFiles/StudentImage/StudentImage/{filename}',
    f'FacultyPortal/UploadedFiles/StudentImage/{filename}',
    f'StudentPortal/UploadedFiles/StudentImage/{filename}',
    f'StudentPortal/UploadedFiles/{filename}'
]

for p in paths:
    url = f'https://arms.sse.saveetha.com/{p}'
    resp = s.get(url)
    if resp.status_code == 200:
        print(f"FOUND!! url={url}, size={len(resp.content)}")
        break
    else:
        print(f"Failed: {p} -> {resp.status_code}")
