"""The source verifier parses data and rejects active or external content."""
import unittest
from skill_bench.verifier import inspect_svg

class VerifierTests(unittest.TestCase):
    def test_static_internal_paint_can_reopen(self):
        root, size = inspect_svg(b'<svg xmlns="http://www.w3.org/2000/svg" width="320" height="240"><rect fill="#00f" width="320" height="240"/></svg>')
        self.assertEqual(size, (320, 240))
    def test_active_external_and_unbounded_sources_are_rejected(self):
        for body in ('<script>bad()</script>', '<image href="file:///home/user/auth.json"/>', '<rect style="fill:url(https://example.com/x)"/>', '<style>@import "bad.css"</style>'):
            with self.subTest(body=body), self.assertRaises(ValueError):
                inspect_svg(('<svg width="320" height="240">' + body + '</svg>').encode())
        with self.assertRaises(ValueError):
            inspect_svg(b'<svg width="100000" height="100000"/>')
