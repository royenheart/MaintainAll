"""Read explicitly selected local Git commits without executing skill content."""
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile


def _git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], timeout=30)


def _commit(repo, ref):
    if not isinstance(ref, str) or not ref or ref.startswith('-') or any(ord(c) < 32 for c in ref):
        raise ValueError('Commit reference must be a local Git revision, not an option')
    sha = _git(repo, 'rev-parse', '--verify', '--end-of-options', ref + '^{commit}').decode().strip()
    if not re.fullmatch('[0-9a-f]{40}', sha):
        raise ValueError('Only SHA-1 Git commit identities are supported')
    return sha


@contextmanager
def committed_skills(repo, previous_ref, candidate_ref, *, skill_path='skills/art-creation'):
    """Yield exact committed bytes and sealable local provenance; never fetch."""
    relative = PurePosixPath(skill_path)
    if relative.is_absolute() or not relative.parts or any(p in ('.', '..') for p in relative.parts) or '\\' in skill_path or skill_path.startswith('-'):
        raise ValueError('Skill path must be an ordinary repository-relative directory')
    previous, candidate = _commit(repo, previous_ref), _commit(repo, candidate_ref)
    epoch, *parents = _git(repo, 'show', '-s', '--format=%ct %P', candidate).decode().strip().split()
    provenance = {'source': 'local-manual', 'candidate_sha': candidate,
        'previous_sha': previous, 'candidate_committed_epoch': int(epoch),
        'previous_committed_epoch': int(_git(repo, 'show', '-s', '--format=%ct', previous).decode().strip()),
        'candidate_parents': parents, 'protocol_id': 'manual-paired-v1'}
    with tempfile.TemporaryDirectory(prefix='skill-commit-inputs-') as directory:
        sources = {}
        for arm, sha in (('previous', previous), ('candidate', candidate)):
            destination = Path(directory) / arm
            listing = _git(repo, 'ls-tree', '-rz', sha, '--', skill_path)
            total, count = 0, 0
            for raw in listing.split(b'\0'):
                if not raw:
                    continue
                count += 1
                if count > 4096:
                    raise ValueError('Committed skill exceeds the file-count ceiling')
                metadata, name = raw.split(b'\t', 1)
                mode, kind, oid = metadata.split()
                rel = PurePosixPath(name.decode()).relative_to(relative)
                if kind != b'blob' or mode not in (b'100644', b'100755') or '..' in rel.parts:
                    raise ValueError('Committed skill contains a link or unsupported tree entry')
                data = _git(repo, 'cat-file', 'blob', oid.decode())
                total += len(data)
                if len(data) > 8 * 1024 * 1024 or total > 64 * 1024 * 1024:
                    raise ValueError('Committed skill exceeds the snapshot byte ceiling')
                target = destination / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            if not (destination / 'SKILL.md').is_file():
                raise ValueError('Selected commit has no SKILL.md at the requested path')
            sources[arm] = destination
        yield sources, provenance
