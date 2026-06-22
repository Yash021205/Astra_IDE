"""Workspace files: write/read/list, path-traversal safety, git-url validation."""
import unittest

from app.services import workspace_files as wf


class TestWorkspaceFiles(unittest.TestCase):
    WS = 999999                            # test workspace id

    def setUp(self):
        wf.delete_workspace_files(self.WS)

    def tearDown(self):
        wf.delete_workspace_files(self.WS)

    def test_write_read_list(self):
        wf.write_file(self.WS, "src/main.py", "print('hi')")
        wf.write_file(self.WS, "README.md", "# repo")
        self.assertEqual(wf.read_file(self.WS, "src/main.py"), "print('hi')")
        paths = {e["path"] for e in wf.list_tree(self.WS)}
        self.assertIn("src/main.py", paths)
        self.assertIn("README.md", paths)
        self.assertIn("src", paths)        # dir entry

    def test_path_traversal_blocked(self):
        with self.assertRaises(ValueError):
            wf.write_file(self.WS, "../../etc/passwd", "x")
        with self.assertRaises(ValueError):
            wf.read_file(self.WS, "../../../secret")

    def test_git_url_validation(self):
        # allow-list regex: only public https github/gitlab/bitbucket repos
        self.assertFalse(wf._ALLOWED_GIT.match("file:///etc/passwd"))
        self.assertFalse(wf._ALLOWED_GIT.match("git@github.com:foo/bar.git"))
        self.assertFalse(wf._ALLOWED_GIT.match("https://evil.com/a/b"))
        self.assertTrue(wf._ALLOWED_GIT.match("https://github.com/octocat/Hello-World"))
        self.assertTrue(wf._ALLOWED_GIT.match("https://gitlab.com/foo/bar.git"))
        # the service rejects a bad scheme before any network call
        self.assertFalse(wf.import_repo(self.WS, "file:///etc/passwd").ok)

    def test_oversize_rejected(self):
        with self.assertRaises(ValueError):
            wf.write_file(self.WS, "big.bin", "x" * (wf.MAX_FILE_BYTES + 1))


if __name__ == "__main__":
    unittest.main(verbosity=2)
