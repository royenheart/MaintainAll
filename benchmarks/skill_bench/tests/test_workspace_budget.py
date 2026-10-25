"""Declared large-reference budgets stay bounded and do not widen other trials."""
import unittest
from skill_bench.backends.local_codex import limits


class WorkspaceBudget(unittest.TestCase):
    def test_explicit_sixty_four_mib_reference_workspace_is_supported(self):
        spec = {'limits': {'turn_seconds': 600, 'max_file_bytes': 8 * 1024 * 1024,
                           'max_workspace_bytes': 64 * 1024 * 1024}}
        try:
            actual = limits(spec)
        except ValueError as error:
            self.fail('Declared original-image annotation workspace is unsupported: ' + str(error))
        self.assertEqual(actual['workspace_bytes'], 64 * 1024 * 1024)
        spec['limits']['max_workspace_bytes'] = 32 * 1024 * 1024
        self.assertEqual(limits(spec)['workspace_bytes'], 32 * 1024 * 1024)
        spec['limits']['max_workspace_bytes'] = 64 * 1024 * 1024 + 1
        with self.assertRaises(ValueError):
            limits(spec)


if __name__ == '__main__':
    unittest.main()
