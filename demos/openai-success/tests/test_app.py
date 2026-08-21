import unittest
from pathlib import Path


class MigrationContractTest(unittest.TestCase):
    def test_supported_call_shape_was_migrated(self) -> None:
        source = Path("src/app.py").read_text(encoding="utf-8")
        self.assertIn("client.responses.create", source)
        self.assertIn("input=", source)
        self.assertIn("max_output_tokens=120", source)
        self.assertIn("response.output_text", source)
        self.assertNotIn("chat.completions.create", source)


if __name__ == "__main__":
    unittest.main()
