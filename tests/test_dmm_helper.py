import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import requests

from src.dmm.helper import helper_lock, windows_args
from src.dmm.session import DEFAULT_PROXY, DmmError, DmmSession, LoginRequired, OperationCancelled
from src.dmm.updater import GameFile, UpdatePlan, VerifiedUpdater, safe_path

SIGN = "CloudFront-Policy=test;CloudFront-Signature=test;CloudFront-Key-Pair-Id=test"
DOMAIN = "https://cdn-gameplayer.games.dmm.com"


class Response:
    def __init__(self, body, status=200, headers=None):
        self.body, self.status_code, self.headers = body, status, headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def iter_content(self, size):
        yield self.body


class DmmTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def plan(self, body=b"new", local="/game.bin", **extra):
        entry = {"local_path": local, "path": "/product/game.bin", "size": len(body),
                 "hash": hashlib.md5(body).hexdigest(), "check_hash_flg": True, **extra}
        return UpdatePlan.parse(self.root, DOMAIN, [entry], "test")

    def test_reject_escaping_and_special_paths(self):
        for name in ("../secret", "/../secret", "C:/secret", "//server/share", "x:stream",
                     "folder/../../escape", "NUL", "trailing. ", ".ok-gm-update/file", "file?", "file\0"):
            with self.subTest(name=name), self.assertRaises(DmmError):
                safe_path(self.root, name)
        self.assertEqual(safe_path(self.root, "/folder/game.bin"), (self.root / "folder" / "game.bin").resolve())

    def test_windows_arguments_preserve_quotes_without_shell(self):
        arguments = ['/viewer_id=example', '/open_id=two words', '/pf_access_token=a&b;$(x)']
        self.assertEqual(windows_args(subprocess.list2cmdline(arguments)), arguments)

    def test_dpapi_roundtrip_preserves_cookie_attributes(self):
        session = DmmSession(root=self.root)
        session.auth = {"accessToken": "secret-token"}
        session.http.cookies.set("login", "secret-cookie", domain=".dmm.com", path="/service",
                                 secure=True, rest={"HttpOnly": True})
        session.save()
        self.assertNotIn(b"secret-token", session.path.read_bytes())
        loaded = DmmSession(root=self.root)
        self.assertEqual(loaded.auth, session.auth)
        cookie = next(iter(loaded.http.cookies))
        self.assertEqual((cookie.domain, cookie.path, cookie.secure, cookie._rest),
                         (".dmm.com", "/service", True, {"HttpOnly": True}))
        self.assertFalse(loaded.http.trust_env)

    def test_check_honors_false_and_sends_token_in_body(self):
        session = DmmSession(root=self.root)
        session.auth = {"accessToken": "secret-token", "expiresInSeconds": 10}
        with patch.object(session, "request", return_value={"result": False}) as request:
            self.assertFalse(session.authenticated())
            self.assertEqual(request.call_args.args[1]["access_token"], "secret-token")

    def test_launch_response_rotated_auth_is_persisted(self):
        session = DmmSession(root=self.root)
        session.auth = {"accessToken": "old-token"}
        response = unittest.mock.Mock(status_code=200)
        response.json.return_value = {"result_code": 100, "data": {
            "execute_args": "sensitive-game-arguments",
            "access_token_info": {"access_token": "new-token", "expires_in_seconds": 600},
        }}
        with patch.object(session.http, "request", return_value=response):
            session.request('/v5/r2/launch/cl', {})
        loaded = DmmSession(root=self.root)
        self.assertEqual(loaded.auth, {"accessToken": "new-token", "expiresInSeconds": 600})
        self.assertNotIn(b"sensitive-game-arguments", loaded.path.read_bytes())

    def test_malformed_rotation_preserves_previous_auth(self):
        session = DmmSession(root=self.root)
        session.auth = {"accessToken": "old-token"}
        with self.assertRaises(DmmError):
            session.accept_auth({"access_token": "new-token", "expires_in_seconds": "unknown"})
        self.assertEqual(session.auth, {"accessToken": "old-token"})

    def test_interrupted_api_body_retries_using_next_node(self):
        from unittest.mock import Mock
        session = DmmSession(root=self.root)
        session.http.proxy_failover = Mock()
        response = Mock(status_code=200)
        response.json.return_value = {'result_code': 100, 'data': {'result': True}}
        with patch.object(session.http, 'request', side_effect=[requests.exceptions.ChunkedEncodingError(), response]) as request:
            self.assertEqual(session.request('/v5/auth/accesstoken/check'), {'result': True})
        self.assertEqual(request.call_count, 2)
        session.http.proxy_failover.assert_called_once()

    def test_lock_prevents_concurrent_operation(self):
        with helper_lock(self.root), self.assertRaises(DmmError):
            with helper_lock(self.root):
                pass

    def test_resume_valid_range_and_verify(self):
        updater = VerifiedUpdater(self.plan(b"abcdef"), DEFAULT_PROXY, SIGN)
        staged = safe_path(updater.staging, "/game.bin")
        staged.parent.mkdir(parents=True)
        staged.write_bytes(b"abc")
        with patch.object(updater.http, "get", return_value=Response(b"def", 206, {"Content-Range": "bytes 3-5/6"})) as get:
            self.assertEqual(updater.run(), 1)
            self.assertEqual(get.call_args.kwargs["headers"], {"Range": "bytes=3-"})
        self.assertEqual((self.root / "game.bin").read_bytes(), b"abcdef")
        self.assertNotIn("actauth", updater.http.headers)

    def test_ignored_range_restarts_without_duplicate_bytes(self):
        updater = VerifiedUpdater(self.plan(b"abcdef"), DEFAULT_PROXY, SIGN)
        staged = safe_path(updater.staging, "/game.bin")
        staged.parent.mkdir(parents=True)
        staged.write_bytes(b"abc")
        with patch.object(updater.http, "get", return_value=Response(b"abcdef")):
            updater.run()
        self.assertEqual((self.root / "game.bin").read_bytes(), b"abcdef")

    def test_stream_failure_switches_node_and_resumes_verified_download(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from src.dmm.xray import ProxyAddress
        pool = SimpleNamespace(nodes=[1, 2], failover=Mock(), cancel_check=lambda: None, success=Mock())
        proxy = ProxyAddress(DEFAULT_PROXY, pool)
        updater = VerifiedUpdater(self.plan(b'abcdef'), proxy, SIGN)

        class Interrupted(Response):
            def iter_content(self, size):
                yield b'abc'
                raise requests.ConnectionError('simulated node disconnect')

        with patch.object(updater.http, 'get', side_effect=[Interrupted(b''), Response(b'def', 206, {'Content-Range': 'bytes 3-5/6'})]) as get:
            updater.run()
        pool.failover.assert_called_once()
        self.assertEqual(get.call_args.kwargs['headers'], {'Range': 'bytes=3-'})
        self.assertEqual((self.root / 'game.bin').read_bytes(), b'abcdef')

    def test_corrupt_download_does_not_change_installed_file(self):
        original = self.root / "game.bin"
        original.write_bytes(b"old")
        updater = VerifiedUpdater(self.plan(), DEFAULT_PROXY, SIGN)
        with patch.object(updater.http, "get", return_value=Response(b"bad")), self.assertRaises(DmmError):
            updater.run()
        self.assertEqual(original.read_bytes(), b"old")

    def test_invalid_range_does_not_change_installed_file(self):
        original = self.root / "game.bin"
        original.write_bytes(b"old")
        updater = VerifiedUpdater(self.plan(b"abcdef"), DEFAULT_PROXY, SIGN)
        staged = safe_path(updater.staging, "/game.bin")
        staged.parent.mkdir(parents=True)
        staged.write_bytes(b"abc")
        with patch.object(updater.http, "get", return_value=Response(b"abc", 206, {"Content-Range": "bytes 0-2/6"})), self.assertRaises(DmmError):
            updater.run()
        self.assertEqual(original.read_bytes(), b"old")

    def test_commit_failure_rolls_back_original(self):
        original = self.root / "game.bin"
        original.write_bytes(b"old")
        updater = VerifiedUpdater(self.plan(), DEFAULT_PROXY, SIGN)
        real_replace = os.replace

        def replace(source, target):
            if Path(source).resolve() == (updater.staging / "game.bin").resolve():
                raise OSError("simulated locked file")
            return real_replace(source, target)

        with patch.object(updater.http, "get", return_value=Response(b"new")), patch("src.dmm.updater.os.replace", side_effect=replace):
            with self.assertRaises(OSError):
                updater.run()
        self.assertEqual(original.read_bytes(), b"old")

    def test_cancel_preserves_installed_file_and_resumes_partial_download(self):
        original = self.root / 'game.bin'
        original.write_bytes(b'old')
        cancelled = False

        def check_cancelled():
            if cancelled:
                raise OperationCancelled('cancelled')

        def progress(done, total):
            nonlocal cancelled
            cancelled = True

        response = Response(b'')
        response.iter_content = lambda size: iter((b'abc', b'def'))
        updater = VerifiedUpdater(self.plan(b'abcdef'), DEFAULT_PROXY, SIGN,
                                  cancel_check=check_cancelled, download_progress=progress)
        with patch.object(updater.http, 'get', return_value=response), self.assertRaises(OperationCancelled):
            updater.run()
        self.assertEqual(original.read_bytes(), b'old')
        self.assertEqual((updater.staging / 'game.bin').read_bytes(), b'abc')
        resumed = VerifiedUpdater(self.plan(b'abcdef'), DEFAULT_PROXY, SIGN)
        with patch.object(resumed.http, 'get', return_value=Response(b'def', 206, {'Content-Range': 'bytes 3-5/6'})):
            resumed.run()
        self.assertEqual(original.read_bytes(), b'abcdef')

    def test_recover_interrupted_commit(self):
        updater = VerifiedUpdater(self.plan(), DEFAULT_PROXY, SIGN)
        updater.backup.mkdir(parents=True)
        (updater.backup / "game.bin").write_bytes(b"old")
        (self.root / "game.bin").write_bytes(b"new")
        updater._journal_write({"state": "applying", "items": [{"local": "/game.bin", "existed": True}]})
        updater.recover()
        updater.recover()
        self.assertEqual((self.root / "game.bin").read_bytes(), b"old")

    def test_protected_installed_file_is_preserved(self):
        original = self.root / "game.bin"
        original.write_bytes(b"user configuration")
        self.assertEqual(self.plan(protected_flg=True).pending(), [])

    def test_protected_first_download_is_verified(self):
        updater = VerifiedUpdater(self.plan(protected_flg=True), DEFAULT_PROXY, SIGN)
        staged = safe_path(updater.staging, "/game.bin")
        staged.parent.mkdir(parents=True)
        staged.write_bytes(b"bad")
        with patch.object(updater.http, "get", return_value=Response(b"new")) as get:
            updater.run()
            get.assert_called_once()
        self.assertEqual((self.root / "game.bin").read_bytes(), b"new")


if __name__ == "__main__":
    unittest.main()
