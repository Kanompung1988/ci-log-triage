"""Self-contained tests. Run python -m unittest discover -s tests -v"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from triage_ci import inspect_log,redact,markdown


class Tests(unittest.TestCase):
    def test_pytest_failure(self):
        r=inspect_log('FAILED tests/test_api.py::test_bad - AssertionError: nope')
        self.assertIn('test-assertion',[i['rule'] for i in r['findings']])
    def test_typescript(self):
        self.assertIn('typescript',[f['rule'] for f in inspect_log('src/main.ts:4:2 - error TS2345: x')['findings']])
    def test_missing_dep(self):
        self.assertIn('missing-dependency',[f['rule'] for f in inspect_log("ModuleNotFoundError: No module named 'x'")['findings']])
    def test_network(self):
        self.assertIn('network-transient',[f['rule'] for f in inspect_log('Error: ECONNRESET') ['findings']])
    def test_permission(self):
        self.assertIn('permission',[f['rule'] for f in inspect_log('Permission denied')['findings']])
    def test_no_signals(self):
        self.assertFalse(inspect_log('All 10 tests passed')['findings'])
    def test_line_evidence(self):
        out=inspect_log('noise\nnoise\nerror TS1234: bad')
        self.assertEqual(out['findings'][0]['evidence'][0]['line'],3)
    def test_dedupe_count(self):
        out=inspect_log('AssertionError: a\nAssertionError: b',max_evidence=1)
        self.assertEqual(out['findings'][0]['count'],2)
        self.assertEqual(len(out['findings'][0]['evidence']),1)
    def test_truncate(self):
        self.assertTrue(inspect_log('a\nb\nc',max_lines=2)['metadata']['truncated'])
    def test_secret_redaction(self):
        line='Authorization: Bearer abcdef1234567890\npassword=SuperSecret123\nghp_'+'x'*24
        clean=redact(line)
        self.assertNotIn('abcdef1234567890',clean)
        self.assertNotIn('SuperSecret123',clean)
        self.assertNotIn('ghp_',clean)
    def test_cli_json(self):
        with tempfile.TemporaryDirectory() as p:
            f=Path(p)/'ci.log';f.write_text('fatal error: no file',encoding='utf-8')
            proc=subprocess.run([sys.executable,str(ROOT/'scripts/triage_ci.py'),'--input',str(f),'--format','json'],capture_output=True,text=True)
            self.assertEqual(proc.returncode,0,proc.stderr)
            self.assertEqual(json.loads(proc.stdout)['summary']['signals'],1)


if __name__=='__main__':unittest.main()
