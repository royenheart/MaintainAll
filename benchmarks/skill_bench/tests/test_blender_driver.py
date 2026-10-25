"""Bounded data validation and real native Blender reopening evidence."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zlib

from skill_bench import blender_driver as driver


def png(width=2, height=2, pixel=b"\x12\x34\x56\xff", ancillary=b""):
    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
    rows = (b"\x00" + pixel * width) * height
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + (chunk(b"tEXt", ancillary) if ancillary else b"") + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


class BlenderDriverDataTests(unittest.TestCase):
    def test_help_is_available_without_importing_blender(self):
        process = subprocess.run([sys.executable, "-I", driver.__file__, "--help"], capture_output=True, text=True)
        self.assertEqual(process.returncode, 0, process.stderr)
        for text in ("--source", "--fixture", "--render-timeout", "generated Python is never loaded", "network-disabled"):
            self.assertIn(text, " ".join(process.stdout.split()))

    def test_resource_limits_and_cli_contract_are_enforced(self):
        for extra in (["--width", "1281"], ["--height", "63"], ["--max-objects", "513"],
                      ["--max-vertices", "200001"], ["--render-timeout", "21"]):
            with self.subTest(extra=extra), self.assertRaises(driver.EvidenceError):
                driver.arguments(["--source", "a.blend", "--output", "new", *extra])
        with self.assertRaises(driver.EvidenceError):
            driver.arguments(["--source", "a.blend"])
        with self.assertRaises(driver.EvidenceError):
            driver.arguments(["--fixture", "a.blend", "--output", "new"])

    def test_native_header_byte_limit_and_symlinks(self):
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / "source.blend"
            for payload in (b"", b"BLENDER", b"\x1f\x8bcompressed", b"BLENDERxv450rest"):
                source.write_bytes(payload)
                with self.subTest(payload=payload), self.assertRaises(driver.EvidenceError):
                    driver.native_source(source)
            source.write_bytes(b"BLENDER-v450rest")
            self.assertEqual(driver.native_source(source), source.read_bytes())
            alias = Path(root) / "linked.blend"
            alias.symlink_to(source)
            with self.assertRaises(driver.EvidenceError):
                driver.native_source(alias)
            with self.assertRaises(driver.EvidenceError):
                driver.bounded_file(source, 8)

    def test_raster_comparison_uses_decoded_pixels(self):
        with tempfile.TemporaryDirectory() as root:
            source, other, changed = (Path(root) / name for name in ("a.png", "b.png", "c.png"))
            source.write_bytes(png())
            other.write_bytes(png(ancillary=b"Comment\x00metadata differs"))
            changed.write_bytes(png(pixel=b"\x13\x34\x56\xff"))
            first, second, third = (driver.raster_record(path, (2, 2)) for path in (source, other, changed))
            self.assertNotEqual(first["sha256"], second["sha256"])
            self.assertEqual(first["pixel_sha256"], second["pixel_sha256"])
            self.assertNotEqual(first["pixel_sha256"], third["pixel_sha256"])

    def test_malformed_and_oversized_rasters_are_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "bad.png"
            for data in (b"not png", png()[:-1], png() + b"tail", png(width=1281), png(height=1281)):
                path.write_bytes(data)
                with self.subTest(length=len(data)), self.assertRaises(driver.EvidenceError):
                    driver.raster_record(path)
            path.write_bytes(png())
            with self.assertRaises(driver.EvidenceError):
                driver.raster_record(path, (3, 2))

    def test_nonfinite_and_unbounded_coordinates_are_rejected(self):
        for coordinate in (float("inf"), float("nan"), 10_000_001):
            with self.subTest(coordinate=coordinate), self.assertRaises(driver.EvidenceError):
                driver.finite([coordinate])

    def test_render_eligibility_unions_paths_and_respects_hidden_ancestors(self):
        def mesh(name, *, hidden=False):
            return SimpleNamespace(name=name, type="MESH", hide_render=hidden, data=SimpleNamespace(vertices=[1]))
        def layer(objects=(), children=(), *, excluded=False, hidden=False):
            return SimpleNamespace(exclude=excluded, collection=SimpleNamespace(hide_render=hidden, objects=objects), children=children)
        shared, hidden, excluded, object_hidden = (mesh(name) for name in ("shared", "hidden", "excluded", "object-hidden"))
        object_hidden.hide_render = True
        tree = layer(children=[layer([shared]), layer(children=[layer([hidden, shared])], hidden=True),
                               layer(children=[layer([excluded, shared])], excluded=True), layer([object_hidden])])
        bpy = SimpleNamespace(context=SimpleNamespace(view_layer=SimpleNamespace(layer_collection=tree)))
        self.assertEqual([obj.name for obj in driver.render_eligible_meshes(bpy)], ["shared"])

    def test_capture_timeout_kills_worker_without_detaching_from_sandbox(self):
        arguments = driver.arguments(["--source", "source.blend", "--output", "new"])
        process = SimpleNamespace(returncode=0)
        calls = []
        def communicate(timeout=None):
            calls.append(timeout)
            if timeout is not None:
                raise subprocess.TimeoutExpired("blender", timeout)
            return b"", b""
        process.communicate = communicate
        process.kill = lambda: calls.append("killed")
        with patch.dict(sys.modules, {"bpy": SimpleNamespace(app=SimpleNamespace(binary_path="blender"))}), patch.object(driver.subprocess, "Popen", return_value=process) as launch:
            with self.assertRaisesRegex(driver.EvidenceError, "hard lifetime"):
                driver.capture(arguments, Path("source.blend"), "front", Path("config.json"))
            self.assertEqual(calls, [20, "killed", None])
            self.assertNotIn("start_new_session", launch.call_args.kwargs)


def installed_blender():
    explicit = os.environ.get("SKILL_BENCH_BLENDER")
    if explicit:
        return explicit if Path(explicit).is_file() else None
    discovered = shutil.which("blender")
    if discovered:
        return discovered
    personal = Path.home() / "bin/blender"
    return str(personal) if personal.is_file() else None


@unittest.skipUnless(installed_blender(), "Optional real Blender runtime is unavailable")
class BlenderDriverNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="skill-bench-native-blender-")
        cls.root = Path(cls.temporary.name)
        cls.binary = installed_blender()
        cls.source = cls.root / "fixture.blend"
        result = cls.invoke(["--fixture", str(cls.source)])
        if result.returncode:
            raise RuntimeError(result.stderr + result.stdout)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    @classmethod
    def invoke(cls, arguments, timeout=100):
        return subprocess.run([cls.binary, "--background", "--factory-startup", "--disable-autoexec", "--threads", "2",
                               "--python-exit-code", "1", "--python", driver.__file__, "--", *arguments],
                              capture_output=True, text=True, timeout=timeout)

    def mutated_fixture(self, label, code):
        source = self.root / (label + ".blend")
        script = self.root / (label + ".py")
        script.write_text("import bpy\n" + "bpy.ops.wm.open_mainfile(filepath=" + repr(str(self.source)) + ", use_scripts=False)\n"
                          + code + "\nbpy.ops.wm.save_as_mainfile(filepath=" + repr(str(source)) + ", compress=False)\n", encoding="utf-8")
        process = subprocess.run([self.binary, "--background", "--factory-startup", "--disable-autoexec", "--threads", "2",
                                  "--python-exit-code", "1", "--python", str(script)], capture_output=True, text=True, timeout=15)
        self.assertEqual(process.returncode, 0, process.stderr)
        return source

    def test_actual_native_reopen_edit_and_raster_evidence(self):
        destination = self.root / "verified"
        original = hashlib.sha256(self.source.read_bytes()).hexdigest()
        # An adjacent generated script must not influence trusted source replay.
        sentinel = self.root / "generated-program-executed"
        (self.root / "source.py").write_text("open(" + repr(str(sentinel)) + ", 'w').write('bad')", encoding="utf-8")
        result = self.invoke(["--source", str(self.source), "--output", str(destination)])
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        evidence = json.loads((destination / "evidence.json").read_text())
        self.assertTrue(evidence["source_reopen_verified"])
        self.assertTrue(evidence["source_editability_verified"])
        self.assertEqual(evidence["source_sha256"], original)
        self.assertEqual(evidence["quality_status"], "unassessed")
        self.assertFalse(evidence["generated_code_executed"])
        self.assertFalse(evidence["inventory"]["geometry_counts_are_quality_scores"])
        self.assertIn("not procedural-rule validity", evidence["edit_scope"])
        self.assertTrue(evidence["modified_native"]["independent_reopen_verified"])
        self.assertTrue(evidence["modified_native"]["edit_observed"])
        self.assertTrue(evidence["modified_native"]["raster_pixels_changed"])
        self.assertNotEqual(evidence["rendered"]["source"]["pixel_sha256"], evidence["rendered"]["edited"]["pixel_sha256"])
        self.assertFalse(sentinel.exists())
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(), original)
        for label in ("front", "side", "camera", "edited-front"):
            record = evidence["rendered"][label]
            self.assertEqual((record["width"], record["height"]), (640, 480))
            self.assertEqual(record["engine"], "BLENDER_WORKBENCH")
            self.assertTrue(record["software_render_observed"])
            self.assertFalse(record["native_shaders_preserved"])
            self.assertLess(record["elapsed_seconds"], 20)
            self.assertEqual(record["sha256"], driver.raster_record(destination / record["path"])["sha256"])
        second = self.invoke(["--source", str(self.source), "--output", str(destination)])
        self.assertNotEqual(second.returncode, 0)

    def test_embedded_autoexecution_is_disabled(self):
        sentinel = self.root / "embedded-module-executed"
        source = self.mutated_fixture("embedded", "text = bpy.data.texts.new('evil.py')\ntext.use_module = True\ntext.write(" + repr("open(" + repr(str(sentinel)) + ", 'w').write('executed')") + ")")
        destination = self.root / "embedded-check"
        process = self.invoke(["--source", str(source), "--output", str(destination), "--width", "128", "--height", "128"])
        self.assertEqual(process.returncode, 0, process.stderr + process.stdout)
        evidence = json.loads((destination / "evidence.json").read_text())
        self.assertFalse(sentinel.exists())
        self.assertTrue(evidence["inventory"]["safety"]["autoexec_disabled"])
        self.assertEqual(evidence["inventory"]["safety"]["embedded_texts"], [{"name": "evil.py", "module": True, "executed": False}])

    def test_hidden_and_excluded_collections_do_not_set_bounds_or_edit_target(self):
        source = self.mutated_fixture("collection-visibility", """
visible = bpy.data.objects['Trusted fixture mesh']
visible.name = 'Visible multi-collection mesh'
visible.scale = (1, 1, 1)
hidden_parent = bpy.data.collections.new('Hidden parent')
bpy.context.scene.collection.children.link(hidden_parent)
hidden_parent.hide_render = True
hidden_child = bpy.data.collections.new('Hidden child')
hidden_parent.children.link(hidden_child)
hidden_child.objects.link(visible)
excluded_parent = bpy.data.collections.new('Excluded parent')
bpy.context.scene.collection.children.link(excluded_parent)
excluded_child = bpy.data.collections.new('Excluded child')
excluded_parent.children.link(excluded_child)
excluded_child.objects.link(visible)
for name, collection, scale, position in [('Largest hidden mesh', hidden_child, 50, 100), ('Largest excluded mesh', excluded_child, 70, -100)]:
    obj = bpy.data.objects.new(name, visible.data.copy())
    collection.objects.link(obj)
    obj.scale = (scale, scale, scale)
    obj.location.x = position
bpy.context.view_layer.update()
bpy.context.view_layer.layer_collection.children['Excluded parent'].exclude = True
bpy.context.view_layer.update()
""")
        original = hashlib.sha256(source.read_bytes()).hexdigest()
        destination = self.root / "collection-visibility-check"
        process = self.invoke(["--source", str(source), "--output", str(destination), "--width", "128", "--height", "128"])
        self.assertEqual(process.returncode, 0, process.stderr + process.stdout)
        evidence = json.loads((destination / "evidence.json").read_text())
        view = json.loads((destination / "trusted-view.json").read_text())
        objects = {obj['name']: obj for obj in evidence['inventory']['objects']}
        self.assertTrue(objects['Visible multi-collection mesh']['render_eligible_mesh'])
        self.assertFalse(objects['Largest hidden mesh']['render_eligible_mesh'])
        self.assertFalse(objects['Largest excluded mesh']['render_eligible_mesh'])
        self.assertEqual(evidence['edit']['object'], 'Visible multi-collection mesh')
        self.assertEqual(view['span'], 2)
        self.assertEqual(view['center'], [0, 0, 0])
        self.assertEqual(evidence['inventory']['view_layer'], 'ViewLayer')
        self.assertTrue(evidence['source_editability_verified'])
        self.assertTrue(evidence['modified_native']['edit_observed'])
        self.assertTrue(evidence['modified_native']['raster_pixels_changed'])
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), original)

    def test_native_drivers_are_rejected(self):
        source = self.mutated_fixture("driver", "obj = bpy.data.objects['Trusted fixture mesh']\nobj.driver_add('location', 0).driver.expression = '1 + 2'")
        destination = self.root / "driver-check"
        process = self.invoke(["--source", str(source), "--output", str(destination)])
        self.assertNotEqual(process.returncode, 0)
        evidence = json.loads((destination / "evidence.json").read_text())
        self.assertEqual(evidence["status"], "failed")
        self.assertIn("drivers are unsupported", evidence["error"])
        self.assertFalse(evidence["source_editability_verified"])

    def test_external_or_missing_textures_are_rejected(self):
        source = self.mutated_fixture("missing-texture", "image = bpy.data.images.new('Missing external texture', width=8, height=8)\nimage.use_fake_user = True\nimage.source = 'FILE'\nimage.filepath = '/missing/unavailable.png'")
        destination = self.root / "missing-texture-check"
        process = self.invoke(["--source", str(source), "--output", str(destination)])
        self.assertNotEqual(process.returncode, 0)
        evidence = json.loads((destination / "evidence.json").read_text())
        self.assertIn("External or missing texture", evidence["error"])
        self.assertFalse(evidence["source_reopen_verified"])

    def test_real_native_geometry_limits_are_enforced(self):
        destination = self.root / "vertex-limit-check"
        process = self.invoke(["--source", str(self.source), "--output", str(destination), "--max-vertices", "4"])
        self.assertNotEqual(process.returncode, 0)
        evidence = json.loads((destination / "evidence.json").read_text())
        self.assertIn("Raw mesh vertex ceiling", evidence["error"])

    def test_malformed_native_body_cannot_claim_a_reopen(self):
        source = self.root / "malformed.blend"
        source.write_bytes(b"BLENDER-v450not a scene")
        destination = self.root / "malformed-check"
        process = self.invoke(["--source", str(source), "--output", str(destination)])
        self.assertNotEqual(process.returncode, 0)
        evidence = json.loads((destination / "evidence.json").read_text())
        self.assertEqual(evidence["status"], "failed")
        self.assertFalse(evidence["source_reopen_verified"])

    def test_external_linked_libraries_are_rejected(self):
        library = self.root / "external-library.blend"
        library.write_bytes(self.source.read_bytes())
        code = "with bpy.data.libraries.load(" + repr(str(library)) + ", link=True) as (data_from, data_to):\n    data_to.objects = ['Trusted fixture mesh']\nbpy.context.scene.collection.objects.link(data_to.objects[0])"
        source = self.mutated_fixture("external-library-user", code)
        destination = self.root / "external-library-check"
        process = self.invoke(["--source", str(source), "--output", str(destination)])
        self.assertNotEqual(process.returncode, 0)
        evidence = json.loads((destination / "evidence.json").read_text())
        self.assertIn("External linked Blender libraries", evidence["error"])
        self.assertFalse(evidence["source_reopen_verified"])

    def test_native_self_assertions_do_not_set_quality_scores(self):
        source = self.mutated_fixture("self-rating", "bpy.context.scene['source_editability_verified'] = True\nbpy.context.scene['quality_status'] = 'excellent'\nbpy.context.scene['score'] = 2")
        destination = self.root / "self-rating-check"
        process = self.invoke(["--source", str(source), "--output", str(destination), "--width", "128", "--height", "128"])
        self.assertEqual(process.returncode, 0, process.stderr + process.stdout)
        evidence = json.loads((destination / "evidence.json").read_text())
        self.assertEqual(evidence["quality_status"], "unassessed")
        self.assertEqual(evidence["inventory"]["quality_status"], "unassessed")
        self.assertNotIn("score", evidence)


if __name__ == "__main__":
    unittest.main()
