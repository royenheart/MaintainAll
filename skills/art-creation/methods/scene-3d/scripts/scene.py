#!/usr/bin/env python3
"""Export a deterministic lathe mesh, its recipe, and a projected form study."""

import argparse
import json
import math
from pathlib import Path


PROFILES = {
    "vase": [(0.24, 0), (0.46, 0.25), (0.5, 0.45), (0.35, 0.75), (0.22, 1)],
    "column": [(0.5, 0), (0.5, 0.25), (0.5, 0.75), (0.5, 1)],
    "rounded": [(0.14, 0), (0.4, 0.18), (0.5, 0.5), (0.4, 0.82), (0.14, 1)],
}


def build_mesh(shape, width, height, segments):
    if shape not in PROFILES:
        raise ValueError("Unknown shape")
    if not all(math.isfinite(value) and 0.1 <= value <= 4 for value in [width, height]):
        raise ValueError("Width and height must be finite values from 0.1 to 4")
    if not isinstance(segments, int) or not 6 <= segments <= 256:
        raise ValueError("Segments must be an integer from 6 to 256")
    profile = PROFILES[shape]
    vertices = []
    for radius, level in profile:
        for index in range(segments):
            angle = 2 * math.pi * index / segments
            vertices.append((width * radius * math.cos(angle), height * level,
                             width * radius * math.sin(angle)))
    faces = []
    for ring in range(len(profile) - 1):
        for index in range(segments):
            following = (index + 1) % segments
            lower, upper = ring * segments, (ring + 1) * segments
            faces.append((lower + index, upper + index,
                          upper + following, lower + following))
    bottom, top = len(vertices), len(vertices) + 1
    vertices.extend([(0, 0, 0), (0, height, 0)])
    for index in range(segments):
        following = (index + 1) % segments
        faces.append((bottom, index, following))
        offset = (len(profile) - 1) * segments
        faces.append((top, offset + following, offset + index))
    return vertices, faces


def obj_text(vertices, faces):
    lines = ["# MaintainAll procedural form study; arbitrary units"]
    lines.extend("v " + " ".join(f"{value:.8f}" for value in vertex) for vertex in vertices)
    lines.extend("f " + " ".join(str(index + 1) for index in face) for face in faces)
    return "\n".join(lines) + "\n"


def projected_svg(vertices, faces, yaw, height):
    if not math.isfinite(yaw) or not -180 <= yaw <= 180:
        raise ValueError("Yaw must be finite and between -180 and 180 degrees")
    angle, pitch = math.radians(yaw), math.radians(25)
    projected = []
    for x, y, z in vertices:
        y -= height / 2
        rx = math.cos(angle) * x + math.sin(angle) * z
        rz = -math.sin(angle) * x + math.cos(angle) * z
        projected.append((rx, math.cos(pitch) * y - math.sin(pitch) * rz,
                          math.sin(pitch) * y + math.cos(pitch) * rz))
    span = max(max(point[0] for point in projected) - min(point[0] for point in projected),
               max(point[1] for point in projected) - min(point[1] for point in projected))
    scale = 430 / span
    light = (0.6, 0.8, 0.5)
    light_length = math.sqrt(sum(value * value for value in light))
    polygons = []
    ordered = sorted(faces, key=lambda face: sum(projected[index][2] for index in face) / len(face))
    for face in ordered:
        a, b, c = (vertices[index] for index in face[:3])
        u, v = [b[i] - a[i] for i in range(3)], [c[i] - a[i] for i in range(3)]
        normal = (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0])
        length = math.sqrt(sum(value * value for value in normal))
        intensity = 0.35 + 0.65 * max(0, sum(normal[i]*light[i] for i in range(3)) / (length*light_length))
        color = "#" + "".join(f"{round(value*intensity):02x}" for value in (183, 116, 78))
        points = " ".join(f"{320+scale*projected[index][0]:.3f},{320-scale*projected[index][1]:.3f}"
                          for index in face)
        polygons.append(f'<polygon points="{points}" fill="{color}" stroke="{color}" stroke-width="0.4"/>')
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="640" height="640" viewBox="0 0 640 640">\n'
            '<title>Actual mesh: orthographic flat-shaded form study</title>\n'
            '<rect width="640" height="640" fill="#f4f1e9"/>\n' + "\n".join(polygons) +
            '<text x="24" y="610" font-family="sans-serif" font-size="14" fill="#253c40">'
            'Orthographic form study; no physical material rendering</text>\n</svg>\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shape", choices=PROFILES, default="vase")
    parser.add_argument("--width", type=float, default=1.0)
    parser.add_argument("--height", type=float, default=2.0)
    parser.add_argument("--segments", type=int, default=32)
    parser.add_argument("--yaw", type=float, default=30)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        vertices, faces = build_mesh(args.shape, args.width, args.height, args.segments)
        svg = projected_svg(vertices, faces, args.yaw, args.height)
        args.output.mkdir(parents=True, exist_ok=True)
        paths = [args.output / name for name in ["model.obj", "preview.svg", "recipe.json"]]
        if any(path.exists() for path in paths):
            raise ValueError("Output artifacts already exist; use a new iteration directory")
        recipe = {"method": "scene-3d", "algorithm": "lathe-study-v1", "units": "arbitrary",
                  "shape": args.shape, "width": args.width, "height": args.height,
                  "segments": args.segments, "yawDegrees": args.yaw,
                  "profile": PROFILES[args.shape], "projection": "orthographic",
                  "previewLimit": "Flat shading and painter sorting; no physical material rendering"}
        paths[0].write_text(obj_text(vertices, faces))
        paths[1].write_text(svg)
        paths[2].write_text(json.dumps(recipe, indent=2) + "\n")
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps({"model": str(paths[0]), "preview": str(paths[1]), "recipe": str(paths[2])}))


if __name__ == "__main__":
    main()
