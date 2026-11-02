import json,re,sys
from pathlib import Path
repo=Path(sys.argv[1]); text=(repo/'report.md').read_text() if (repo/'report.md').is_file() else ''
t=text.lower()
checks={
 'report': bool(text.strip()),
 'image_pin': bool(re.search(r'action\.yml',t)) and bool(re.search(r'(docker://|ghcr\.io).{0,80}(tag|标签|digest|摘要|未固定|mutable|可变)',t)),
 'docker_pin': bool(re.search(r'(node:24|base image|基础镜像|apt-get|npm install -g).{0,100}(未固定|unpinned|tag|digest|摘要|lock)',t)),
 'secrets': bool(re.search(r'(\.secrets\.local\.json|langfuse_secret|github_token|deepseek_api_key|token).{0,100}(secret|密钥|凭据|env|环境变量)',t)),
 'auth': bool(re.search(r'(author_association|owner|member|collaborator).{0,100}(command|命令|授权|allow|允许)',t)) or bool(re.search(r'(comment|评论).{0,80}(owner|member|collaborator|association)',t)),
 'evidence': bool(re.search(r'(action\.yml|dockerfile|src/|container/|package\.json)',t)),
 'severity': bool(re.search(r'(high|medium|low|严重|高|中|低|p[0-3])',t)),
 'no_false_digest': not bool(re.search(r'(digest|摘要).{0,40}(已固定|pinned|verified)',t)) or bool(re.search(r'(not|未|没有).{0,30}(digest|摘要)',t)),
}
print(json.dumps({'score':sum(checks.values()),'max':len(checks),'checks':checks},ensure_ascii=False,indent=2))
