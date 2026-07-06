import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import subprocess, os

script = os.path.join(os.path.dirname(__file__), 'arms_portal.py')
proc = subprocess.run(
    ['python', script],
    input='8\n0\n',
    capture_output=True,
    text=True,
    encoding='utf-8',
    errors='replace',
    cwd=os.path.dirname(__file__)
)
print(proc.stdout)
if proc.stderr:
    print("STDERR:", proc.stderr[:500])
