import json,re,sys
from pathlib import Path
repo=Path(sys.argv[1]);text=(repo/'report.md').read_text() if (repo/'report.md').is_file() else ''
t=text.lower()
checks={
 'report':bool(text.strip()),
 'image':bool(re.search(r'(action\.yml|docker://|ghcr\.io).{0,100}(tag|digest|固定|pin|可变|mutable)',t)),
 'image_docker':bool(re.search(r'(dockerfile|node:24|基础镜像|base image|apt).{0,100}(digest|pin|固定|unpinned|tag|lock)',t)),
 'install_rce':bool(re.search(r'(postinstall|install-script|安装时|lifecycle).{0,140}(curl|wget|https?://|remote|远程|exec|执行|sh)',t)),
 'secrets':bool(re.search(r'(\.secrets\.local\.json|github_token|deepseek_api_key|langfuse_secret|secret).{0,120}(env|环境|file|文件|token|key|凭据)',t)),
 'auth':bool(re.search(r'(author_association|owner|member|collaborator).{0,120}(command|评论|comment|授权|allow|允许)',t)) or bool(re.search(r'(comment|评论).{0,100}(owner|member|collaborator|association)',t)),
 'evidence':bool(re.search(r'(action\.yml|dockerfile|package\.json|src/|container/|scripts/)',t)),
 'severity':bool(re.search(r'(critical|high|medium|low|严重|高|中|低|p[0-3])',t)),
}
print(json.dumps({'score':sum(checks.values()),'max':len(checks),'checks':checks},ensure_ascii=False,indent=2))
