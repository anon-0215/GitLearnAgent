import unittest

from app.services.qa_agent import answer_question


class QaAgentTests(unittest.TestCase):
    def test_entry_question_returns_citation(self):
        bundle = {
            "analysis": {
                "modules": [{"name": "app"}],
                "start_commands": ["uvicorn app.main:app --reload"],
                "overview": "Demo project",
            },
            "files": [
                {
                    "path": "app/main.py",
                    "content": "from fastapi import FastAPI\napp = FastAPI()\n",
                    "summary": "入口文件",
                    "importance": 99,
                    "is_core": True,
                },
                {
                    "path": "README.md",
                    "content": "Run uvicorn app.main:app --reload",
                    "summary": "说明文档",
                    "importance": 100,
                    "is_core": True,
                },
            ],
        }
        result = answer_question("入口文件在哪", bundle)
        self.assertTrue(result["citations"])
        self.assertIn("app/main.py", {item["path"] for item in result["citations"]})


if __name__ == "__main__":
    unittest.main()

