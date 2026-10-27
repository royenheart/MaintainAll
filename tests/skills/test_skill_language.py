"""Keep repository-owned skill instructions and resources in English."""

from pathlib import Path
import json
import re
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
TEXT_TYPES = {'.md', '.py', '.json', '.yaml', '.yml', '.js', '.jsx', '.ts', '.tsx', '.html', '.svg', '.txt', '.css'}
NON_ENGLISH_SCRIPT = re.compile('[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\U00020000-\U0002fa1f]')


def language_violations(root):
    """Catch CJK text in authored resources, including escaped JSON strings."""
    errors = []
    for file in sorted(root.rglob('*')):
        if not file.is_file() or (file.suffix not in TEXT_TYPES and file.name not in {'LICENSE', 'NOTICE', 'COPYING'}):
            continue
        relative = file.relative_to(root)
        if any(part in {'__pycache__', '.venv', 'node_modules', '.git'} for part in relative.parts):
            continue
        # Historical decision records may quote the source language; they are evidence, not skill instructions.
        if "decisions" in relative.parts:
            continue
        text = file.read_text(encoding='utf-8')
        if file.suffix == '.json':
            text = json.dumps(json.loads(text), ensure_ascii=False)
        for number, line in enumerate(text.splitlines(), 1):
            if NON_ENGLISH_SCRIPT.search(line):
                errors.append(f'{file.relative_to(root)}:{number}: non-English CJK text')
    return errors


class SkillLanguageTests(unittest.TestCase):
    def test_repository_owned_skills_have_no_cjk_text(self):
        for root in (ROOT/'skills', ROOT/'.agents/skills'):
            with self.subTest(root=root):
                self.assertEqual(language_violations(root), [])

    def test_reference_and_template_text_are_checked(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'references').mkdir()
            (root/'references/example.md').write_text('# Example\n\u4e2d\u6587\n')
            (root/'example.svg').write_text('<svg><text>\u8863\u670d</text></svg>')
            (root/'LICENSE').write_text('\u4e2d\u6587')
            self.assertEqual(len(language_violations(root)), 3)

    def test_escaped_json_text_is_checked(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'example.json').write_text(json.dumps({'label':'\u4e2d\u6587'}))
            self.assertEqual(len(language_violations(root)), 1)

    def test_english_allows_math_and_typographic_symbols(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'SKILL.md').write_text('Use an estimate of 10 \u00b1 2. Explain the rule \u2192 effect.\n')
            self.assertEqual(language_violations(root), [])
