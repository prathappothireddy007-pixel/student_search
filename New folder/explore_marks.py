import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import requests
from bs4 import BeautifulSoup
import json

BASE = 'https://arms.sse.saveetha.com'
s = requests.Session()
s.headers.update({'User-Agent': 'Mozilla/5.0'})

r = s.get(BASE + '/')
soup = BeautifulSoup(r.text, 'html.parser')
payload = {
    '__VIEWSTATE': soup.find('input', {'name': '__VIEWSTATE'})['value'],
    '__VIEWSTATEGENERATOR': soup.find('input', {'name': '__VIEWSTATEGENERATOR'})['value'],
    '__EVENTVALIDATION': soup.find('input', {'name': '__EVENTVALIDATION'})['value'],
    'txtusername': 'SSETSCS262', 'txtpassword': 'kumbakonam123$', 'btnlogin': 'Login',
}
s.post(BASE + '/', data=payload, allow_redirects=True)

student_id   = '192411184'
student_int_id = '15220'

# Try all combinations with int id
print("=== Testing with numeric StudentId=15220 ===")
tests = [
    ('Controller', 'ViewMarks', 'MarkSplitbyId', {'Id': student_int_id}),
    ('Testmark', 'RevaluationStudent', 'StudTestMark', {'CourseId': student_int_id}),
    ('NoDue', 'Noduedetails', 'StudentInternalMark', {'Id': student_int_id}),
    ('Fees', 'StudentByCourseSection', 'STUDENTPGMFORGRADE', {'StudentId': student_int_id}),
    ('Administration', 'PRINCGETENROLLCOURSE', 'GETENROLLCOURSE', {'Id': student_int_id}),
    ('Administration', 'PRINCGETENROLLCOURSE', 'GETRESULT', {'Id': student_int_id}),
    ('Parents', 'StudentDetails', 'CourseCompleteStatus', {'StudentId': student_int_id}),
    ('Parents', 'StudentProfile', 'Paymentlist', {}),
    ('Parents', 'StudentDetails', 'Paymentlist', {'StudentId': student_int_id}),
    ('Datafile', 'PrincDatacenterDetailsStudent', 'DATACENTERDETAILSTU', {'Id': student_int_id}),
    ('Administration', 'PrincDashInstitute', 'StudentDetailsById', {'Id': student_int_id}),
    ('Administration', 'CourseDateByProgramStuDean', 'ATTENDANCESTUPERSENT', {'SId': student_int_id}),
]

for handler, page, mode, extra in tests:
    url = f'{BASE}/Handler/{handler}.ashx'
    params = {'Page': page, 'Mode': mode, **extra}
    try:
        r2 = s.get(url, params=params, timeout=10)
        text = r2.text.strip()
        if text:
            try:
                data = r2.json()
                if isinstance(data, list) and data:
                    print(f'\n{handler}/{page}/{mode}: LIST {len(data)} rows')
                    print(f'  Keys: {list(data[0].keys())}')
                    print(f'  Sample: {json.dumps(data[0])[:400]}')
                elif isinstance(data, dict):
                    for k, v in data.items():
                        if isinstance(v, list) and v:
                            print(f'\n{handler}/{page}/{mode}: Table "{k}" {len(v)} rows')
                            print(f'  Keys: {list(v[0].keys())}')
                            print(f'  Sample: {json.dumps(v[0])[:400]}')
                        elif v:
                            print(f'\n{handler}/{page}/{mode}: "{k}" = {str(v)[:100]}')
            except:
                print(f'\n{handler}/{page}/{mode}: RAW {text[:200]}')
        else:
            pass  # empty, skip
    except Exception as e:
        print(f'\n{handler}/{page}/{mode}: ERROR {e}')
