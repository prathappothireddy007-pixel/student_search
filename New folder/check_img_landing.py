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

# Load student home page
r2 = s.get('https://arms.sse.saveetha.com/StudentPortal/Landing.aspx')
soup2 = BeautifulSoup(r2.text, 'html.parser')
# Find all img tags
print("=== IMG tags ===")
for img in soup2.find_all('img'):
    print('  IMG src:', img.get('src'))

# Search page content for JPG urls
urls = re.findall(r'/[^\s"\'\>]+?\.jpg', r2.text, re.IGNORECASE)
print("=== JPG URLs ===")
for u in set(urls):
    print('  ', u)
