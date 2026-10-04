"""Geometry and replay contracts for the portable creative scene generator."""

from collections import Counter
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "skills/art-creation/methods/scene-3d/scripts/scene.py"
SPEC = importlib.util.spec_from_file_location("creative_scene", SCRIPT)
SCENE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SCENE)


class SceneTests(unittest.TestCase):
    def test_each_form_has_closed_consistently_oriented_edges(self):
        for shape in SCENE.PROFILES:
            with self.subTest(shape=shape):
                vertices, faces = SCENE.build_mesh(shape, 1, 2, 16)
                edges = Counter()
                directed = Counter()
                for face in faces:
                    for a, b in zip(face, face[1:] + face[:1]):
                        self.assertTrue(0 <= a < len(vertices) and 0 <= b < len(vertices))
                        edges[tuple(sorted((a, b)))] += 1
                        directed[(a, b)] += 1
                self.assertTrue(all(count == 2 for count in edges.values()))
                self.assertTrue(all(directed[(a, b)] == directed[(b, a)] for a, b in edges))
                self.assertAlmostEqual(max(vertex[1] for vertex in vertices), 2)
                self.assertAlmostEqual(max(vertex[0] for vertex in vertices) - min(vertex[0] for vertex in vertices), 1)

    def test_camera_does_not_change_model_and_replay_matches(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = [Path(temporary) / name for name in ["first", "replay", "other-view"]]
            for path, yaw in zip(paths, [30, 30, 100]):
                subprocess.run([sys.executable, str(SCRIPT), "--output", str(path), "--yaw", str(yaw)],
                               check=True, capture_output=True)
            for name in ["model.obj", "preview.svg", "recipe.json"]:
                self.assertEqual((paths[0] / name).read_bytes(), (paths[1] / name).read_bytes())
            self.assertEqual((paths[0] / "model.obj").read_bytes(), (paths[2] / "model.obj").read_bytes())
            self.assertNotEqual((paths[0] / "preview.svg").read_bytes(), (paths[2] / "preview.svg").read_bytes())
            recipe = json.loads((paths[2] / "recipe.json").read_text())
            self.assertEqual(recipe["yawDegrees"], 100)

    def test_invalid_input_and_existing_iteration_are_rejected(self):
        with self.assertRaises(ValueError):
            SCENE.build_mesh("vase", float("nan"), 2, 16)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            original = output / "model.obj"
            original.write_text("accepted baseline")
            result = subprocess.run([sys.executable, str(SCRIPT), "--output", temporary], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(original.read_text(), "accepted baseline")
            self.assertFalse((output / "preview.svg").exists())


if __name__ == "__main__":
    unittest.main()
