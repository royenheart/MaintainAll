#!/usr/bin/env python3
"""Initialize, check, export and serve a native Godot project using installed tools."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import sys

STARTER = Path(__file__).resolve().parents[1] / "templates/feel-lab"


def engine_path(value):
    candidate = shutil.which(value)
    if not candidate:
        raise ValueError("Godot executable was not found; supply --engine /path/to/godot")
    return str(Path(candidate).resolve())


def run_engine(engine, arguments, timeout=180):
    result = subprocess.run([engine, *arguments], capture_output=True, text=True, timeout=timeout)
    log = result.stdout + result.stderr
    if result.returncode or any(line.lstrip().startswith(("ERROR:", "SCRIPT ERROR:")) for line in log.splitlines()):
        raise ValueError("Godot failed:\n" + log[-12000:])
    return log


def project_root(value):
    root = Path(value).resolve()
    if not (root / "project.godot").is_file():
        raise ValueError("Project directory must contain project.godot")
    return root


def initialize(output):
    target = Path(output).absolute()
    if target.exists() or target.is_symlink():
        raise ValueError("Initialize into a new directory")
    target = target.resolve()
    shutil.copytree(STARTER, target, ignore=shutil.ignore_patterns(".godot", "*.uid"))
    return {"project": str(target), "native_engine": "Godot", "starter": "feel-lab"}


def check(engine, project, frames=30):
    root = project_root(project)
    run_engine(engine, ["--headless", "--path", str(root), "--import"])
    log = run_engine(engine, ["--headless", "--path", str(root), "--quit-after", str(frames)])
    return {"checked": True, "frames": frames, "log": log.strip()}


def export(engine, project, preset, output):
    root = project_root(project)
    target = Path(output).absolute()
    if target.exists() or target.is_symlink():
        raise ValueError("Export into a new directory to keep previous previews available")
    target = target.resolve()
    if target.is_relative_to(root):
        raise ValueError("Place exported builds outside the source project")
    check(engine, root)
    target.mkdir(parents=True)
    filename = "index.html" if preset == "Web" else "game.x86_64"
    run_engine(engine, ["--headless", "--path", str(root), "--export-release", preset, str(target / filename)], timeout=300)
    if not (target / filename).is_file():
        raise ValueError("Godot did not produce the requested build")
    files = sorted(path.name for path in target.iterdir() if path.is_file())
    manifest = {"schema_version": 1, "engine": run_engine(engine, ["--version"]).strip(), "preset": preset,
                "files": {name: hashlib.sha256((target / name).read_bytes()).hexdigest() for name in files}}
    (target / "build-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return {"exported": True, "preset": preset, "directory": str(target), "files": [*files, "build-manifest.json"]}


class PreviewHandler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, ".wasm": "application/wasm", ".pck": "application/octet-stream"}
    def __init__(self, *args, isolated=False, **kwargs):
        self.isolated = isolated
        super().__init__(*args, **kwargs)

    def do_GET(self):
        if self.path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return
        super().do_GET()

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        if self.isolated:
            self.send_header("Cross-Origin-Opener-Policy", "same-origin")
            self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        super().end_headers()

    def list_directory(self, path):
        self.send_error(404)
        return None


def serve(root, bind, port, isolated=False, cert=None, key=None):
    if bool(cert) != bool(key):
        raise ValueError("Supply --cert and --key together")
    directory = Path(root).resolve()
    if not (directory / "index.html").is_file() or not list(directory.glob("*.wasm")) or not list(directory.glob("*.pck")):
        raise ValueError("Serve a Godot Web export directory containing index.html, WASM and PCK files")
    if (directory / "project.godot").exists() or any(path.is_symlink() for path in directory.rglob("*")):
        raise ValueError("Use the exported build directory without source files or symbolic links")
    handler = partial(PreviewHandler, directory=str(directory), isolated=isolated)
    with ThreadingHTTPServer((bind, port), handler) as server:
        if cert:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(cert, key)
            server.socket = context.wrap_socket(server.socket, server_side=True)
        print(json.dumps({"serving": str(directory), "bind": bind, "port": server.server_port, "https": bool(cert), "isolation_headers": isolated}), flush=True)
        server.serve_forever()


def parser():
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--engine", default="godot", help="Installed Godot executable name or path (default: godot)")
    commands = value.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="Print the engine version and installed export template files")
    init = commands.add_parser("init", help="Copy the native movement/feedback starter into a new project directory")
    init.add_argument("--output", required=True, type=Path)
    validate = commands.add_parser("check", help="Import resources and run a bounded headless scene check")
    validate.add_argument("--project", required=True, type=Path)
    validate.add_argument("--frames", type=int, default=30, choices=range(1, 601), metavar="1..600")
    build = commands.add_parser("export", help="Check and export the same native project into a new Web or Linux build")
    build.add_argument("--project", required=True, type=Path)
    build.add_argument("--preset", choices=("Web", "Linux"), default="Web")
    build.add_argument("--output", required=True, type=Path)
    preview = commands.add_parser("serve", help="Serve an exported game; requires no running Godot editor")
    preview.add_argument("--root", required=True, type=Path)
    preview.add_argument("--bind", default="127.0.0.1", help="Bind address; use a reachable interface for remote previews")
    preview.add_argument("--port", type=int, default=8792)
    preview.add_argument("--isolation-headers", action="store_true", help="Add COOP/COEP for threaded builds; remote browsers also require HTTPS")
    preview.add_argument("--cert", type=Path, help="TLS certificate chain for HTTPS preview")
    preview.add_argument("--key", type=Path, help="Private key matching --cert; keep it outside the exported directory")
    return value


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "init":
            result = initialize(args.output)
        elif args.command == "serve":
            serve(args.root, args.bind, args.port, args.isolation_headers, args.cert, args.key)
            return 0
        else:
            engine = engine_path(args.engine)
            if args.command == "doctor":
                version = run_engine(engine, ["--version"]).strip()
                parts = version.split(".")
                channel_index = 3 if len(parts) > 2 and parts[2].isdigit() else 2
                version_dir = ".".join(parts[:channel_index + 1])
                template_root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "godot/export_templates" / version_dir
                result = {"engine": engine, "version": version, "template_directory": str(template_root), "templates": sorted(path.name for path in template_root.glob("*") if path.is_file())}
            elif args.command == "check":
                result = check(engine, args.project, args.frames)
            else:
                result = export(engine, args.project, args.preset, args.output)
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
