"""Verify documented synthetic fixture output without external services."""
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
cmd=[sys.executable,'scripts/triage_ci.py',*'--input examples/synthetic-ci.log --format json'.split()]
result=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,check=False)
if result.returncode!=0:
    raise SystemExit(f'CLI exit was {result.returncode} instead of 0: {result.stderr}')
obj=json.loads(result.stdout)
assert len(obj['findings'])==3, len(obj['findings'])
assert obj['metadata']['total_lines']==9, obj['metadata']
print('PASS: 3 CI signal categories in 9 synthetic lines (CLI exit 0)')
