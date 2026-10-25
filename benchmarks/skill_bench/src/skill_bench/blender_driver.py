"""Trusted, bounded native Blender evidence; never execute generated source programs.

Run with Blender's factory startup and disabled automatic execution. The caller
must enclose every invocation in its verified, network-disabled command sandbox,
cap memory/CPU/process lifetime, and mount only frozen inputs and new outputs.
This script is also importable without Blender for CLI and PNG validation tests.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import sys
import time
import zlib


MAX_SOURCE_BYTES = 64 * 1024 * 1024
MAX_RASTER_BYTES = 8 * 1024 * 1024
EDIT_SCOPE = (
    "One existing mesh object's local X-location; verifies a native object-transform "
    "edit only, not procedural-rule validity, rigging, cloth simulation, or VRM acceptance."
)


class EvidenceError(ValueError):
    """A native source or evidence operation violated the bounded contract."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def bounded_file(path: Path, limit: int) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise EvidenceError("Expected a regular, nonsymlink file")
    if path.stat().st_size > limit:
        raise EvidenceError("File byte ceiling exceeded")
    with path.open("rb") as handle:
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise EvidenceError("File byte ceiling exceeded")
    return data


def native_source(path: Path) -> bytes:
    data = bounded_file(path, MAX_SOURCE_BYTES)
    # Compressed files have a different header. Requiring the uncompressed native
    # representation makes the source-byte limit meaningful before Blender opens it.
    if (len(data) < 12 or data[:7] != b"BLENDER" or data[7:8] not in (b"_", b"-")
            or data[8:9] not in (b"v", b"V") or not data[9:12].isdigit()):
        raise EvidenceError("Unsupported native header: supply an uncompressed .blend file")
    return data


def raster_record(path: Path, expected: tuple[int, int] | None = None) -> dict:
    """Validate a bounded RGBA/RGB PNG and hash decoded pixels, not just metadata."""
    data = bounded_file(path, MAX_RASTER_BYTES)
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise EvidenceError("Expected a PNG raster")
    offset, compressed, geometry, ended = 8, bytearray(), None, False
    while offset < len(data):
        if offset + 12 > len(data):
            raise EvidenceError("Truncated PNG chunk")
        length = struct.unpack_from(">I", data, offset)[0]
        kind = data[offset + 4:offset + 8]
        end = offset + 12 + length
        if end > len(data):
            raise EvidenceError("Truncated PNG payload")
        body = data[offset + 8:offset + 8 + length]
        crc = struct.unpack_from(">I", data, offset + 8 + length)[0]
        if zlib.crc32(kind + body) & 0xFFFFFFFF != crc:
            raise EvidenceError("PNG CRC mismatch")
        if kind == b"IHDR":
            if geometry is not None or length != 13:
                raise EvidenceError("Invalid PNG header")
            width, height, depth, color, compression, filtering, interlace = struct.unpack(">IIBBBBB", body)
            if (not 1 <= width <= 1280 or not 1 <= height <= 1280 or width * height > 1_638_400
                    or depth != 8 or color not in (2, 6) or any((compression, filtering, interlace))):
                raise EvidenceError("Unsupported or unbounded PNG geometry")
            geometry = (width, height, 3 if color == 2 else 4)
        elif kind == b"IDAT":
            if geometry is None:
                raise EvidenceError("PNG data precedes its header")
            compressed.extend(body)
        elif kind == b"IEND":
            if length or end != len(data):
                raise EvidenceError("Invalid PNG ending")
            ended = True
            break
        elif kind[:1].isupper():
            raise EvidenceError("Unsupported critical PNG chunk")
        offset = end
    if geometry is None or not ended:
        raise EvidenceError("Incomplete PNG")
    width, height, channels = geometry
    if expected is not None and (width, height) != expected:
        raise EvidenceError("Unexpected PNG dimensions")
    stride = width * channels
    maximum = height * (stride + 1)
    decoder = zlib.decompressobj()
    raw = decoder.decompress(bytes(compressed), maximum + 1)
    if len(raw) != maximum or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
        raise EvidenceError("Invalid or oversized PNG decompression")
    pixels, previous = bytearray(), bytearray(stride)
    for row_index in range(height):
        start = row_index * (stride + 1)
        filtering = raw[start]
        row = bytearray(raw[start + 1:start + 1 + stride])
        if filtering > 4:
            raise EvidenceError("Unsupported PNG row filter")
        for index in range(stride):
            left = row[index - channels] if index >= channels else 0
            up = previous[index]
            upper_left = previous[index - channels] if index >= channels else 0
            if filtering == 1:
                predictor = left
            elif filtering == 2:
                predictor = up
            elif filtering == 3:
                predictor = (left + up) // 2
            elif filtering == 4:
                guess = left + up - upper_left
                distances = (abs(guess - left), abs(guess - up), abs(guess - upper_left))
                predictor = (left, up, upper_left)[distances.index(min(distances))]
            else:
                predictor = 0
            row[index] = (row[index] + predictor) & 0xFF
        pixels.extend(row)
        previous = row
    return {
        "path": path.name, "sha256": sha256(data), "size": len(data),
        "width": width, "height": height, "channels": channels,
        "pixel_sha256": sha256(bytes(pixels)),
    }


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        description="Safely reopen a frozen native Blender scene, capture three bounded views, and verify one native object-transform edit.",
        epilog="Caller must use a verified network-disabled sandbox with memory/CPU and whole-process time limits. Example: blender --background --factory-startup --disable-autoexec --threads 2 --python blender_driver.py -- --source frozen.blend --output NEWDIR",
    )
    choice = value.add_mutually_exclusive_group(required=True)
    choice.add_argument("--source", type=Path, help="Frozen, uncompressed .blend input; generated Python is never loaded.")
    choice.add_argument("--fixture", type=Path, help="Create a new trusted native healthcheck scene and print its file metadata.")
    value.add_argument("--output", type=Path, help="New evidence directory; required with --source.")
    value.add_argument("--width", type=int, default=640, help="PNG width, 64–1280 (default: 640).")
    value.add_argument("--height", type=int, default=480, help="PNG height, 64–1280 (default: 480).")
    value.add_argument("--max-objects", type=int, default=512, help="Source object ceiling, 1–512 (default: 512).")
    value.add_argument("--max-vertices", type=int, default=200_000, help="Total raw and evaluated mesh vertex ceiling, 1–200000.")
    value.add_argument("--render-timeout", type=float, default=20, help="Hard lifetime of each independent Blender capture process, 1–20 seconds.")
    value.add_argument("--worker", choices=("front", "side", "camera", "edited-front"), help=argparse.SUPPRESS)
    value.add_argument("--view-config", type=Path, help=argparse.SUPPRESS)
    return value


def arguments(argv: list[str] | None = None) -> argparse.Namespace:
    if argv is None:
        argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    result = parser().parse_args(argv)
    if (not 64 <= result.width <= 1280 or not 64 <= result.height <= 1280
            or result.width * result.height > 1_638_400 or not 1 <= result.max_objects <= 512
            or not 1 <= result.max_vertices <= 200_000 or not 1 <= result.render_timeout <= 20):
        raise EvidenceError("Unsupported resource limits")
    if result.source is not None and result.output is None:
        raise EvidenceError("--source requires --output")
    if result.fixture is not None and result.output is not None:
        raise EvidenceError("--fixture does not take --output")
    if bool(result.worker) != bool(result.view_config):
        raise EvidenceError("Internal worker requires a trusted view configuration")
    return result


def finite(values) -> list[float]:
    result = [float(value) for value in values]
    if not all(math.isfinite(value) and abs(value) <= 10_000_000 for value in result):
        raise EvidenceError("Nonfinite or unbounded scene coordinates")
    return result


def all_ids(bpy):
    """Inspect Blender ID collections including material/world node trees."""
    seen, total = set(), 0
    for name in dir(bpy.data):
        if name.startswith("_"):
            continue
        collection = getattr(bpy.data, name)
        if not hasattr(collection, "values") or not hasattr(collection, "__iter__"):
            continue
        for item in collection:
            if not hasattr(item, "as_pointer"):
                continue
            for candidate in (item, getattr(item, "node_tree", None)):
                if candidate is None or candidate.as_pointer() in seen:
                    continue
                seen.add(candidate.as_pointer())
                total += 1
                if total > 10_000:
                    raise EvidenceError("Native datablock ceiling exceeded")
                yield candidate


def safe_open(bpy, source: Path, args) -> dict:
    native_source(source)
    bpy.context.preferences.filepaths.use_scripts_auto_execute = False
    bpy.ops.wm.open_mainfile(filepath=str(source.resolve()), load_ui=False, use_scripts=False)
    bpy.context.preferences.filepaths.use_scripts_auto_execute = False
    if bpy.data.libraries:
        raise EvidenceError("External linked Blender libraries are unsupported")
    driver_count = 0
    for item in all_ids(bpy):
        if getattr(item, "library", None) is not None:
            raise EvidenceError("Linked external native datablocks are unsupported")
        animation = getattr(item, "animation_data", None)
        driver_count += len(animation.drivers) if animation else 0
    if driver_count:
        raise EvidenceError("Native drivers are unsupported; source refused before trusted capture")
    if bpy.data.movieclips or bpy.data.sounds or bpy.data.cache_files or bpy.data.volumes:
        raise EvidenceError("External movie, sound, cache, and volume resources are unsupported")
    for image in bpy.data.images:
        packed = bool(image.packed_file or len(image.packed_files))
        if image.source not in ("GENERATED", "VIEWER") and not (image.source == "FILE" and packed):
            raise EvidenceError("External or missing texture resource is unsupported: " + image.name)
    for scene in bpy.data.scenes:
        if scene.sequence_editor and len(scene.sequence_editor.strips):
            raise EvidenceError("Sequencer sources are unsupported")
    if len(bpy.data.objects) > args.max_objects:
        raise EvidenceError("Native object ceiling exceeded")
    raw_vertices = sum(len(mesh.vertices) for mesh in bpy.data.meshes)
    if raw_vertices > args.max_vertices:
        raise EvidenceError("Raw mesh vertex ceiling exceeded")
    if sum(len(mesh.polygons) for mesh in bpy.data.meshes) > args.max_vertices * 4:
        raise EvidenceError("Raw mesh polygon evaluation ceiling exceeded")
    node_count = 0
    for item in all_ids(bpy):
        nodes = getattr(item, "nodes", None)
        if nodes is None:
            continue
        node_count += len(nodes)
        if node_count > 20_000:
            raise EvidenceError("Native node evaluation ceiling exceeded")
        for node in nodes:
            if node.bl_idname.startswith("GeometryNode") and any(name in node.bl_idname for name in ("Import", "Bake", "Simulation")):
                raise EvidenceError("External import, bake, or simulation geometry nodes are unsupported")
    for obj in bpy.data.objects:
        if len(obj.modifiers) > 64:
            raise EvidenceError("Native modifier evaluation ceiling exceeded")
        for modifier in obj.modifiers:
            if modifier.type in ("CLOTH", "FLUID", "SOFT_BODY", "MESH_SEQUENCE_CACHE", "PARTICLE_SYSTEM"):
                raise EvidenceError("Simulation or external-cache modifiers are unsupported")
            if modifier.type == "SUBSURF" and max(modifier.levels, modifier.render_levels) > 3:
                raise EvidenceError("Subdivision evaluation ceiling exceeded")
            if modifier.type == "ARRAY" and modifier.count > 512:
                raise EvidenceError("Array evaluation ceiling exceeded")
    dependency = bpy.context.evaluated_depsgraph_get()
    evaluated_vertices = 0
    for obj in bpy.context.scene.objects:
        finite(obj.location)
        finite(obj.scale)
        finite(value for row in obj.matrix_world for value in row)
        if obj.type == "MESH":
            evaluated = obj.evaluated_get(dependency)
            mesh = evaluated.to_mesh()
            try:
                evaluated_vertices += len(mesh.vertices)
                if evaluated_vertices > args.max_vertices:
                    raise EvidenceError("Evaluated mesh vertex ceiling exceeded")
            finally:
                evaluated.to_mesh_clear()
    return {
        "autoexec_disabled": True, "drivers": driver_count,
        "embedded_texts": [{"name": text.name, "module": bool(text.use_module), "executed": False} for text in bpy.data.texts],
        "external_libraries": 0, "raw_vertices": raw_vertices,
        "evaluated_vertices": evaluated_vertices,
        "packed_images": [image.name for image in bpy.data.images if image.packed_file or len(image.packed_files)],
    }


def render_eligible_meshes(bpy) -> list:
    """Union renderable collection paths in the active view layer, ignoring viewport-only visibility."""
    objects = {}

    def visit(layer_collection):
        collection = layer_collection.collection
        if layer_collection.exclude or collection.hide_render:
            return
        for obj in collection.objects:
            if obj.type == "MESH" and not obj.hide_render and len(obj.data.vertices):
                objects[obj.name] = obj
        for child in layer_collection.children:
            visit(child)

    visit(bpy.context.view_layer.layer_collection)
    return list(objects.values())


def inventory(bpy, safety: dict) -> dict:
    eligible = {obj.name for obj in render_eligible_meshes(bpy)}
    objects = []
    for obj in sorted(bpy.data.objects, key=lambda item: item.name):
        item = {
            "name": obj.name, "type": obj.type, "parent": obj.parent.name if obj.parent else None,
            "location": finite(obj.location), "rotation_mode": obj.rotation_mode,
            "rotation_euler": finite(obj.rotation_euler), "rotation_quaternion": finite(obj.rotation_quaternion),
            "scale": finite(obj.scale), "matrix_world": [finite(row) for row in obj.matrix_world],
            "dimensions": finite(obj.dimensions), "hide_render": bool(obj.hide_render),
            "render_eligible_mesh": obj.name in eligible,
            "materials": [slot.material.name if slot.material else None for slot in obj.material_slots],
            "modifiers": [{"name": mod.name, "type": mod.type, "show_render": bool(mod.show_render)} for mod in obj.modifiers],
        }
        if obj.type == "MESH":
            digest = hashlib.sha256()
            for vertex in obj.data.vertices:
                digest.update(struct.pack("<3d", *finite(vertex.co)))
            for polygon in obj.data.polygons:
                digest.update(struct.pack("<I", len(polygon.vertices)))
                for vertex in polygon.vertices:
                    digest.update(struct.pack("<I", vertex))
            item["mesh"] = {"vertices": len(obj.data.vertices), "edges": len(obj.data.edges), "polygons": len(obj.data.polygons), "geometry_sha256": digest.hexdigest()}
        if obj.type == "CAMERA":
            item["camera"] = {"type": obj.data.type, "lens": float(obj.data.lens), "ortho_scale": float(obj.data.ortho_scale)}
        objects.append(item)
    materials = [{"name": material.name, "diffuse_color": finite(material.diffuse_color),
                  "roughness": float(material.roughness), "metallic": float(material.metallic),
                  "use_nodes": bool(material.use_nodes),
                  "node_types": sorted(node.bl_idname for node in material.node_tree.nodes) if material.node_tree else []}
                 for material in sorted(bpy.data.materials, key=lambda item: item.name)]
    return {"scene": bpy.context.scene.name, "frame": bpy.context.scene.frame_current,
            "view_layer": bpy.context.view_layer.name,
            "active_camera": bpy.context.scene.camera.name if bpy.context.scene.camera else None,
            "objects": objects, "materials": materials, "safety": safety,
            "quality_status": "unassessed", "geometry_counts_are_quality_scores": False}


def view_configuration(bpy) -> dict:
    from mathutils import Vector
    points = [obj.matrix_world @ Vector(corner) for obj in render_eligible_meshes(bpy) for corner in obj.bound_box]
    if not points:
        raise EvidenceError("No render-eligible mesh geometry is available in the active view layer")
    minimum = [min(point[axis] for point in points) for axis in range(3)]
    maximum = [max(point[axis] for point in points) for axis in range(3)]
    center = [(low + high) / 2 for low, high in zip(minimum, maximum)]
    span = max(high - low for low, high in zip(minimum, maximum))
    if not 0.000001 <= span <= 1_000_000:
        raise EvidenceError("Unsupported scene extent")
    return {"center": finite(center), "span": span, "minimum": finite(minimum), "maximum": finite(maximum),
            "camera_name": bpy.context.scene.camera.name if bpy.context.scene.camera else None}


def configure_render(bpy, args, view: str, config: dict) -> dict:
    from mathutils import Vector
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.threads_mode = "FIXED"
    scene.render.threads = 2
    scene.render.resolution_x, scene.render.resolution_y = args.width, args.height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "8"
    scene.render.film_transparent = False
    scene.display.render_aa = "8"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_shadows = True
    scene.display.shading.show_cavity = True
    scene.display.shading.background_type = "WORLD"
    scene.world = scene.world or bpy.data.worlds.new("Trusted evidence world")
    scene.world.color = (0.12, 0.12, 0.12)
    native = bpy.data.objects.get(config.get("camera_name")) if config.get("camera_name") else None
    if view == "camera" and native is not None and native.type == "CAMERA":
        scene.camera = native
        camera_origin = "native source camera"
    else:
        center, span = Vector(config["center"]), config["span"]
        directions = {"front": Vector((0, -1, 0)), "side": Vector((1, 0, 0)),
                      "camera": Vector((1, -1.6, 0.9)), "edited-front": Vector((0, -1, 0))}
        camera = bpy.data.objects.new("Trusted evidence camera", bpy.data.cameras.new("Trusted evidence camera"))
        scene.collection.objects.link(camera)
        camera.location = center + directions[view].normalized() * span * 3
        camera.rotation_euler = (center - camera.location).to_track_quat("-Z", "Y").to_euler()
        camera.data.type = "ORTHO"
        camera.data.ortho_scale = span * 1.55 * max(1, args.height / args.width)
        camera.data.clip_start = max(span / 100_000, 0.000001)
        camera.data.clip_end = span * 10
        scene.camera = camera
        camera_origin = "trusted fixed source-bounds view"
    return {"view": view, "camera_origin": camera_origin, "engine": "BLENDER_WORKBENCH",
            "software_render_requested": os.environ.get("LIBGL_ALWAYS_SOFTWARE") == "1",
            "threads": 2, "llvmpipe_threads_requested": os.environ.get("LP_NUM_THREADS"), "native_shaders_preserved": False,
            "scope": "Geometry and diffuse material overview; Workbench does not validate native lighting or shader output."}


def render_worker(bpy, args) -> dict:
    safety = safe_open(bpy, args.source, args)
    config = json.loads(bounded_file(args.view_config, 32_768))
    if set(config) != {"center", "span", "minimum", "maximum", "camera_name"}:
        raise EvidenceError("Invalid trusted view configuration")
    finite(config["center"])
    details = configure_render(bpy, args, args.worker, config)
    args.output.mkdir(parents=False, mode=0o700, exist_ok=True)
    target = args.output / (args.worker + ".png")
    bpy.context.scene.render.filepath = str(target.resolve())
    started = time.monotonic()
    bpy.ops.render.render(write_still=True, layer=bpy.context.view_layer.name)
    details["elapsed_seconds"] = round(time.monotonic() - started, 4)
    import gpu
    details["gpu_renderer"] = gpu.platform.renderer_get()
    details["gpu_vendor"] = gpu.platform.vendor_get()
    details["software_render_observed"] = any(name in details["gpu_renderer"].lower() for name in ("llvmpipe", "softpipe", "software"))
    if not details["software_render_observed"]:
        raise EvidenceError("Workbench software renderer was requested but not confirmed")
    details.update(raster_record(target, (args.width, args.height)))
    # The edited worker independently opens the actual modified .blend before
    # returning this inventory; parent comparisons do not trust generated claims.
    result = {"source_sha256": sha256(native_source(args.source)), "rendered": details,
              "inventory": inventory(bpy, safety)}
    (args.output / (args.worker + ".json")).write_text(json.dumps(result, sort_keys=True), encoding="utf-8")
    return result


def capture(args, source: Path, view: str, config: Path) -> dict:
    import bpy
    command = [bpy.app.binary_path, "--background", "--factory-startup", "--disable-autoexec",
               "--threads", "2", "--python-exit-code", "1", "--python", str(Path(__file__).resolve()), "--",
               "--source", str(source.resolve()), "--output", str(args.output.resolve()), "--worker", view,
               "--view-config", str(config.resolve()), "--width", str(args.width), "--height", str(args.height),
               "--max-objects", str(args.max_objects), "--max-vertices", str(args.max_vertices)]
    environment = dict(os.environ, LIBGL_ALWAYS_SOFTWARE="1", MESA_LOADER_DRIVER_OVERRIDE="llvmpipe",
                       LP_NUM_THREADS="2", OMP_NUM_THREADS="2", OPENBLAS_NUM_THREADS="2")
    # Keep captures in the enclosing sandbox's process group so its global
    # timeout also kills an in-progress capture if this coordinator is stopped.
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=environment)
    try:
        stdout, stderr = process.communicate(timeout=args.render_timeout)
    except subprocess.TimeoutExpired as error:
        process.kill()
        process.communicate()
        raise EvidenceError("Independent Blender capture exceeded its hard lifetime: " + view) from error
    if process.returncode:
        raise EvidenceError("Independent Blender capture failed: " + view + "; " + (stderr or stdout)[-2000:].decode("utf-8", "replace"))
    result = json.loads(bounded_file(args.output / (view + ".json"), 4 * 1024 * 1024))
    if result.get("source_sha256") != sha256(native_source(source)):
        raise EvidenceError("Independent native reopen source hash mismatch")
    raster = raster_record(args.output / (view + ".png"), (args.width, args.height))
    if any(result["rendered"].get(key) != value for key, value in raster.items()):
        raise EvidenceError("Independent raster metadata mismatch")
    return result


def fixture(bpy, destination: Path) -> dict:
    if destination.exists() or destination.is_symlink():
        raise EvidenceError("Fixture path must be new")
    if not destination.parent.is_dir():
        raise EvidenceError("Fixture parent directory must already exist")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.mesh.primitive_cube_add(size=2)
    cube = bpy.context.object
    cube.name = "Trusted fixture mesh"
    cube.scale = (0.8, 0.5, 1.2)
    material = bpy.data.materials.new("Trusted fixture blue")
    material.diffuse_color = (0.04, 0.3, 0.8, 1)
    cube.data.materials.append(material)
    from mathutils import Vector
    camera = bpy.data.objects.new("Trusted fixture camera", bpy.data.cameras.new("Trusted fixture camera"))
    bpy.context.scene.collection.objects.link(camera)
    camera.location = (5, -7, 4)
    camera.rotation_euler = (-Vector(camera.location)).to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = camera
    bpy.ops.wm.save_as_mainfile(filepath=str(destination.resolve()), compress=False, check_existing=False)
    data = native_source(destination)
    return {"path": str(destination), "sha256": sha256(data), "size": len(data), "fixture": True}


def verify_native(bpy, args) -> dict:
    source_data = native_source(args.source)
    if args.output.exists() or args.output.is_symlink():
        raise EvidenceError("Evidence output directory must be new")
    if not args.output.parent.is_dir():
        raise EvidenceError("Evidence output parent directory must already exist")
    args.output.mkdir(mode=0o700)
    initial = {"source_sha256": sha256(source_data), "source_reopen_verified": False,
               "source_editability_verified": False, "edit_scope": EDIT_SCOPE,
               "quality_status": "unassessed", "generated_code_executed": False,
               "verifier_sha256": sha256(Path(__file__).read_bytes()),
               "blender_version": bpy.app.version_string, "rendered": {}}
    try:
        safety = safe_open(bpy, args.source, args)
        initial["source_reopen_verified"] = True
        initial["inventory"] = inventory(bpy, safety)
        config = view_configuration(bpy)
        config_path = args.output / "trusted-view.json"
        config_path.write_text(json.dumps(config, sort_keys=True), encoding="utf-8")
        for view in ("front", "side", "camera"):
            original = capture(args, args.source, view, config_path)
            initial["rendered"][view] = original["rendered"]
        candidates = render_eligible_meshes(bpy)
        target = max(candidates, key=lambda obj: max(obj.dimensions))
        before = finite(target.location)
        delta = config["span"] * 0.12
        target.location.x += delta
        after = finite(target.location)
        initial["edit"] = {"object": target.name, "attribute": "location.x", "before": before[0],
                           "after": after[0], "delta": delta, "basis": "12% of the frozen source scene's maximum extent"}
        edited_path = args.output / "edited.blend"
        bpy.context.scene.render.engine = "BLENDER_WORKBENCH"
        bpy.ops.wm.save_as_mainfile(filepath=str(edited_path.resolve()), compress=False, check_existing=False)
        modified = native_source(edited_path)
        edited = capture(args, edited_path, "edited-front", config_path)
        reopened = next((obj for obj in edited["inventory"]["objects"] if obj["name"] == target.name), None)
        observed = reopened is not None and math.isclose(reopened["location"][0], after[0], rel_tol=1e-6, abs_tol=1e-6)
        pixels_changed = initial["rendered"]["front"]["pixel_sha256"] != edited["rendered"]["pixel_sha256"]
        initial["rendered"]["edited-front"] = edited["rendered"]
        initial["rendered"]["source"] = dict(initial["rendered"]["front"])
        initial["rendered"]["edited"] = dict(edited["rendered"])
        initial["modified_native"] = {"path": edited_path.name, "sha256": sha256(modified), "size": len(modified),
                                      "independent_reopen_verified": True, "edit_observed": observed,
                                      "raster_pixels_changed": pixels_changed}
        initial["source_editability_verified"] = bool(observed and pixels_changed and sha256(modified) != initial["source_sha256"])
        initial["status"] = "completed"
    except Exception as error:
        initial["status"] = "failed"
        initial["error"] = str(error)
        (args.output / "evidence.json").write_text(json.dumps(initial, indent=2, sort_keys=True), encoding="utf-8")
        raise
    (args.output / "evidence.json").write_text(json.dumps(initial, indent=2, sort_keys=True), encoding="utf-8")
    return initial


def main(argv: list[str] | None = None) -> int:
    try:
        args = arguments(argv)
        import bpy
        if args.fixture is not None:
            result = fixture(bpy, args.fixture)
        elif args.worker:
            result = render_worker(bpy, args)
        else:
            result = verify_native(bpy, args)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (EvidenceError, ImportError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
