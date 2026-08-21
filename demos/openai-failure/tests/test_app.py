import unittest
from pathlib import Path


class MigrationContractTest(unittest.TestCase):
    def test_call_uses_responses(self) -> None:
        source = Path("src/app.py").read_text(encoding="utf-8")
        self.assertIn("client.responses.create", source)


if __name__ == "__main__":
    unittest.main()
