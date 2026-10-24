#!/usr/bin/env python3
"""Offline CI log signal extraction. Hypotheses are not proof of a root cause."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any

RULES = [
  ('disk-space', 'environment', 92, r'\b(?:ENOSPC|no space left on device)\b', 'Runner disk exhausted.', 'Check available disk/inodes; remove safe build caches or increase runner capacity.'),
  ('memory', 'environment', 86, r'\b(?:out of memory|ENOMEM|JavaScript heap out of memory|oom-killer|killed process \d+)\b', 'Process likely exceeded memory resources.', 'Inspect runner memory limits and peak usage; reproduce with the same resource limits.'),
  ('missing-dependency', 'dependency', 90, r'\b(?:ModuleNotFoundError|No module named|Cannot find module|Module not found|ERR_MODULE_NOT_FOUND)\b', 'Dependency resolution failed.', 'Verify lockfile, package install step, module name and execution working directory.'),
  ('typescript', 'compiler', 91, r'\berror TS\d{4}:', 'TypeScript compile/type-check error.', 'Run the exact typecheck command locally and inspect the cited source location.'),
  ('build-compiler', 'compiler', 85, r'(?:^|\s)(?:fatal error:|error: cannot find symbol|SyntaxError:|error\[E\d{4}\])', 'Compile, parsing or language-level error.', 'Rerun the failing compile step with original toolchain version; inspect the first compiler error.'),
  ('test-assertion', 'test', 83, r'\b(?:AssertionError|FAILED\s+\S+::|expect\(.+\)\.to(?:Be|Equal)|Expected:|Assertion failed:)\b', 'Test expectation failed.', 'Re-run the single named test and compare actual versus expected behavior; avoid changing expectations without evidence.'),
  ('test-runner', 'test', 72, r'^(?:FAIL\s+\S+|={2,}\s*FAILURES\s*={2,}|Tests?:\s*\d+ failed)', 'Test runner reports failed tests.', 'Find the earliest concrete assertion/traceback above the summary and re-run the failing case.'),
  ('auth-secret', 'configuration', 86, r'\b(?:401 Unauthorized|403 Forbidden|Invalid credentials|authentication failed|missing (?:required )?environment variable|secret not found)\b', 'Authentication or missing configuration may block CI.', 'Verify which secret name/scope is required without printing its value; inspect runner permissions.'),
  ('network-transient', 'environment', 79, r'\b(?:ECONNRESET|ETIMEDOUT|EAI_AGAIN|Temporary failure in name resolution|connection reset by peer|429 Too Many Requests)\b', 'Network, DNS or rate-limit transient possible.', 'Inspect service status, retry count and network logs; determine whether failure reproduces before labeling flaky.'),
  ('permission', 'configuration', 76, r'\b(?:Permission denied|EACCES|Operation not permitted)\b', 'File or execution permission problem.', 'Inspect file ownership, execute bits, workspace permissions and runner identity.'),
  ('timeout', 'environment', 60, r'\b(?:TimeoutError|Timed out after|Test timeout of|Job exceeded maximum execution time)\b', 'A timeout occurred; cause unknown.', 'Capture timing, inspect hangs/deadlocks, then attempt deterministic reproduction.'),
  ('dependency-install', 'dependency', 78, r'\b(?:ERESOLVE|Unable to resolve dependency tree|Could not find a version that satisfies|ResolutionImpossible|npm ERR! code)\b', 'Package installation or dependency constraints failed.', 'Inspect package manager log and lockfile drift; avoid blind version upgrades.'),
  ('docker', 'environment', 73, r'\b(?:Cannot connect to the Docker daemon|docker: Error response from daemon|failed to solve:)\b', 'Container build/runtime failure.', 'Inspect Docker daemon, builder logs, base images and registry access.'),
]
COMPILED = [(key,cat,score,re.compile(expr,re.I),hyp,verify) for key,cat,score,expr,hyp,verify in RULES]

# Redact secrets before any evidence is stored, printed, or serialized.
REDACTIONS = [
    re.compile(r'(?i)(authorization\s*:\s*bearer\s+)\S+'),
    re.compile(r'(?i)((?:api[_-]?key|access[_-]?token|password|secret|client[_-]?secret)\s*[:=]\s*["\']?)\S+'),
    re.compile(r'\b(?:ghp_|gho_|ghu_|ghs_|ghr_)[A-Za-z0-9_]{20,}\b'),
    re.compile(r'\bgithub_pat_[A-Za-z0-9_]{20,}\b'),
    re.compile(r'\bsk-[A-Za-z0-9_-]{20,}\b'),
    re.compile(r'\bglpat-[A-Za-z0-9_-]{12,}\b'),
]


def redact(line: str) -> str:
    for idx,pattern in enumerate(REDACTIONS):
        line = pattern.sub((r'\1[REDACTED]' if idx<2 else '[REDACTED]'),line)
    return line


def inspect_log(text: str, max_evidence: int = 3, max_lines: int = 200000) -> dict[str, Any]:
    findings: dict[str, dict[str, Any]]={}
    original_line_count=0
    for line_no,line in enumerate(text.splitlines(),start=1):
        original_line_count=line_no
        if line_no>max_lines:
            break
        clean=redact(line.strip())[:320]
        for key,cat,score,pattern,hyp,verify in COMPILED:
            if not pattern.search(clean):continue
            if key not in findings:
                findings[key]={"rule":key,"category":cat,"confidence_hint":"high" if score>=85 else "moderate" if score>=75 else "low", "signal_score":score,"hypothesis":hyp,"safe_next_step":verify,"count":0,"evidence":[]}
            item=findings[key];item['count']+=1
            if len(item['evidence'])<max_evidence:
                item['evidence'].append({"line":line_no,"text":clean})
    ranked=sorted(findings.values(), key=lambda f:(-f['signal_score'],min(x['line'] for x in f['evidence'])))
    return {'metadata':{'total_lines':original_line_count,'inspected_lines':min(original_line_count,max_lines),'truncated':original_line_count>max_lines,'deterministic_signals_only':True},'findings':ranked,'summary':{'categories':sorted({f['category'] for f in ranked}),'signals':len(ranked)}}


def markdown(report: dict[str,Any], source: str) -> str:
    meta=report['metadata'];items=report['findings']
    lines=['# CI Log Triage','',f'Source: `{source}`','',f"Inspected {meta['inspected_lines']} line(s) — {len(items)} signal group(s).",'']
    if meta['truncated']:
        lines.append('**Caution:** Log exceeded the line limit; only the first section was checked.\n')
    if not items:
        lines.extend(['No supported signal patterns found. That does NOT prove CI passed.',''])
    for f in items:
        lines.extend([f"## {f['rule']} — {f['category']}",f"Evidence hits: {f['count']}. Confidence hint: {f['confidence_hint']} (pattern specificity only).",f"**Hypothesis:** {f['hypothesis']}",f"**Next verification:** {f['safe_next_step']}",'','Evidence (redacted):'])
        for e in f['evidence']:
            safe_text = e["text"].replace("`", r"\`")
            lines.append(f"- Line {e['line']}: `{safe_text}`")
        lines.append('')
    lines.append('This tool does not assert a root cause or execute code, tests, network access, or repairs.\n')
    return '\n'.join(lines)


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',default='-',help='UTF-8 text file; - for stdin')
    parser.add_argument('--format',choices=['markdown','json'],default='markdown')
    parser.add_argument('--out',type=Path,help='Save output to path (default stdout)')
    parser.add_argument('--max-evidence',type=int,default=3)
    parser.add_argument('--max-lines',type=int,default=200000)
    args=parser.parse_args(argv)
    if not 1<=args.max_evidence<=20 or not 1<=args.max_lines<=1000000:
        parser.error('max-evidence must be 1..20 and max-lines must be 1..1,000,000')
    try:
        if args.input=='-':
            content=sys.stdin.read(16_000_001)
        else:
            path=Path(args.input)
            if path.stat().st_size>16_000_000:
                raise ValueError('Log file exceeds 16MB safety limit; split the log first')
            content=path.read_text(encoding='utf-8',errors='replace')
        if len(content)>16_000_000:
            raise ValueError('Log exceeds 16MB safety limit; split the log first')
        result=inspect_log(content,max_evidence=args.max_evidence,max_lines=args.max_lines)
        output=json.dumps(result,ensure_ascii=False,indent=2)+'\n' if args.format=='json' else markdown(result,args.input)
        if args.out:
            args.out.parent.mkdir(parents=True,exist_ok=True)
            args.out.write_text(output,encoding='utf-8')
        else:
            sys.stdout.write(output)
        return 0
    except (ValueError,OSError) as exc:
        print(f'ERROR: {exc}',file=sys.stderr)
        return 1


if __name__=='__main__':
    sys.exit(main())
