#!/usr/bin/env python3
"""Fail when a built MkDocs site contains a broken internal link or asset."""

from __future__ import annotations

import argparse
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit


class SiteParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.references: list[tuple[str, str]] = []
        self.anchors: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if identifier := values.get("id"):
            self.anchors.add(identifier)
        if tag == "a" and values.get("href"):
            self.references.append(("link", str(values["href"])))
        elif tag in {"img", "script"} and values.get("src"):
            self.references.append(("asset", str(values["src"])))
        elif tag == "link" and values.get("href"):
            self.references.append(("asset", str(values["href"])))


def _page_url(site_root: Path, page: Path) -> str:
    relative = page.relative_to(site_root).as_posix()
    if relative == "index.html":
        return "https://docs.local/agentdiff/"
    if relative.endswith("/index.html"):
        return f"https://docs.local/agentdiff/{relative.removesuffix('index.html')}"
    return f"https://docs.local/agentdiff/{relative}"


def _target_path(site_root: Path, path: str) -> Path | None:
    prefix = "/agentdiff/"
    if path == "/agentdiff":
        path = prefix
    if not path.startswith(prefix):
        return None
    relative = unquote(path.removeprefix(prefix)).lstrip("/")
    candidate = site_root / relative
    if path.endswith("/"):
        return candidate / "index.html"
    if candidate.suffix:
        return candidate
    if candidate.is_file():
        return candidate
    return candidate / "index.html"


def check_site(site_root: Path) -> list[str]:
    pages = sorted(
        page
        for page in site_root.rglob("*.html")
        if "overrides" not in page.relative_to(site_root).parts
    )
    parsed: dict[Path, SiteParser] = {}
    for page in pages:
        parser = SiteParser()
        parser.feed(page.read_text(encoding="utf-8"))
        parsed[page.resolve()] = parser

    failures: list[str] = []
    for page in pages:
        page_url = _page_url(site_root, page)
        for kind, reference in parsed[page.resolve()].references:
            if reference.startswith(("data:", "javascript:", "mailto:", "tel:")):
                continue
            resolved = urlsplit(urljoin(page_url, reference))
            if resolved.netloc != "docs.local":
                continue
            target = _target_path(site_root, resolved.path)
            if target is None:
                continue
            target = target.resolve()
            if not target.is_file():
                failures.append(f"{page.relative_to(site_root)}: missing {kind} {reference}")
                continue
            if kind == "link" and resolved.fragment and target.suffix == ".html":
                target_parser = parsed.get(target)
                if (
                    target_parser is not None
                    and unquote(resolved.fragment) not in target_parser.anchors
                ):
                    failures.append(f"{page.relative_to(site_root)}: missing anchor {reference}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("site", type=Path, nargs="?", default=Path("site"))
    args = parser.parse_args()
    site_root = args.site.resolve(strict=True)
    failures = check_site(site_root)
    if failures:
        print("Built-site link validation failed:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"Built-site links valid across {len(list(site_root.rglob('*.html')))} pages.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
