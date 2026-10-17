#!/usr/bin/env python3
"""Validate the static GameAITools site before deploying it.

Uses only the Python standard library so it runs on GitHub Actions without
installing dependencies.
"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent.parent
SITE_ORIGIN = "https://gameaitools.com"
SITEMAP_PATH = ROOT / "sitemap.xml"
ROBOTS_PATH = ROOT / "robots.txt"
BREADCRUMB_PAGES = {
    "ai-game-coding-tools.html", "ai-3d-game-assets.html",
    "ai-2d-game-art-tools.html", "ai-game-audio-tools.html",
    "ai-game-animation-tools.html", "ai-npc-tools-for-games.html",
    "ai-tools-for-indie-game-developers.html",
    "ai-3d-model-generators-for-games.html", "ai-npc-dialogue-tools.html",
}


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.in_title = False
        self.h1_count = 0
        self.descriptions: list[str] = []
        self.canonicals: list[str] = []
        self.favicons: list[str] = []
        self.open_graph: dict[str, list[str]] = {}
        self.twitter_cards: list[str] = []
        self.ids: list[str] = []
        self.links: list[str] = []
        self.jsonld_parts: list[list[str]] = []
        self.in_jsonld = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_map = dict(attrs)
        if tag == "title":
            self.in_title = True
        elif tag == "h1":
            self.h1_count += 1

        if attrs_map.get("id"):
            self.ids.append(attrs_map["id"])

        if tag == "meta":
            meta_name = (attrs_map.get("name") or "").lower()
            meta_property = (attrs_map.get("property") or "").lower()
            value = (attrs_map.get("content") or "").strip()
            if meta_name == "description" and value:
                self.descriptions.append(value)
            if meta_name == "twitter:card" and value:
                self.twitter_cards.append(value)
            if meta_property.startswith("og:") and value:
                self.open_graph.setdefault(meta_property, []).append(value)

        if tag == "link":
            rel = (attrs_map.get("rel") or "").lower().split()
            value = (attrs_map.get("href") or "").strip()
            if "canonical" in rel and value:
                self.canonicals.append(value)
            if "icon" in rel and value:
                self.favicons.append(value)

        for attr in ("href", "src"):
            value = attrs_map.get(attr)
            if value:
                self.links.append(value.strip())

        if tag == "script" and "ld+json" in (attrs_map.get("type") or "").lower():
            self.jsonld_parts.append([])
            self.in_jsonld = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False
        elif tag == "script" and self.in_jsonld:
            self.in_jsonld = False

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data)
        if self.in_jsonld and self.jsonld_parts:
            self.jsonld_parts[-1].append(data)

    @property
    def title(self) -> str:
        return "".join(self.title_parts).strip()


def main() -> int:
    errors: list[str] = []
    html_files = sorted(
        path for path in ROOT.rglob("*.html")
        if ".git" not in path.parts and "node_modules" not in path.parts
    )
    if not html_files:
        errors.append("No HTML pages found.")

    parsed: dict[Path, PageParser] = {}
    canonical_owners: dict[str, Path] = {}
    title_owners: dict[str, Path] = {}

    for path in html_files:
        relative = path.relative_to(ROOT)
        parser = PageParser()
        try:
            parser.feed(path.read_text(encoding="utf-8"))
            parser.close()
        except (OSError, UnicodeError) as exc:
            errors.append(f"{relative}: could not read or parse HTML: {exc}")
            continue
        parsed[path] = parser

        if not parser.title:
            errors.append(f"{relative}: missing <title>.")
        elif parser.title in title_owners:
            errors.append(
                f"{relative}: duplicate title also used by "
                f"{title_owners[parser.title].relative_to(ROOT)}."
            )
        else:
            title_owners[parser.title] = path

        if len(parser.descriptions) != 1:
            errors.append(
                f"{relative}: expected exactly one meta description, "
                f"found {len(parser.descriptions)}."
            )
        if len(parser.canonicals) != 1:
            errors.append(
                f"{relative}: expected exactly one canonical URL, "
                f"found {len(parser.canonicals)}."
            )
        else:
            canonical = parser.canonicals[0]
            expected_path = relative.as_posix()
            expected = SITE_ORIGIN + ("/" if expected_path == "index.html" else "/" + expected_path)
            if canonical != expected:
                errors.append(f"{relative}: canonical should be {expected!r}, got {canonical!r}.")
            if canonical in canonical_owners:
                errors.append(
                    f"{relative}: canonical duplicates {canonical_owners[canonical].relative_to(ROOT)}."
                )
            else:
                canonical_owners[canonical] = path

        if parser.h1_count != 1:
            errors.append(f"{relative}: expected exactly one H1, found {parser.h1_count}.")

        if not parser.favicons:
            errors.append(f"{relative}: missing favicon link.")
        for property_name in ("og:title", "og:description", "og:url", "og:site_name"):
            if len(parser.open_graph.get(property_name, [])) != 1:
                errors.append(
                    f"{relative}: expected exactly one Open Graph {property_name} value, "
                    f"found {len(parser.open_graph.get(property_name, []))}."
                )
        if parser.open_graph.get("og:title") and parser.open_graph["og:title"][0] != parser.title:
            errors.append(f"{relative}: og:title should match the page title.")
        if parser.open_graph.get("og:description") and parser.descriptions and parser.open_graph["og:description"][0] != parser.descriptions[0]:
            errors.append(f"{relative}: og:description should match the meta description.")
        if len(parser.twitter_cards) != 1 or parser.twitter_cards[0] != "summary":
            errors.append(f"{relative}: expected exactly one twitter:card set to 'summary'.")

        duplicate_ids = sorted(value for value, count in Counter(parser.ids).items() if count > 1)
        if duplicate_ids:
            errors.append(f"{relative}: duplicate HTML IDs: {', '.join(duplicate_ids)}.")

        for index, raw_json in enumerate(parser.jsonld_parts, start=1):
            try:
                json.loads("".join(raw_json).strip())
            except json.JSONDecodeError as exc:
                errors.append(f"{relative}: JSON-LD block {index} is invalid: {exc}.")

    # Editorial pages use semantic visible breadcrumbs and matching BreadcrumbList data.
    for source, parser in parsed.items():
        relative = source.relative_to(ROOT).as_posix()
        if relative not in BREADCRUMB_PAGES:
            continue
        html = source.read_text(encoding="utf-8")
        nav_match = re.search(
            r'<nav class="breadcrumbs" aria-label="Breadcrumb">(.*?)</nav>',
            html,
            flags=re.DOTALL,
        )
        if nav_match is None:
            errors.append(f"{relative}: missing accessible breadcrumb navigation.")
            breadcrumb_html = ""
        else:
            breadcrumb_html = nav_match.group(1)
        if len(re.findall(r"<li(?:\s|>)", breadcrumb_html)) != 3:
            errors.append(f"{relative}: breadcrumb navigation must contain exactly three list items.")
        if '<li aria-current="page">' not in breadcrumb_html:
            errors.append(f"{relative}: current breadcrumb must identify the current page.")
        breadcrumb_blocks = []
        for raw_json in parser.jsonld_parts:
            try:
                data = json.loads("".join(raw_json).strip())
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict) and data.get("@type") == "BreadcrumbList":
                breadcrumb_blocks.append(data)
        if len(breadcrumb_blocks) != 1:
            errors.append(f"{relative}: expected exactly one BreadcrumbList JSON-LD block, found {len(breadcrumb_blocks)}.")
        else:
            items = breadcrumb_blocks[0].get("itemListElement", [])
            if len(items) != 3:
                errors.append(f"{relative}: BreadcrumbList must contain exactly three items.")
            else:
                expected_items = [
                    (1, "Home", SITE_ORIGIN + "/"),
                    (2, "Categories" if relative in {
                        "ai-game-coding-tools.html", "ai-3d-game-assets.html",
                        "ai-2d-game-art-tools.html", "ai-game-audio-tools.html",
                        "ai-game-animation-tools.html", "ai-npc-tools-for-games.html",
                    } else "Guides",
                     SITE_ORIGIN + ("/#categories" if relative in {
                        "ai-game-coding-tools.html", "ai-3d-game-assets.html",
                        "ai-2d-game-art-tools.html", "ai-game-audio-tools.html",
                        "ai-game-animation-tools.html", "ai-npc-tools-for-games.html",
                     } else "/#guides")),
                    (3, None, SITE_ORIGIN + ("/" + relative)),
                ]
                for item, (position, name, url) in zip(items, expected_items):
                    if item.get("@type") != "ListItem" or item.get("position") != position:
                        errors.append(f"{relative}: BreadcrumbList item {position} has an invalid type or position.")
                    if name is not None and item.get("name") != name:
                        errors.append(f"{relative}: BreadcrumbList item {position} should be named {name!r}.")
                    if item.get("item") != url:
                        errors.append(f"{relative}: BreadcrumbList item {position} should link to {url!r}.")

    # Resolve local links and fragments against the repository files.
    for source, parser in parsed.items():
        relative_source = source.relative_to(ROOT)
        for raw_link in parser.links:
            if raw_link.startswith("//"):
                continue
            parsed_url = urlsplit(raw_link)
            if parsed_url.scheme.lower() in {"http", "https", "mailto", "tel", "data", "javascript"}:
                continue
            if parsed_url.netloc:
                continue

            if parsed_url.path:
                if parsed_url.path.startswith("/"):
                    target = ROOT / unquote(parsed_url.path.lstrip("/"))
                else:
                    target = source.parent / unquote(parsed_url.path)
                if target.is_dir():
                    target = target / "index.html"
                target = target.resolve()
                try:
                    target.relative_to(ROOT.resolve())
                except ValueError:
                    errors.append(f"{relative_source}: local link escapes the site root: {raw_link!r}.")
                    continue
            else:
                target = source

            if not target.is_file():
                errors.append(f"{relative_source}: broken local link or asset {raw_link!r}.")
                continue

            fragment = unquote(parsed_url.fragment)
            if fragment and target.suffix.lower() == ".html":
                target_parser = parsed.get(target)
                if target_parser is None:
                    target_parser = PageParser()
                    try:
                        target_parser.feed(target.read_text(encoding="utf-8"))
                        target_parser.close()
                    except (OSError, UnicodeError) as exc:
                        errors.append(f"{relative_source}: cannot inspect link target {raw_link!r}: {exc}.")
                        continue
                    parsed[target] = target_parser
                if fragment not in target_parser.ids:
                    errors.append(f"{relative_source}: missing anchor in {raw_link!r}.")

    # Ensure sitemap entries correspond to real pages and include every HTML page.
    if not SITEMAP_PATH.is_file():
        errors.append("Missing sitemap.xml.")
    else:
        try:
            root = ET.parse(SITEMAP_PATH).getroot()
            locations = [
                element.text.strip()
                for element in root.iter()
                if element.tag.rsplit("}", 1)[-1] == "loc" and element.text and element.text.strip()
            ]
            if len(locations) != len(set(locations)):
                errors.append("sitemap.xml contains duplicate URLs.")
            listed_pages: set[Path] = set()
            for location in locations:
                url = urlsplit(location)
                if url.scheme != "https" or url.netloc != "gameaitools.com":
                    errors.append(f"sitemap.xml contains a non-canonical host or scheme: {location!r}.")
                    continue
                relative_path = unquote(url.path.lstrip("/")) or "index.html"
                target = (ROOT / relative_path).resolve()
                if target.is_dir():
                    target = target / "index.html"
                if not target.is_file():
                    errors.append(f"sitemap.xml URL does not map to a file: {location!r}.")
                elif target.suffix.lower() == ".html":
                    listed_pages.add(target)
            # GitHub Pages uses 404.html as an error response, not a search landing page.
            # Keep it out of the sitemap while validating its metadata and local links above.
            not_sitemap_pages = {(ROOT / "404.html").resolve()}
            if any(urlsplit(location).path.rstrip("/") == "/404.html" for location in locations):
                errors.append("404.html must not be included in sitemap.xml.")
            for path in html_files:
                if path.resolve() not in listed_pages and path.resolve() not in not_sitemap_pages:
                    errors.append(f"{path.relative_to(ROOT)}: HTML page missing from sitemap.xml.")
        except (ET.ParseError, OSError) as exc:
            errors.append(f"Could not parse sitemap.xml: {exc}.")

    if not ROBOTS_PATH.is_file():
        errors.append("Missing robots.txt.")
    elif "https://gameaitools.com/sitemap.xml" not in ROBOTS_PATH.read_text(encoding="utf-8"):
        errors.append("robots.txt does not reference the canonical sitemap URL.")

    if errors:
        print(f"Site validation failed with {len(errors)} issue(s):")
        for error in errors:
            print(f" - {error}")
        return 1

    print(
        f"Site validation passed: {len(html_files)} HTML pages, "
        "unique titles/canonicals, metadata, H1s, JSON-LD, local links, "
        "anchors, assets, sitemap, and robots.txt."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
