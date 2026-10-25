"""Versioned public result packages; Git stores the catalog, not generated sites."""
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import stat
import tempfile
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import zipfile

from .publication import (DEFAULT_REPORTS, MAX_COLLECTION_BYTES, MAX_REPORTS, NAME,
                          _ordinary_directory, _suites, _title, _unique_object, validate_collection)
from .report import render_html, validate_public_bundle
from .review import MAX_JSON_BYTES, checked_file

DEFAULT_CATALOG = 'benchmarks/results/catalog.json'
MAX_PACKAGE_BYTES = 64 * 1024 * 1024
MAX_MEMBERS = 1024
SHA = re.compile(r'[0-9a-f]{64}')
MEMBER = re.compile(r'(?:report\.json|media/[0-9a-f]{64}\.(?:png|jpg|webp|gif))')
SUMMARY_FIELDS = {'experiments', 'trials', 'ratings', 'pairs', 'images'}


def _https_url(value):
    if not isinstance(value, str) or any(ord(char) <= 32 or ord(char) == 127 for char in value):
        raise ValueError('Result packages require public HTTPS URLs')
    url = urlsplit(value)
    if url.scheme != 'https' or not url.hostname or url.username or url.password or url.fragment or url.port not in (None, 443):
        raise ValueError('Result packages require public HTTPS URLs without credentials or fragments')
    return url


def load_catalog(path):
    """Validate the small committed index without downloading any result data."""
    path = Path(path)
    _, raw = checked_file(path.parent, path.name, max_bytes=256 * 1024)
    value = json.loads(raw, object_pairs_hook=_unique_object)
    if not isinstance(value, dict) or set(value) != {'schema_version', 'suites', 'reports'} or type(value['schema_version']) is not int or value['schema_version'] != 1:
        raise ValueError('Result catalog requires schema_version 1, suites and reports')
    suites = _suites(value['suites'])
    suite_ids = {entry['id'] for entry in suites}
    if not isinstance(value['reports'], list) or not 1 <= len(value['reports']) <= MAX_REPORTS:
        raise ValueError('Result catalog requires one to 128 reports')
    ids, paths, filenames, total = set(), set(), set(), 0
    for entry in value['reports']:
        if not isinstance(entry, dict) or set(entry) != {'id', 'title', 'path', 'suite_id', 'package', 'report_fingerprint', 'summary'}:
            raise ValueError('Invalid result catalog entry fields')
        if any(not isinstance(entry[key], str) or not NAME.fullmatch(entry[key]) or entry[key] in {'.', '..'} for key in ('id', 'path')):
            raise ValueError('Result identities and paths must be safe single directory names')
        if entry['id'] in ids or entry['path'] in paths:
            raise ValueError('Duplicate result identity or path')
        if not isinstance(entry['suite_id'], str) or entry['suite_id'] not in suite_ids:
            raise ValueError('Result refers to an unknown suite')
        _title(entry['title'])
        package = entry['package']
        if not isinstance(package, dict) or set(package) != {'url', 'sha256', 'size'}:
            raise ValueError('A package requires url, sha256 and size')
        url = _https_url(package['url'])
        filename = url.path.rsplit('/', 1)[-1]
        if url.query or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,150}\.zip', filename) or filename in filenames:
            raise ValueError('Package URLs require distinct ZIP filenames without query strings')
        if any(not isinstance(digest, str) or not SHA.fullmatch(digest) for digest in (package['sha256'], entry['report_fingerprint'])):
            raise ValueError('Package and report hashes must be full SHA-256 values')
        if type(package['size']) is not int or not 1 <= package['size'] <= MAX_PACKAGE_BYTES:
            raise ValueError('Package exceeds the 64 MiB size limit')
        summary = entry['summary']
        if not isinstance(summary, dict) or set(summary) != SUMMARY_FIELDS:
            raise ValueError('Result summary fields are incomplete')
        if not isinstance(summary['experiments'], list) or not summary['experiments'] or any(not isinstance(item, str) or not NAME.fullmatch(item) for item in summary['experiments']):
            raise ValueError('Summary requires experiment identities')
        if len(summary['experiments']) != len(set(summary['experiments'])):
            raise ValueError('Summary experiment identities must be unique')
        if any(type(summary[key]) is not int or summary[key] < 0 for key in SUMMARY_FIELDS - {'experiments'}):
            raise ValueError('Summary counts must be nonnegative integers')
        ids.add(entry['id'])
        paths.add(entry['path'])
        filenames.add(filename)
        total += package['size']
    if total > MAX_COLLECTION_BYTES or {entry['suite_id'] for entry in value['reports']} != suite_ids:
        raise ValueError('Result catalog exceeds its size limit or contains an empty suite')
    return value


def _summary(report):
    return {'experiments': [entry['id'] for entry in report['experiments']],
            **{key: len(report[key]) for key in ('trials', 'ratings', 'pairs')},
            'images': len({item['export_path'] for item in report['media']})}


def _new_path(path):
    target = Path(path).absolute()
    if '..' in target.parts or any(part.is_symlink() for part in (target, *target.parents)) or target.exists():
        raise ValueError('Use a new destination without symbolic links or parent traversal')
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def pack_report(root, output):
    """Pack validated JSON and exact image bytes; HTML is rebuilt on restoration."""
    root = _ordinary_directory(root)
    proof = validate_public_bundle(root)
    _, raw = checked_file(root, 'report.json')
    report = json.loads(raw)
    if report['report_fingerprint'] != proof['report_fingerprint']:
        raise ValueError('Report changed during packaging')
    target = _new_path(output)
    if target.is_relative_to(root):
        raise ValueError('Place the result package outside its source bundle')
    images = {item['export_path']: item for item in report['media']}
    if len(images) + 1 > MAX_MEMBERS:
        raise ValueError('Result package has too many files')
    with tempfile.TemporaryDirectory(prefix='.pack-', dir=target.parent) as temporary:
        packed = Path(temporary) / 'result.zip'
        with zipfile.ZipFile(packed, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name in sorted(['report.json', *images]):
                if name == 'report.json':
                    data = raw
                else:
                    item = images[name]
                    _, data = checked_file(root, name, expected_hash=item['sha256'], expected_size=item['size'])
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                info.compress_type = zipfile.ZIP_DEFLATED if name == 'report.json' else zipfile.ZIP_STORED
                archive.writestr(info, data)
        _, data = checked_file(packed.parent, packed.name, max_bytes=MAX_PACKAGE_BYTES)
        # Validate the actual archive before publishing it, including the frozen summary.
        metadata = {'package': {'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data)},
                    'report_fingerprint': proof['report_fingerprint'], 'summary': _summary(report)}
        _restore(data, metadata, Path(temporary) / 'verified')
        with target.open('xb') as destination:
            destination.write(data)
    return {'valid': True, 'generation_calls': 0, **metadata}


class _HTTPSRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, url):
        _https_url(url)
        return super().redirect_request(request, fp, code, message, headers, url)


def _download(package):
    request = Request(package['url'], headers={'User-Agent': 'skill-bench-results/1'})
    with build_opener(_HTTPSRedirect()).open(request, timeout=30) as response:
        _https_url(response.url)
        data = response.read(package['size'] + 1)
    return data


def _restore(data, entry, target):
    package = entry['package']
    if len(data) != package['size'] or hashlib.sha256(data).hexdigest() != package['sha256']:
        raise ValueError('Result package size or hash differs from the catalog')
    target.mkdir()
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members = archive.infolist()
            if not 1 <= len(members) <= MAX_MEMBERS or sum(item.file_size for item in members) > MAX_PACKAGE_BYTES:
                raise ValueError('Result package exceeds its expanded file or byte limit')
            names = set()
            for item in members:
                mode = item.external_attr >> 16
                if not MEMBER.fullmatch(item.filename) or item.filename in names or item.flag_bits & 1 or stat.S_IFMT(mode) not in (0, stat.S_IFREG) or item.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED) or item.file_size > MAX_JSON_BYTES:
                    raise ValueError('Result package contains a duplicate, linked, oversized or unsupported member')
                names.add(item.filename)
                with archive.open(item) as source:
                    content = source.read(MAX_JSON_BYTES + 1)
                if len(content) != item.file_size:
                    raise ValueError('Expanded result member differs from its declared size')
                path = target / item.filename
                path.parent.mkdir(exist_ok=True)
                path.write_bytes(content)
        _, raw = checked_file(target, 'report.json')
        report = json.loads(raw, object_pairs_hook=_unique_object)
        if report['report_fingerprint'] != entry['report_fingerprint'] or _summary(report) != entry['summary']:
            raise ValueError('Restored report differs from the catalog fingerprint or summary')
        (target / 'index.html').write_text(render_html(report), encoding='utf-8')
        return validate_public_bundle(target)
    except (zipfile.BadZipFile, EOFError, NotImplementedError) as error:
        raise ValueError('Invalid result ZIP package') from error


def fetch_results(catalog=DEFAULT_CATALOG, output=DEFAULT_REPORTS, *, archives=None):
    """Restore a new checked collection from HTTPS or an explicit offline ZIP folder."""
    value = load_catalog(catalog)
    target = _new_path(output)
    source = _ordinary_directory(archives) if archives is not None else None
    staging = Path(tempfile.mkdtemp(prefix='.results-', dir=target.parent))
    try:
        total = 0
        for entry in value['reports']:
            package = entry['package']
            if source is None:
                data = _download(package)
            else:
                filename = urlsplit(package['url']).path.rsplit('/', 1)[-1]
                _, data = checked_file(source, filename, max_bytes=MAX_PACKAGE_BYTES)
            proof = _restore(data, entry, staging / entry['path'])
            total += proof['bytes']
            if total > MAX_COLLECTION_BYTES:
                raise ValueError('Restored collection exceeds the aggregate byte limit')
        collection = {'schema_version': 2, 'suites': value['suites'],
                      'reports': [{key: entry[key] for key in ('id', 'title', 'path', 'suite_id')} for entry in value['reports']]}
        (staging / 'reports.json').write_text(json.dumps(collection, indent=2) + '\n', encoding='utf-8')
        proof = validate_collection(staging)
        if target.exists() or target.is_symlink():
            raise ValueError('Result destination appeared during restoration')
        staging.rename(target)
        return proof
    finally:
        shutil.rmtree(staging, ignore_errors=True)
