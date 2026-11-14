"""Offline release publication regressions; never contact GitHub."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import publish as p


class FakeGitHub:
    def __init__(self, plan, *, tag=None, draft=None, assets=()):
        self.plan = plan
        self.tag = tag
        self.current = None if draft is None else self.record(draft)
        self.data = {}
        self.writes = []
        self.fail_upload = None
        self.move_tag_on_upload = False
        for asset in assets:
            self.add(asset)

    def record(self, draft):
        return dict(tag_name=self.plan.tag, name=self.plan.title, body=self.plan.notes,
                    prerelease=self.plan.prerelease, draft=draft, assets=[])

    def add(self, asset):
        ident = len(self.data) + 1
        self.data[ident] = asset.path.read_bytes()
        self.current['assets'].append(dict(id=ident, name=asset.name,
                                           size=asset.size, state='uploaded'))

    def tag_commit(self, tag):
        return self.tag

    def create_tag(self, plan):
        self.writes.append(('tag', plan.commit))
        self.tag = plan.commit

    def release(self, tag):
        return deepcopy(self.current)

    def create_draft(self, plan):
        self.writes.append(('draft', plan.tag))
        self.current = self.record(True)

    def asset_bytes(self, asset):
        return self.data[asset['id']]

    def upload(self, tag, asset):
        self.writes.append(('upload', asset.name))
        if asset.name == self.fail_upload:
            raise p.ReleaseError('Simulated interrupted upload')
        self.add(asset)
        if self.move_tag_on_upload:
            self.tag = 'b' * 40

    def publish_draft(self, tag):
        self.writes.append(('publish', tag))
        self.current['draft'] = False


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        assets = []
        for name, data in [('sector0.bin', b'primary'), ('sector1.bin', b'secondary')]:
            path = root / name
            path.write_bytes(data)
            assets.append(p.Asset(path, name, len(data), p.sha256(data)))
        self.plan = p.Plan('new-firmware', 'New firmware', root/'notes.md', 'Notes\n',
                           True, 'a' * 40, tuple(assets))

    def test_new_release_stays_draft_until_every_asset_verified(self):
        gh = FakeGitHub(self.plan)
        p.publish(gh, self.plan)
        self.assertEqual([w[0] for w in gh.writes], ['tag', 'draft', 'upload', 'upload', 'publish'])
        self.assertFalse(gh.current['draft'])

    def test_existing_tag_on_different_commit_stops_before_mutation(self):
        gh = FakeGitHub(self.plan, tag='b' * 40)
        with self.assertRaisesRegex(p.ReleaseError, 'different commit'):
            p.publish(gh, self.plan)
        self.assertEqual(gh.writes, [])

    def test_matching_published_release_is_noop(self):
        gh = FakeGitHub(self.plan, tag=self.plan.commit, draft=False, assets=self.plan.assets)
        self.assertIn('no changes', p.publish(gh, self.plan))
        self.assertEqual(gh.writes, [])

    def test_matching_partial_draft_uploads_only_missing_asset(self):
        gh = FakeGitHub(self.plan, tag=self.plan.commit, draft=True, assets=self.plan.assets[:1])
        p.publish(gh, self.plan)
        self.assertEqual(gh.writes, [('upload', 'sector1.bin'), ('publish', self.plan.tag)])

    def test_published_missing_asset_is_not_repaired(self):
        gh = FakeGitHub(self.plan, tag=self.plan.commit, draft=False, assets=self.plan.assets[:1])
        with self.assertRaisesRegex(p.ReleaseError, 'missing assets'):
            p.publish(gh, self.plan)
        self.assertEqual(gh.writes, [])

    def test_corrupt_equal_length_asset_is_never_overwritten(self):
        for draft in (False, True):
            with self.subTest(draft=draft):
                gh = FakeGitHub(self.plan, tag=self.plan.commit, draft=draft, assets=self.plan.assets)
                gh.data[1] = b'corrupt'
                with self.assertRaisesRegex(p.ReleaseError, 'content differs'):
                    p.publish(gh, self.plan)
                self.assertEqual(gh.writes, [])

    def test_incomplete_asset_metadata_changes_and_extra_assets_fail_closed(self):
        for kind in ('metadata', 'incomplete', 'extra'):
            with self.subTest(kind=kind):
                gh = FakeGitHub(self.plan, tag=self.plan.commit, draft=True, assets=self.plan.assets)
                if kind == 'metadata':
                    gh.current['body'] = 'different notes'
                elif kind == 'incomplete':
                    gh.current['assets'][0]['state'] = 'starter'
                else:
                    gh.current['assets'].append(dict(id=99, name='surprise.bin', size=1, state='uploaded'))
                with self.assertRaises(p.ReleaseError):
                    p.publish(gh, self.plan)
                self.assertEqual(gh.writes, [])

    def test_failed_upload_leaves_draft_and_retry_preserves_existing_asset(self):
        gh = FakeGitHub(self.plan)
        gh.fail_upload = 'sector1.bin'
        with self.assertRaisesRegex(p.ReleaseError, 'interrupted'):
            p.publish(gh, self.plan)
        self.assertTrue(gh.current['draft'])
        self.assertEqual([a['name'] for a in gh.current['assets']], ['sector0.bin'])
        gh.fail_upload = None
        gh.writes.clear()
        p.publish(gh, self.plan)
        self.assertEqual(gh.writes, [('upload', 'sector1.bin'), ('publish', self.plan.tag)])

    def test_tag_movement_mid_upload_never_publishes(self):
        gh = FakeGitHub(self.plan)
        gh.move_tag_on_upload = True
        with self.assertRaisesRegex(p.ReleaseError, 'points to'):
            p.publish(gh, self.plan)
        self.assertTrue(gh.current['draft'])
        self.assertNotIn('publish', [w[0] for w in gh.writes])

    def test_local_asset_mutation_is_not_uploaded(self):
        gh = FakeGitHub(self.plan, tag=self.plan.commit, draft=True)
        self.plan.assets[0].path.write_bytes(b'changed')
        with self.assertRaisesRegex(p.ReleaseError, 'Local asset changed'):
            p.publish(gh, self.plan)
        self.assertEqual(gh.writes, [])


class AdapterTests(unittest.TestCase):
    def test_only_http_404_is_missing(self):
        for code in (200, 401, 403, 404, 500):
            with self.subTest(code=code):
                result = subprocess.CompletedProcess([], 0 if code == 200 else 1,
                    f'HTTP/2.0 {code} Status\r\nContent-Type: application/json\r\n\r\n{{}}'.encode(), b'')
                with patch.object(p.subprocess, 'run', return_value=result):
                    if code == 404:
                        self.assertIsNone(p.GitHub('owner/repo').api('/releases/tags/tag', missing=True))
                    elif code == 200:
                        self.assertEqual(p.GitHub('owner/repo').release('tag'), {})
                    else:
                        with self.assertRaises(p.ReleaseError):
                            p.GitHub('owner/repo').release('tag')

    def test_network_failure_cannot_be_mistaken_for_missing_release(self):
        result = subprocess.CompletedProcess([], 1, b'', b'network failure')
        with patch.object(p.subprocess, 'run', return_value=result), self.assertRaises(p.ReleaseError):
            p.GitHub('owner/repo').release('tag')

    def test_annotated_tag_is_peeled(self):
        gh = p.GitHub('owner/repo')
        with patch.object(gh, 'api', side_effect=[{'object': {'type': 'tag', 'sha': 'a'*40}},
                                                {'object': {'type': 'commit', 'sha': 'b'*40}}]):
            self.assertEqual(gh.tag_commit('v1'), 'b'*40)

    def test_missing_tag_lookup_finds_existing_draft_without_creating(self):
        gh = p.GitHub('owner/repo')
        draft = {'tag_name': 'v1', 'draft': True}
        full_page = [{'tag_name': f'other-{i}'} for i in range(100)]
        with patch.object(gh, 'api', side_effect=[None, full_page, [draft]]) as api:
            self.assertEqual(gh.release('v1'), draft)
            self.assertEqual(api.call_args_list[-1].args[0], '/releases?per_page=100&page=2')

    def test_unfollowed_redirect_headers_fail_closed(self):
        response = b'HTTP/2.0 302 Found\r\nLocation: elsewhere\r\n\r\nHTTP/2.0 200 OK\r\n\r\n{}'
        result = subprocess.CompletedProcess([], 0, response, b'')
        with patch.object(p.subprocess, 'run', return_value=result), self.assertRaises(p.ReleaseError):
            p.GitHub('owner/repo').api('/releases/assets/1', binary=True)

    def test_upload_has_no_replace_flag_and_publish_changes_only_visibility(self):
        gh = p.GitHub('owner/repo')
        asset = p.Asset(Path('sector.bin'), 'sector.bin', 0, '')
        with patch.object(p.subprocess, 'run') as run:
            gh.upload('tag', asset)
            gh.publish_draft('tag')
        self.assertEqual(run.call_args_list[0].args[0],
                         ['gh', 'release', 'upload', 'tag', 'sector.bin', '--repo', 'owner/repo'])
        self.assertEqual(run.call_args_list[1].args[0],
                         ['gh', 'release', 'edit', 'tag', '--draft=false', '--repo', 'owner/repo'])


class RequestTests(unittest.TestCase):
    def test_historical_request_is_disabled_and_push_does_not_publish(self):
        root = Path(__file__).resolve().parents[1]
        with self.assertRaisesRegex(p.ReleaseError, 'disabled'):
            p.load_plan(root, 'knobs-2026-11-14', 'a'*40)
        workflow = (root/'.github/workflows/publish-release.yml').read_text()
        self.assertIn('  workflow_dispatch:', workflow)
        self.assertNotIn('  push:', workflow)
        self.assertNotIn('--clobber', workflow)
        self.assertIn('--confirm-tag "$RELEASE_TAG"', workflow)

    def test_request_checks_committed_bytes_and_tag_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'release').mkdir()
            (root/'notes.md').write_text('Notes\n')
            (root/'sector.bin').write_bytes(b'firmware')
            request = dict(publish=True, tag='v1', title='Firmware', notes='notes.md',
                           prerelease=True, assets=['sector.bin'])
            (root/'release/request.json').write_text(json.dumps(request))

            def show(args, **kwargs):
                relative = args[-1].split(':', 1)[1]
                return subprocess.CompletedProcess(args, 0, (root/relative).read_bytes(), b'')

            with patch.object(p.subprocess, 'check_output', return_value='a'*40), \
                    patch.object(p.subprocess, 'run', side_effect=show):
                self.assertEqual(p.load_plan(root, 'v1', 'a'*40).assets[0].sha256, p.sha256(b'firmware'))
                with self.assertRaisesRegex(p.ReleaseError, 'Typed tag'):
                    p.load_plan(root, 'wrong', 'a'*40)
            with patch.object(p.subprocess, 'check_output', return_value='a'*40), \
                    patch.object(p.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, b'wrong', b'')):
                with self.assertRaisesRegex(p.ReleaseError, 'differs from'):
                    p.load_plan(root, 'v1', 'a'*40)


if __name__ == '__main__':
    unittest.main()
