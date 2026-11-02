from pathlib import Path
ref = Path(__file__).resolve().parents[1] / 'references' / 'plugin-instrumentation.md'
text = ref.read_text()
assert 'recordException' not in text
assert 'dsh.error.type' in text
print('dsh-observability privacy docs test: PASS')
