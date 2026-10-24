#!/usr/bin/env python3
"""Read-only review preview and byte-preserving evidence packages."""
from __future__ import annotations

import argparse
from decimal import Decimal
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
import threading
from urllib.parse import parse_qs, unquote, urlsplit
import zipfile

ASSETS = Path(__file__).resolve().parents[1] / "assets"
STATIC = {"index.html", "style.css", "app.js", "vendor/marked.js", "vendor/purify.js"}
IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp"}


class ReviewError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ReviewError(message)


def pairs(values):
    result = {}
    for key, value in values:
        require(key not in result, f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def relative_path(root, value):
    require(isinstance(value, str) and value and "\\" not in value and ":" not in value, f"Invalid relative path: {value!r}")
    relative = PurePosixPath(value)
    require(not relative.is_absolute() and ".." not in relative.parts and relative.as_posix() == value, f"Invalid relative path: {value}")
    result = (root / value).resolve()
    require(result.is_relative_to(root.resolve()), f"Path escapes root: {value}")
    return result


def fingerprint(path):
    h = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
            size += len(chunk)
    return size, h.hexdigest()


def web_url(value):
    require(isinstance(value, str) and urlsplit(value).scheme in {"http", "https"} and urlsplit(value).netloc, f"Invalid HTTP(S) URL: {value!r}")


class Case:
    def __init__(self, root, value, verify=True):
        require(isinstance(value, dict), "Each item must be an object")
        self.value = value
        self.verify = verify
        self.id = value.get("id")
        require(isinstance(self.id, str) and re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", self.id), "Invalid item id")
        require(isinstance(value.get("title"), str) and value["title"], f"{self.id}: missing title")
        require(all(isinstance(value.get(key, ""), str) for key in ("baseline", "candidate")), f"{self.id}: revisions must be text")
        self.root = relative_path(root, value.get("root"))
        require(self.root.is_dir(), f"{self.id}: root directory missing")
        self.files = {}
        for kind in ("issue", "pr"):
            draft = value.get(kind)
            require(isinstance(draft, dict) and isinstance(draft.get("title"), str) and draft["title"], f"{self.id}: {kind} requires title")
            if kind == "pr":
                require(isinstance(draft.get("draft"), bool), f"{self.id}: pr.draft must be boolean")
            if "url" in draft:
                web_url(draft["url"])
            self.add(draft.get("body"), {"role": kind})
        self.add(value.get("patch"), {"role": "patch"})
        require(isinstance(value.get("files"), list), f"{self.id}: files must be an array")
        urls = set()
        for file in value["files"]:
            require(isinstance(file, dict), f"{self.id}: invalid file entry")
            require(isinstance(file.get("role", "evidence"), str), f"{self.id}: file role must be text")
            require(isinstance(file.get("sha256"), str) and re.fullmatch(r"[0-9a-f]{64}", file["sha256"]), f"{self.id}: file requires SHA-256")
            if "url" in file:
                web_url(file["url"])
                require(file["url"] not in urls, f"{self.id}: duplicate file URL")
                urls.add(file["url"])
            if file.get("role") == "screenshot":
                require(Path(file.get("path", "")).suffix.lower() in IMAGE_TYPES, f"{self.id}: unsupported screenshot type")
            self.add(file.get("path"), file)
        require(isinstance(value.get("metrics", []), list), f"{self.id}: metrics must be an array")
        for metric in value.get("metrics", []):
            require(isinstance(metric, dict) and all(key in metric for key in ("label", "before", "after", "unit", "scope", "source")), f"{self.id}: incomplete metric")
            require(isinstance(metric["source"], str) and metric["source"] in self.files, f"{self.id}: metric source must be included")
            require(all(isinstance(metric[k], str) and metric[k] for k in ("label", "unit", "scope")), f"{self.id}: metric labels/scope must be text")
            require(all(isinstance(metric[k], (str, int, Decimal)) and not isinstance(metric[k], bool) for k in ("before", "after")), f"{self.id}: metric values must be text or numbers")
        require(isinstance(value.get("types", []), list) and all(isinstance(x, str) for x in value.get("types", [])), f"{self.id}: types must be strings")

    def add(self, name, record):
        path = relative_path(self.root, name)
        require(name != "review-manifest.json" and name not in self.files, f"{self.id}: duplicate/reserved file: {name}")
        require(path.is_file(), f"{self.id}: file missing: {name}")
        size, sha = fingerprint(path) if self.verify or "sha256" not in record else (path.stat().st_size, record["sha256"])
        require(record.get("sha256", sha) == sha, f"{self.id}: SHA-256 mismatch: {name}")
        self.files[name] = {"path": name, "role": record.get("role", "evidence"), "bytes": size, "sha256": sha, **({"url": record["url"]} if "url" in record else {})}

    def snapshot(self, name):
        require(name in self.files, f"{self.id}: unlisted file")
        record = self.files[name]
        result = tempfile.SpooledTemporaryFile(max_size=1024 * 1024)
        try:
            h = hashlib.sha256()
            with relative_path(self.root, name).open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    h.update(chunk)
                    result.write(chunk)
            require(h.hexdigest() == record["sha256"], f"{self.id}: file changed: {name}")
            size = result.tell()
            result.seek(0)
            return result, size
        except BaseException:
            result.close()
            raise

    def public(self):
        value = self.value
        metrics = [{**{key: row[key] for key in ("label", "unit", "scope", "source")}, "before": str(row["before"]), "after": str(row["after"])} for row in value.get("metrics", [])]
        drafts = {kind: {key: value[kind][key] for key in ("title", "body", "url", "draft") if key in value[kind]} for kind in ("issue", "pr")}
        return {"id": self.id, "title": value["title"], "baseline": value.get("baseline", ""), "candidate": value.get("candidate", ""), "types": value.get("types", []), **drafts, "patch": value["patch"], "files": list(self.files.values()), "metrics": metrics}


class Review:
    def __init__(self, path, verify=True):
        self.path = Path(path).resolve()
        value = json.loads(self.path.read_text(), parse_float=Decimal, object_pairs_hook=pairs)
        require(isinstance(value, dict) and isinstance(value.get("project"), str) and value["project"], "Manifest requires project")
        require(isinstance(value.get("items"), list) and value["items"], "Manifest requires nonempty items")
        self.project = value["project"]
        self.items = {}
        for entry in value["items"]:
            item = Case(self.path.parent, entry, verify)
            require(item.id not in self.items, f"Duplicate item: {item.id}")
            self.items[item.id] = item

    def public(self):
        return {"project": self.project, "items": [item.public() for item in self.items.values()], "readOnly": True}


def pack(review, item_id, output):
    require(item_id in review.items, "Unknown item")
    item = review.items[item_id]
    output = Path(output)
    destination = output.open("xb")
    try:
        with destination:
            public = item.public()
            index = {"project": review.project, **{key: public[key] for key in ("id", "title", "baseline", "candidate", "types", "issue", "pr", "metrics")}, "files": {}}
            with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for name, record in sorted(item.files.items()):
                    source, size = item.snapshot(name)
                    with source, archive.open(item_id + "/" + name, "w") as target:
                        shutil.copyfileobj(source, target, length=1024 * 1024)
                    index["files"][name] = {"bytes": size, "sha256": record["sha256"]}
                archive.writestr(item_id + "/review-manifest.json", json.dumps(index, indent=2) + "\n")
    except BaseException:
        output.unlink()
        raise
    return index


def make_server(manifest, bind="127.0.0.1", port=8787):
    manifest = Path(manifest).resolve()
    Review(manifest)
    archive_lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def send_headers(self, size, mime, filename=None):
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(size))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            if filename:
                from urllib.parse import quote
                self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + quote(filename, safe=""))
            self.end_headers()

        def bytes(self, data, mime):
            self.send_headers(len(data), mime)
            if self.command != "HEAD":
                self.wfile.write(data)

        def do_HEAD(self):
            self.do_GET()

        def do_POST(self):
            self.send_error(405, "Read-only preview")

        def do_GET(self):
            route = urlsplit(self.path)
            query = parse_qs(route.query)
            try:
                if route.path == "/" or route.path.startswith("/assets/"):
                    name = "index.html" if route.path == "/" else unquote(route.path[len("/assets/"):])
                    require(name in STATIC, "Unknown asset")
                    mime = "application/javascript; charset=utf-8" if name.endswith(".js") else "text/css; charset=utf-8" if name.endswith(".css") else "text/html; charset=utf-8"
                    self.bytes(relative_path(ASSETS, name).read_bytes(), mime)
                    return
                review = Review(manifest, verify=False)
                if route.path == "/api/review":
                    self.bytes(json.dumps(review.public()).encode(), "application/json; charset=utf-8")
                    return
                item_id = query.get("item", [""])[0]
                require(item_id in review.items, "Unknown item")
                item = review.items[item_id]
                if route.path == "/file":
                    name = query.get("path", [""])[0]
                    source, size = item.snapshot(name)
                    with source:
                        mime = IMAGE_TYPES.get(Path(name).suffix.lower(), "text/plain; charset=utf-8")
                        if query.get("download"):
                            mime = "application/octet-stream"
                        self.send_headers(size, mime, PurePosixPath(name).name if query.get("download") else None)
                        if self.command != "HEAD":
                            shutil.copyfileobj(source, self.wfile, length=1024 * 1024)
                    return
                if route.path == "/archive":
                    with archive_lock, tempfile.TemporaryDirectory(prefix="change-review-") as directory:
                        output = Path(directory) / (item_id + ".zip")
                        pack(review, item_id, output)
                        self.send_headers(output.stat().st_size, "application/zip", output.name)
                        if self.command != "HEAD":
                            with output.open("rb") as source:
                                shutil.copyfileobj(source, self.wfile, length=1024 * 1024)
                    return
                self.send_error(404)
            except (ReviewError, OSError, json.JSONDecodeError):
                self.send_error(400, "Review unavailable; run local manifest validation for details")

    return ThreadingHTTPServer((bind, port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "serve", "pack"):
        command = commands.add_parser(name)
        command.add_argument("--manifest", type=Path, required=True)
        if name == "serve":
            command.add_argument("--bind", default="127.0.0.1")
            command.add_argument("--port", type=int, default=8787)
        if name == "pack":
            command.add_argument("--item", required=True)
            command.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        review = Review(args.manifest)
        if args.command == "validate":
            print(json.dumps({"status": "passed", "items": len(review.items), "files": sum(len(item.files) for item in review.items.values())}))
        elif args.command == "pack":
            index = pack(review, args.item, args.output)
            print(json.dumps({"output": str(args.output.resolve()), "files": len(index["files"])}))
        else:
            server = make_server(args.manifest, args.bind, args.port)
            print(f"Read-only review: http://{args.bind}:{server.server_port}/", flush=True)
            try:
                server.serve_forever()
            finally:
                server.server_close()
    except (ReviewError, OSError, json.JSONDecodeError) as error:
        parser.exit(1, f"review: {error}\n")


if __name__ == "__main__":
    main()
