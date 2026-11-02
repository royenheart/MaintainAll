import json, re, sys
from pathlib import Path
repo=Path(sys.argv[1]).resolve(); case_id=sys.argv[3] if len(sys.argv)>3 else ''
truth=json.loads((Path(__file__).resolve().parents[1]/'truth'/(case_id+'.json')).read_text())
rows=truth['entrypoints']; checks={}
data={}
try:
 data=json.loads((repo/truth.get('report','report.json')).read_text()); entries=data.get('entrypoints') or []
 checks['report_json']=isinstance(data,dict)
except Exception:
 entries=[]; checks['report_json']=False
def norm(x): return str(x or '').replace('\\','/').lower()
def line_ok(entry, expected):
 return norm(expected) in norm(entry.get('evidence',''))
by={}
for e in entries:
 if isinstance(e,dict):
  by[norm(e.get('route'))]=e
  for alias in (e.get('aliases') or []): by[norm(alias)]=e
def find_row(r):
 for key in [r['route']]+(r.get('aliases') or []):
  if norm(key) in by: return by[norm(key)]
 for e in entries:
  if not isinstance(e, dict): continue
  route = norm(e.get('route'))
  for key in [r['route']]+(r.get('aliases') or []):
   if norm(key) and (norm(key) in route or route in norm(key)): return e
 return {}
checks['coverage']=all(bool(find_row(r)) for r in rows)
checked=0
for r in rows:
 e=find_row(r)
 checks['auth:'+r['route']]=e.get('hostAuth')==r['hostAuth']
 checks['evidence:'+r['route']]=line_ok(e,r['evidence'])
 checks['severity:'+r['route']]=e.get('severity')==r['severity'] or (r['severity']=='high' and e.get('severity')=='critical')
 chain=[norm(x) for x in (e.get('chain') or [])]
 if r['severity']=='high':
  checks['chain:'+r['route']]=all(norm(x) in chain for x in r['chain'])
 else:
  checks['chain:'+r['route']]=(not chain)
checks['not_verified']=isinstance(data.get('notVerified'),list) and bool(data.get('notVerified'))
unsupported=[e for e in entries if isinstance(e,dict) and e.get('hostAuth') in ('yes','n/a') and e.get('severity') in ('high','critical')]
checks['no_unsupported_high']=not unsupported
score=sum(checks.values())
print(json.dumps({'score':score,'max':len(checks),'checks':checks},ensure_ascii=False,indent=2)); sys.exit(0)
