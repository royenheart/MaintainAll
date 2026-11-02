import json, re, sys
from pathlib import Path
repo = Path(sys.argv[1]).resolve(); text = (repo/'metrics.md').read_text() if (repo/'metrics.md').is_file() else ''
t = text.lower()
checks = {
 'report': bool(text.strip()),
 'total_350': bool(re.search(r'\b350\b', t)),
 'input_100': bool(re.search(r'\b100\b', t)),
 'output_50': bool(re.search(r'\b50\b', t)),
 'cache_200': bool(re.search(r'\b200\b', t)),
 'cache_hit': bool(re.search(r'0\.66|66\.7|2/3', t)),
 'tool_calls_2': bool(re.search(r'(tool calls?|工具调用).{0,20}\b2\b|\b2\b.{0,20}(tool calls?|工具调用)', t)),
 'tool_p50_100': bool(re.search(r'(p50|中位|median).{0,20}\b100\b|\b100\s*ms', t)),
 'reference_1': bool(re.search(r'(reference|参考).{0,30}\b1\b|\b1\b.{0,20}(reference|参考)', t)),
 'compaction_1': bool(re.search(r'(compaction|压缩).{0,20}\b1\b|\b1\b.{0,20}(compaction|压缩)', t)),
 'summary_100': bool(re.search(r'(summary|摘要).{0,20}\b100\b', t)),
 'shadowed_3': bool(re.search(r'(shadowed|shadow).{0,20}\b3\b', t)),
 'uncached_150': bool(re.search(r'(uncached|未缓存).{0,20}\b150\b', t)),
}
keys = list(checks); score = sum(checks.values())
print(json.dumps({'score': score, 'max': len(keys), 'checks': checks}, ensure_ascii=False, indent=2))
sys.exit(0)
