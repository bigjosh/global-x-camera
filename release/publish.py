"""Publish an explicitly enabled request without replacing tags or assets.

No network calls or writes occur without --execute. Ordinary pushes do not
invoke this script. A retry may fill missing assets in a matching draft;
published releases must already match exactly, otherwise use a new tag.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import quote


class ReleaseError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise ReleaseError(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class Asset:
    path: Path
    name: str
    size: int
    sha256: str


@dataclass(frozen=True)
class Plan:
    tag: str
    title: str
    notes_path: Path
    notes: str
    prerelease: bool
    commit: str
    assets: tuple[Asset, ...]


def load_plan(root: Path, confirm_tag: str, commit: str) -> Plan:
    root = root.resolve()
    request = json.loads((root / 'release/request.json').read_text(encoding='utf-8'))
    require(request.get('publish') is True,
            'Release request is disabled; do not publish the historical package.')
    for key in ('tag', 'title', 'notes'):
        require(isinstance(request.get(key), str) and request[key].strip(),
                f'Missing or invalid request field: {key}')
    tag = request['tag']
    require(tag == confirm_tag, 'Typed tag does not match release/request.json.')
    require(not tag.startswith('-') and not any(c.isspace() for c in tag), 'Invalid tag.')
    require(isinstance(request.get('prerelease'), bool), 'prerelease must be a Boolean.')
    require(re.fullmatch(r'[0-9a-f]{40}', commit) is not None, 'Expected a full commit SHA.')
    head = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
    require(head == commit, 'Checked-out commit does not match the requested release commit.')

    def committed_file(name):
        require(isinstance(name, str) and name, 'Invalid release file path.')
        path = (root / name).resolve()
        require(path.is_relative_to(root) and path.is_file(), f'Missing or external file: {name}')
        relative = path.relative_to(root).as_posix()
        result = subprocess.run(['git', '-C', str(root), 'show', f'{commit}:{relative}'],
                                capture_output=True)
        require(result.returncode == 0 and result.stdout == path.read_bytes(),
                f'Release file differs from the checked-out commit: {relative}')
        return path

    # The enable flag, paths and metadata must themselves be committed.
    committed_file('release/request.json')
    notes = committed_file(request['notes'])
    names = request.get('assets')
    require(isinstance(names, list) and names, 'At least one release asset is required.')
    assets = []
    for name in names:
        path = committed_file(name)
        require('#' not in path.name, 'Asset names must not contain gh upload label syntax (#).')
        data = path.read_bytes()
        assets.append(Asset(path, path.name, len(data), sha256(data)))
    require(len({a.name for a in assets}) == len(assets), 'Duplicate release asset names.')
    return Plan(tag, request['title'], notes, notes.read_text(encoding='utf-8'),
                request['prerelease'], commit, tuple(assets))


class GitHub:
    """Small gh CLI adapter; only a genuine HTTP 404 means absent."""
    def __init__(self, repository: str):
        require(re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository) is not None,
                'Expected owner/repository.')
        self.repository = repository
        self.base = f'repos/{repository}'

    def api(self, route, *, missing=False, payload=None, binary=False):
        args = ['gh', 'api', self.base + route, '--include']
        if payload is not None:
            args += ['--method', 'POST', '--input', '-']
        if binary:
            args += ['-H', 'Accept: application/octet-stream']
        result = subprocess.run(args, input=None if payload is None else json.dumps(payload).encode(),
                                capture_output=True)
        # With --include gh emits the response headers even for HTTP errors.
        header, separator, body = result.stdout.partition(b'\r\n\r\n')
        if not separator:
            header, separator, body = result.stdout.partition(b'\n\n')
        match = re.match(rb'HTTP/\S+ (\d{3})\b', header)
        require(match is not None and separator, 'GitHub response has no verifiable HTTP status.')
        status = int(match[1])
        if status == 404 and missing:
            return None
        require(result.returncode == 0 and 200 <= status < 300,
                f'GitHub request failed (HTTP {status}); no publication retry was attempted.')
        return body if binary else json.loads(body)

    def tag_commit(self, tag):
        ref = self.api('/git/ref/tags/' + quote(tag, safe=''), missing=True)
        if ref is None:
            return None
        obj = ref['object']
        for _ in range(8):
            if obj['type'] == 'commit':
                return obj['sha']
            require(obj['type'] == 'tag', 'Release tag does not resolve to a commit.')
            obj = self.api('/git/tags/' + obj['sha'])['object']
        raise ReleaseError('Release tag nesting is too deep.')

    def create_tag(self, plan):
        self.api('/git/refs', payload={'ref': 'refs/tags/' + plan.tag, 'sha': plan.commit})

    def release(self, tag):
        release = self.api('/releases/tags/' + quote(tag, safe=''), missing=True)
        if release is not None:
            return release
        # The tag lookup may omit unpublished drafts. The authenticated list
        # includes them; find a partial draft before attempting another create.
        page = 1
        while True:
            releases = self.api(f'/releases?per_page=100&page={page}')
            require(isinstance(releases, list), 'Unexpected releases-list response.')
            matching = [r for r in releases if r['tag_name'] == tag]
            require(len(matching) <= 1, 'Several releases share the requested tag.')
            if matching:
                return matching[0]
            if len(releases) < 100:
                return None
            page += 1

    def create_draft(self, plan):
        # Uploads happen separately; a failed upload leaves an unpublished draft.
        self.api('/releases', payload={'tag_name': plan.tag, 'target_commitish': plan.commit,
                                      'name': plan.title, 'body': plan.notes,
                                      'prerelease': plan.prerelease, 'draft': True})

    def asset_bytes(self, asset):
        return self.api('/releases/assets/' + str(asset['id']), binary=True)

    def upload(self, tag, asset):
        # Deliberately no --clobber. A concurrent duplicate must fail closed.
        subprocess.run(['gh', 'release', 'upload', tag, str(asset.path),
                        '--repo', self.repository], check=True)

    def publish_draft(self, tag):
        # Only visibility changes: no edit to notes, metadata, tag or assets.
        subprocess.run(['gh', 'release', 'edit', tag, '--draft=false',
                        '--repo', self.repository], check=True)


def check_tag(github, plan):
    actual = github.tag_commit(plan.tag)
    require(actual == plan.commit,
            f'Tag {plan.tag} points to {actual}, not {plan.commit}; use a new tag.')


def inspect_release(github, plan, release):
    require(release is not None, 'Expected release is missing.')
    require(release['tag_name'] == plan.tag and release['name'] == plan.title and
            release.get('body', '') == plan.notes and release['prerelease'] == plan.prerelease,
            'Existing release metadata differs; no notes or assets will be replaced.')
    remote = release['assets']
    require(len({a['name'] for a in remote}) == len(remote), 'Duplicate remote asset names.')
    by_name = {a['name']: a for a in remote}
    require(set(by_name) <= {a.name for a in plan.assets}, 'Existing release has unexpected assets.')
    missing = []
    for expected in plan.assets:
        actual = by_name.get(expected.name)
        if actual is None:
            missing.append(expected)
            continue
        require(actual.get('state') == 'uploaded' and actual['size'] == expected.size,
                f'Existing asset is incomplete or differs: {expected.name}')
        # Read the actual bytes; older GitHub assets may lack a SHA-256 digest.
        data = github.asset_bytes(actual)
        require(len(data) == expected.size and sha256(data) == expected.sha256,
                f'Existing asset content differs: {expected.name}; never overwritten.')
    return missing


def publish(github, plan):
    actual = github.tag_commit(plan.tag)
    require(actual is None or actual == plan.commit,
            f'Existing tag {plan.tag} points to a different commit; use a new tag.')
    release = github.release(plan.tag)
    if release is not None:
        require(actual is not None, 'Existing release has no matching tag.')
        missing = inspect_release(github, plan, release)
        if not release['draft']:
            require(not missing, 'Published release is missing assets; it will not be modified.')
            return 'Existing published release matches; no changes made.'
    else:
        if actual is None:
            github.create_tag(plan)
        check_tag(github, plan)
        github.create_draft(plan)
        release = github.release(plan.tag)
        require(release is not None and release['draft'], 'Expected a new unpublished draft.')
        missing = inspect_release(github, plan, release)
    for asset in missing:
        check_tag(github, plan)
        require(sha256(asset.path.read_bytes()) == asset.sha256,
                f'Local asset changed during publication: {asset.name}')
        github.upload(plan.tag, asset)
    # A partial upload or moved tag can never be promoted to a published release.
    check_tag(github, plan)
    release = github.release(plan.tag)
    require(release is not None and release['draft'], 'Draft state changed during publication.')
    require(not inspect_release(github, plan, release), 'Draft still lacks required assets.')
    github.publish_draft(plan.tag)
    return 'Published verified draft; tag and asset contents preserved.'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--commit', required=True)
    parser.add_argument('--repository', required=True)
    parser.add_argument('--confirm-tag', required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    plan = load_plan(args.root, args.confirm_tag, args.commit)
    if args.execute:
        print(publish(GitHub(args.repository), plan))
    else:
        print(f'Validated {plan.tag} at {plan.commit}; no GitHub access without --execute.')


if __name__ == '__main__':
    main()
