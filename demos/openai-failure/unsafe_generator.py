"""Intentionally unsafe worker used by the rejection demo."""

from pathlib import Path

source_path = Path("src/app.py")
source = source_path.read_text(encoding="utf-8")
source = source.replace("client.chat.completions.create", "client.responses.create")
source = source.replace("messages=", "input=")
source = source.replace("response.choices[0].message.content", "response.output_text")
source_path.write_text(source, encoding="utf-8")

workflow = Path(".github/workflows/deploy.yml")
workflow.parent.mkdir(parents=True, exist_ok=True)
workflow.write_text("name: unsafe-deployment-change\n", encoding="utf-8")
