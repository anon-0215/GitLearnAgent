import unittest

from app.services.github_client import (
    is_interesting_text_file,
    parse_github_url,
    should_skip_path,
)


class GithubClientTests(unittest.TestCase):
    def test_parse_regular_url(self):
        self.assertEqual(parse_github_url("https://github.com/openai/codex"), ("openai", "codex"))

    def test_parse_git_suffix(self):
        self.assertEqual(parse_github_url("https://github.com/user/repo.git"), ("user", "repo"))

    def test_parse_invalid_url(self):
        with self.assertRaises(ValueError):
            parse_github_url("https://example.com/user/repo")

    def test_skip_dependency_dirs(self):
        self.assertTrue(should_skip_path("frontend/node_modules/react/index.js"))
        self.assertFalse(should_skip_path("src/main.py"))

    def test_interesting_files(self):
        self.assertTrue(is_interesting_text_file("package.json", 1000))
        self.assertTrue(is_interesting_text_file("src/app.tsx", 1000))
        self.assertFalse(is_interesting_text_file("dist/app.js", 1000))
        self.assertFalse(is_interesting_text_file("src/big.py", 500_000))


if __name__ == "__main__":
    unittest.main()

