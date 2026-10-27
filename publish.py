#!/usr/bin/env python3
"""Build a static blog from Google Docs in one Drive folder.

Required environment variables:
  GOOGLE_SERVICE_ACCOUNT_JSON  Service account JSON, supplied as a GitHub Actions secret.
  DRIVE_FOLDER_ID              ID of the Google Drive folder containing the posts.
Optional:
  SITE_URL                     Full published base URL, e.g. https://USER.github.io/REPO/
  GITHUB_REPOSITORY             owner/repository; used to create a fallback URL.
"""
from __future__ import annotations

import html
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import bleach
from bs4 import BeautifulSoup
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

ROOT = Path(__file__).resolve().parent
SITE = ROOT / "site"
POSTS = SITE / "posts"
MANIFEST_PATH = SITE / "_data" / "manifest.json"
DOC_MIME = "application/vnd.google-apps.document"
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

ALLOWED_TAGS = set(bleach.sanitizer.ALLOWED_TAGS) | {
    "h1", "h2", "h3", "h4", "p", "div", "span", "br", "hr",
    "img", "figure", "figcaption", "table", "thead", "tbody",
    "tr", "th", "td", "pre", "code", "sup", "sub",
}
ALLOWED_ATTRIBUTES = {
    "*": ["class"],
    "a": ["href", "title", "rel"],
    "img": ["src", "alt", "title", "width", "height"],
    "th": ["colspan", "rowspan"],
    "td": ["colspan", "rowspan"],
}
ALLOWED_PROTOCOLS = {"http", "https", "mailto", "data"}


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value[:65].strip("-") or "article"


def load_credentials():
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if not raw:
        fail("Missing GOOGLE_SERVICE_ACCOUNT_JSON GitHub secret.")
    try:
        info = json.loads(raw)
        return service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        fail(f"GOOGLE_SERVICE_ACCOUNT_JSON is not valid service-account JSON: {exc}")


def list_documents(drive, folder_id: str) -> list[dict]:
    documents = []
    page_token = None
    query = (
        f"'{folder_id}' in parents and trashed = false "
        f"and mimeType = '{DOC_MIME}'"
    )
    while True:
        response = drive.files().list(
            q=query,
            pageSize=1000,
            pageToken=page_token,
            orderBy="name",
            fields="nextPageToken,files(id,name,modifiedTime,webViewLink,mimeType)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        documents.extend(response.get("files", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    return documents


def export_html(drive, file_id: str) -> str:
    result = drive.files().export(fileId=file_id, mimeType="text/html").execute()
    if isinstance(result, bytes):
        return result.decode("utf-8", errors="replace")
    return str(result)


def extract_safe_body(raw_html: str) -> str:
    soup = BeautifulSoup(raw_html, "html.parser")
    for node in soup(["script", "style", "iframe", "object", "embed", "form", "input"]):
        node.decompose()
    body = soup.body or soup
    content = "".join(str(child) for child in body.contents).strip()
    cleaned = bleach.clean(
        content,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        strip=True,
    )
    return cleaned or "<p>This document has no publishable text content.</p>"


def read_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        return {}
    try:
        data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        fail("The existing manifest is unreadable. Fix site/_data/manifest.json before publishing.")


def page_html(title: str, body: str, doc_url: str, css_path: str, home_path: str, canonical: str = "") -> str:
    canonical_tag = f'<link rel="canonical" href="{html.escape(canonical, quote=True)}">' if canonical else ""
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <meta name="description" content="{html.escape(title, quote=True)}">
  {canonical_tag}
  <link rel="stylesheet" href="{css_path}">
</head>
<body>
  <header class="site-header">
    <a class="brand" href="{home_path}">Drive Blog</a>
    <a href="{html.escape(doc_url, quote=True)}" target="_blank" rel="noopener noreferrer">View source document</a>
  </header>
  <main class="article">
    <p class="eyebrow">ARTICLE</p>
    <h1>{html.escape(title)}</h1>
    <article>{body}</article>
    <p class="source-link"><a href="{html.escape(doc_url, quote=True)}" target="_blank" rel="noopener noreferrer">Open original Google Doc</a></p>
    <p><a href="{home_path}">← All articles</a></p>
  </main>
  <footer class="site-footer">Published from Google Docs</footer>
</body>
</html>
"""


def make_index(posts: list[dict], base_url: str) -> str:
    cards = []
    for post in posts:
        url = f"posts/{post['slug']}/"
        excerpt = post.get("excerpt") or "Read the full article."
        cards.append(
            '<article class="post-card">'
            f'<p class="eyebrow">ARTICLE</p><h2><a href="{html.escape(url, quote=True)}">'
            f'{html.escape(post["title"])}</a></h2>'
            f'<p>{html.escape(excerpt)}</p>'
            f'<a class="read-more" href="{html.escape(url, quote=True)}">Read article →</a>'
            '</article>'
        )
    listing = "\n".join(cards) or '<p>No articles have been published yet.</p>'
    canonical = f'<link rel="canonical" href="{html.escape(base_url, quote=True)}">' if base_url else ""
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Drive Blog — Articles</title>
  <meta name="description" content="Articles published from Google Docs.">
  {canonical}
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <header class="site-header"><a class="brand" href="./">Drive Blog</a><span>Articles from Google Docs</span></header>
  <main class="home">
    <section class="hero"><p class="eyebrow">THE BLOG</p><h1>Ideas, published simply.</h1>
    <p>Articles are published from a connected Google Drive folder.</p></section>
    <section class="post-list" aria-label="Published articles">{listing}</section>
  </main>
  <footer class="site-footer">Powered by Google Docs and GitHub Pages</footer>
</body>
</html>
"""


def make_sitemap(posts: list[dict], base_url: str) -> str:
    if not base_url:
        return ""
    urls = [base_url]
    urls.extend(urljoin(base_url, f"posts/{post['slug']}/") for post in posts)
    entries = "\n".join(f"  <url><loc>{html.escape(url)}</loc></url>" for url in urls)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + (
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{entries}\n</urlset>\n"
    )


def main() -> None:
    folder_id = os.environ.get("DRIVE_FOLDER_ID", "").strip()
    if not folder_id:
        fail("Missing DRIVE_FOLDER_ID secret.")
    base_url = os.environ.get("SITE_URL", "").strip()
    if base_url and not base_url.endswith("/"):
        base_url += "/"

    creds = load_credentials()
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)
    try:
        docs = list_documents(drive, folder_id)
    except HttpError as exc:
        fail(f"Could not list the Drive folder. Check the folder ID and service-account access. {exc}")

    SITE.mkdir(exist_ok=True)
    POSTS.mkdir(parents=True, exist_ok=True)
    (SITE / "_data").mkdir(parents=True, exist_ok=True)
    old_manifest = read_manifest()
    new_manifest = {}
    published = []

    for doc in docs:
        doc_id = doc["id"]
        title = doc.get("name", "Untitled")
        modified = doc.get("modifiedTime", "")
        old = old_manifest.get(doc_id, {})
        slug = old.get("slug") or f"{slugify(title)}-{doc_id[:7].lower()}"
        output_dir = POSTS / slug
        output_file = output_dir / "index.html"
        doc_url = doc.get("webViewLink") or f"https://docs.google.com/document/d/{doc_id}/edit"
        canonical = urljoin(base_url, f"posts/{slug}/") if base_url else ""

        if old.get("modifiedTime") == modified and output_file.exists() and old.get("title") == title:
            print(f"UNCHANGED: {title}")
            excerpt = old.get("excerpt", "")
        else:
            print(f"UPDATED: {title}")
            try:
                raw = export_html(drive, doc_id)
            except HttpError as exc:
                fail(f"Could not export '{title}'. Check its permissions. {exc}")
            body = extract_safe_body(raw)
            text_content = BeautifulSoup(body, "html.parser").get_text(" ", strip=True)
            excerpt = text_content[:180] + ("…" if len(text_content) > 180 else "")
            output_dir.mkdir(parents=True, exist_ok=True)
            output_file.write_text(
                page_html(title, body, doc_url, "../../styles.css", "../../", canonical),
                encoding="utf-8",
            )

        entry = {
            "title": title,
            "slug": slug,
            "modifiedTime": modified,
            "docUrl": doc_url,
            "excerpt": excerpt,
        }
        new_manifest[doc_id] = entry
        published.append(entry)

    # Remove only article folders tracked by the previous manifest and no longer present in Drive.
    deleted_ids = set(old_manifest) - set(new_manifest)
    for deleted_id in deleted_ids:
        old_slug = old_manifest[deleted_id].get("slug")
        if old_slug:
            stale_dir = POSTS / old_slug
            if stale_dir.exists():
                for path in sorted(stale_dir.rglob("*"), reverse=True):
                    if path.is_file() or path.is_symlink():
                        path.unlink()
                    elif path.is_dir():
                        path.rmdir()
                stale_dir.rmdir()
                print(f"REMOVED: stale article {old_slug}")

    published.sort(key=lambda item: item["title"].casefold())
    MANIFEST_PATH.write_text(json.dumps(new_manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (SITE / "index.html").write_text(make_index(published, base_url), encoding="utf-8")
    (SITE / "styles.css").write_text(STYLES, encoding="utf-8")
    (SITE / ".nojekyll").write_text("", encoding="utf-8")
    sitemap = make_sitemap(published, base_url)
    if sitemap:
        (SITE / "sitemap.xml").write_text(sitemap, encoding="utf-8")
    elif (SITE / "sitemap.xml").exists():
        (SITE / "sitemap.xml").unlink()
    print(f"Done. {len(published)} article(s) listed; unchanged articles were not re-exported.")


STYLES = r"""
:root{color-scheme:light;--ink:#172033;--muted:#667085;--line:#e5e7eb;--paper:#fff;--wash:#f6f7fb;--accent:#335cff}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.7 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
.site-header{display:flex;justify-content:space-between;align-items:center;gap:1rem;padding:1rem max(1.25rem,calc((100vw - 1040px)/2));border-bottom:1px solid var(--line);font-size:.92rem;color:var(--muted)}
.brand{font-size:1.05rem;font-weight:800;color:var(--ink)}
.home,.article{width:min(860px,calc(100% - 2rem));margin:0 auto}
.hero{padding:4.5rem 0 2.5rem}.hero h1{font-size:clamp(2.3rem,6vw,4rem);line-height:1.08;letter-spacing:-.04em;margin:.4rem 0 1rem}.hero>p:last-child{color:var(--muted);font-size:1.1rem}
.eyebrow{font-size:.75rem;letter-spacing:.14em;font-weight:800;color:var(--accent);text-transform:uppercase}
.post-list{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,290px),1fr));gap:1rem;padding:1rem 0 4rem}
.post-card{padding:1.4rem;border:1px solid var(--line);border-radius:1rem;background:#fff;box-shadow:0 6px 24px #17203308}
.post-card h2{font-size:1.35rem;line-height:1.3;margin:.25rem 0}.post-card p:not(.eyebrow){color:var(--muted)}
.read-more{font-weight:700}
.article{padding:3rem 0 4rem;max-width:760px}.article h1{font-size:clamp(2rem,5vw,3.2rem);line-height:1.15;letter-spacing:-.035em;margin:.4rem 0 2rem}
article{overflow-wrap:anywhere}article h2,article h3{line-height:1.3;margin-top:2rem}article img{max-width:100%;height:auto}article table{display:block;max-width:100%;overflow-x:auto;border-collapse:collapse}article th,article td{border:1px solid var(--line);padding:.5rem .7rem}article blockquote{border-left:3px solid var(--accent);padding-left:1rem;color:var(--muted)}article pre{overflow-x:auto;background:var(--wash);padding:1rem;border-radius:.6rem}
.source-link{margin-top:3rem;padding-top:1rem;border-top:1px solid var(--line)}
.site-footer{border-top:1px solid var(--line);padding:1.5rem;text-align:center;color:var(--muted);font-size:.85rem}
@media(max-width:520px){.site-header{align-items:flex-start;flex-direction:column;gap:.25rem}.hero{padding-top:3rem}}
"""

if __name__ == "__main__":
    main()
