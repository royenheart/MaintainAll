import json, re, sys
from pathlib import Path
repo=Path(sys.argv[1]); text=(repo/'report.md').read_text() if (repo/'report.md').is_file() else ''
t=text.lower()
checks={
 'report': bool(text.strip()),
 'gpu_not_visible': bool(re.search(r'(/dev/nvidia|/dev/dri).{0,80}(不|不可见|没有|private|私有|absent|not)',t)) or bool(re.search(r'(私有|private).{0,40}/dev',t)),
 'network_unrestricted': bool(re.search(r'(网络|network).{0,80}(不限制|不受|outside|not.*(restrict|govern)|没有.*限制)',t)),
 'not_security_boundary': bool(re.search(r'(不是|not).{0,40}(安全边界|security boundary|vm|虚拟机)',t)) or bool(re.search(r'(共享|share).{0,40}(内核|kernel)',t)),
 'modes': all(x in t for x in ('read-only','workspace-write','danger-full-access')),
 'file_effects_only': bool(re.search(r'(文件效果|file.effect|文件.*策略|file.*policy)',t)),
 'no_false_passthrough': not bool(re.search(r'(gpu|nvidia).{0,40}(可直接使用|可用|passthrough|直通)',t)) or bool(re.search(r'(不|未|没有).{0,30}(可用|passthrough)',t)),
}
print(json.dumps({'score':sum(checks.values()),'max':len(checks),'checks':checks},ensure_ascii=False,indent=2))
