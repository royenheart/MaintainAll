import json,re,sys
from pathlib import Path
repo=Path(sys.argv[1]);text=(repo/'report.md').read_text() if (repo/'report.md').is_file() else ''
t=text.lower()
checks={
 'report':bool(text.strip()),
 'file':bool(re.search(r'scripts/postinstall\.mjs|postinstall',t)),
 'lifecycle':bool(re.search(r'(postinstall|安装时|install.?time|lifecycle)',t)),
 'remote_exec':bool(re.search(r'(curl|wget|https?://|remote|远程).{0,100}(exec|执行|sh|shell|pipe|管道)|(exec|执行|sh|shell).{0,100}(curl|wget|https?://|remote|远程)',t)),
 'severity':bool(re.search(r'(critical|high|严重|高危|critical)',t)),
 'fix':bool(re.search(r'(remove|删除|移除|vendor|锁定|lock|audit|审计|禁用|disable).{0,80}(postinstall|install|安装|script|脚本|dependency|依赖)',t)),
 'evidence':bool(re.search(r'(package\.json|scripts/postinstall\.mjs)',t)),
}
print(json.dumps({'score':sum(checks.values()),'max':len(checks),'checks':checks},ensure_ascii=False,indent=2))
