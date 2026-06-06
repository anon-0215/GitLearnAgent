import unittest

from app.models import RepoFile, RepositorySnapshot
from app.services.analyzer import analyze_snapshot


class AnalyzerTests(unittest.TestCase):
    def test_python_fastapi_analysis(self):
        snapshot = RepositorySnapshot(
            repo_url="https://github.com/demo/sample",
            owner="demo",
            repo="sample",
            default_branch="main",
            files=[
                RepoFile("README.md", 40, "# Sample\nRun `uvicorn app.main:app --reload`"),
                RepoFile("requirements.txt", 20, "fastapi\nuvicorn\npytest\n"),
                RepoFile("app/main.py", 160, "from fastapi import FastAPI\napp = FastAPI()\n\n@app.get('/')\ndef home():\n    return {'ok': True}\n"),
                RepoFile("app/service.py", 80, "class Service:\n    def run(self):\n        return True\n"),
            ],
        )
        analysis = analyze_snapshot(snapshot)
        self.assertEqual(analysis["primary_language"], "Python")
        self.assertIn("FastAPI", analysis["frameworks"])
        self.assertGreaterEqual(analysis["stats"]["core_file_count"], 2)
        self.assertTrue(any(module["name"] == "app" for module in analysis["modules"]))

    def test_react_vite_analysis(self):
        snapshot = RepositorySnapshot(
            repo_url="https://github.com/demo/react-app",
            owner="demo",
            repo="react-app",
            default_branch="main",
            files=[
                RepoFile("package.json", 120, '{"scripts":{"dev":"vite"},"dependencies":{"@vitejs/plugin-react":"latest","react":"latest","vite":"latest"}}'),
                RepoFile("src/main.tsx", 120, "import React from 'react';\nimport { createRoot } from 'react-dom/client';\ncreateRoot(document.getElementById('root')!).render(<App />);"),
                RepoFile("src/App.tsx", 80, "export default function App(){ return <main>Hello</main> }"),
            ],
        )
        analysis = analyze_snapshot(snapshot)
        self.assertIn("React", analysis["frameworks"])
        self.assertIn("Vite", analysis["frameworks"])
        self.assertEqual(analysis["primary_language"], "TypeScript")


if __name__ == "__main__":
    unittest.main()

