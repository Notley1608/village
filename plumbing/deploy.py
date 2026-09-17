import os
import re
import sys

from core import db


def _markdown_to_html(text):
    lines = []
    in_list = False

    def close_list():
        nonlocal in_list
        if in_list:
            in_list = False
            return "</ul>"
        return ""

    for raw in (text or "").splitlines():
        line = raw.rstrip()
        if not line:
            lines.append(close_list())
            continue
        heading = re.match(r"^(#{1,3})\s+(.*)$", line)
        if heading:
            lines.append(close_list())
            level = len(heading.group(1)) + 1
            lines.append(f"<h{level}>{_inline(heading.group(2))}</h{level}>")
            continue
        bullet = re.match(r"^\s*-\s+(.*)$", line)
        if bullet:
            if not in_list:
                lines.append("<ul>")
                in_list = True
            lines.append(f"<li>{_inline(bullet.group(1))}</li>")
            continue
        numbered = re.match(r"^\s*\d+\.\s+(.*)$", line)
        if numbered:
            lines.append(close_list())
            lines.append(f"<p>{_inline(numbered.group(1))}</p>")
            continue
        lines.append(close_list())
        lines.append(f"<p>{_inline(line)}</p>")
    lines.append(close_list())
    return "\n".join(lines)


def _inline(text):
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    return text


def _slug_draft(draft):
    title = re.sub(r"^#+\s*", "", (draft["payload"] or "").splitlines()[0].strip())
    title = title.split(" (2026)")[0]
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    if not slug:
        slug = f"draft-{draft['id']}"
    if draft["kind"] == "money_page":
        return slug
    return "index" if draft["kind"] == "hub_page" else f"{slug}-{draft['id']}"


def _shell(site_name, title, body_html, canonical_url, href_base="."):
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{title} — researched and human-checked before publish.">
<meta name="robots" content="index,follow">
<link rel="canonical" href="{canonical_url}">
<style>
body{{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;max-width:760px;margin:0 auto;padding:24px;color:#1c2430;line-height:1.6}}
h1{{font-size:26px}}h2{{font-size:19px;margin-top:28px}}h3{{font-size:16px}}a{{color:#1d4ed8}}
ul{{padding-left:20px}}li{{margin:6px 0}}footer{{margin-top:40px;padding-top:14px;border-top:1px solid #e3e6ea;color:#7a8494;font-size:12px}}
</style>
</head>
<body>
{body_html}
<footer><a href="{href_base}/">← Back to the index</a> · {site_name}</footer>
</body>
</html>"""


def _embed_affiliate_links(payload, links):
    if not links:
        return payload
    pat = re.compile(r"^(\s*- \*\*([^*]+)\*\*[^\[]*)\[(.*?)\]\((.*?)\)(.*)$")
    out = []
    for line in payload.splitlines():
        m = pat.match(line)
        if m and links.get(m.group(2).strip()):
            out.append(f"{m.group(1)}[{m.group(3)}]({links[m.group(2).strip()]}){m.group(5)}")
        elif "linked externally" in line:
            out.append(line.replace("linked externally; links marked with our affiliate tag may earn us a commission",
                                    "linked externally; some links are affiliate links and may earn us a commission"))
        else:
            out.append(line)
    return "\n".join(out)


def build_site(conn, out_dir, site_name="Tooldeck", site_url="", resident_name="directory",
               affiliate_links=None):
    rid = conn.execute("SELECT id FROM residents WHERE name = ?", (resident_name,)).fetchone()
    drafts = conn.execute(
        "SELECT * FROM drafts WHERE status = 'published' "
        "AND (? IS NULL OR resident_id = ?) ORDER BY id",
        (rid["id"] if rid else None, rid["id"] if rid else None),
    ).fetchall()
    os.makedirs(out_dir, exist_ok=True)
    pages_dir = os.path.join(out_dir, "pages")
    os.makedirs(pages_dir, exist_ok=True)

    pages = []
    for draft in drafts:
        slug = _slug_draft(draft)
        payload = _embed_affiliate_links(draft["payload"], affiliate_links or {})
        title = re.sub(r"^#+\s*", "", payload.splitlines()[0].strip())
        body_html = _markdown_to_html(payload)
        url = f"{site_url}/pages/{slug}.html" if site_url else f"pages/{slug}.html"
        filename = "index.html" if slug == "index" else f"{pages_dir}/{slug}.html"
        with open(filename, "w") as f:
            f.write(_shell(site_name, f"{title} — {site_name}", body_html, url))
        pages.append((slug, title))

    hub = [p for p in pages if p[0] == "index"]
    rest = [p for p in pages if p[0] != "index"]
    if hub:
        pass
    elif rest:
        body = "<h1>AI & automation tools by use case</h1><ul>" + "".join(
            f'<li><a href="pages/{slug}.html">{title}</a></li>' for slug, title in rest
        ) + "</ul>"
        with open(os.path.join(out_dir, "index.html"), "w") as f:
            f.write(_shell(site_name, f"{site_name} — AI tools by use case", body, f"{site_url}/" if site_url else "."))
    else:
        with open(os.path.join(out_dir, "index.html"), "w") as f:
            f.write(_shell(site_name, f"{site_name} — coming soon", "<p>Coming soon.</p>", f"{site_url}/" if site_url else "."))

    sitemap_entries = [f"{site_url}/" if site_url else "."]
    for slug, title in pages:
        sitemap_entries.append(f"{site_url}/pages/{slug}.html" if site_url else f"pages/{slug}.html")
    with open(os.path.join(out_dir, "sitemap.xml"), "w") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')
        for loc in sitemap_entries:
            f.write(f"  <url><loc>{loc}</loc></url>\n")
        f.write("</urlset>\n")
    with open(os.path.join(out_dir, "robots.txt"), "w") as f:
        f.write("User-agent: *\nAllow: /\nSitemap: " + (f"{site_url}/sitemap.xml" if site_url else "sitemap.xml") + "\n")

    return [p for p in pages]


def write_verification_file(out_dir, token):
    os.makedirs(out_dir, exist_ok=True)
    filename = f"google{token}.html"
    path = os.path.join(out_dir, filename)
    body = f"google-site-verification: google{token}.html"
    with open(path, "w") as f:
        f.write(f"<!doctype html><html><head><title>verification</title></head><body>{body}</body></html>")
    return path


def deploy(resident_name: str = "directory", out_dir=None, site_url=""):
    from core import config as core_config

    cfg = core_config.load_config()
    site = None
    for r in cfg["residents"]:
        if r["name"] == resident_name:
            site = r.get("site", {})
    site_name = (site or {}).get("name", "Tooldeck")
    site_url = site_url or (site or {}).get("url", "")
    out_dir = out_dir or os.path.join(os.path.dirname(__file__), "..", "site")
    conn = db.connect()
    try:
        return build_site(
            conn, out_dir, site_name=site_name, site_url=site_url, resident_name=resident_name,
            affiliate_links=(site or {}).get("affiliate_links"),
        )
    finally:
        conn.close()


def main():
    args = sys.argv[1:]
    if args and args[0] == "verify":
        token = args[1] if len(args) > 1 else sys.exit("usage: python -m plumbing.deploy verify <token>")
        print(f"verification file: {write_verification_file('site', token)}")
        return
    out_dir = args[0] if args else "site"
    print(f"building site into {os.path.abspath(out_dir)}")
    pages = deploy(out_dir=out_dir)
    print(f"{len(pages)} page(s) built")


if __name__ == "__main__":
    main()