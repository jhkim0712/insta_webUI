"""RSS 2.0 feed builder with inline media (content:encoded) and Media RSS tags."""
import html
import mimetypes
from datetime import datetime
from email.utils import format_datetime
from urllib.parse import quote
from xml.sax.saxutils import escape

from .config import DOWNLOADS_ROOT

NS = ('xmlns:content="http://purl.org/rss/1.0/modules/content/" '
      'xmlns:media="http://search.yahoo.com/mrss/" '
      'xmlns:atom="http://www.w3.org/2005/Atom"')


def media_url(base_url: str, rel_path: str) -> str:
    return f"{base_url}/media/{quote(rel_path)}"


def _size(rel_path: str) -> int:
    try:
        return (DOWNLOADS_ROOT / rel_path).stat().st_size
    except OSError:
        return 0


def _cdata(text: str) -> str:
    return "<![CDATA[" + text.replace("]]>", "]]]]><![CDATA[>") + "]]>"


def _title(post: dict) -> str:
    first_line = (post.get("caption") or "").strip().splitlines()
    text = first_line[0] if first_line else ""
    if len(text) > 80:
        text = text[:80] + "…"
    return f"@{post.get('owner') or post['target_name']}: {text}" if text else f"@{post.get('owner')} ({post['shortcode']})"


def _html_body(post: dict, base_url: str) -> str:
    parts = []
    for m in post["media"]:
        src = media_url(base_url, m["path"])
        if m["type"] == "video":
            poster = f' poster="{media_url(base_url, m["poster"])}"' if m.get("poster") else ""
            parts.append(f'<p><video controls preload="none" src="{src}"{poster} style="max-width:100%"></video></p>')
            if m.get("poster"):
                # Many readers strip <video>; the linked thumbnail keeps something visible.
                parts.append(f'<p><a href="{src}"><img src="{media_url(base_url, m["poster"])}" alt="video" style="max-width:100%"/></a></p>')
        else:
            parts.append(f'<p><img src="{src}" alt="" style="max-width:100%"/></p>')
    caption = html.escape(post.get("caption") or "").replace("\n", "<br/>")
    if caption:
        parts.append(f"<p>{caption}</p>")
    parts.append(f'<p><a href="https://www.instagram.com/p/{post["shortcode"]}/">Instagram에서 보기</a></p>')
    return "\n".join(parts)


def build_feed(posts: list[dict], base_url: str, title: str, self_url: str, description: str) -> str:
    now = format_datetime(datetime.now().astimezone())
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f"<rss version=\"2.0\" {NS}>",
        "<channel>",
        f"<title>{escape(title)}</title>",
        f"<link>{escape(base_url)}/</link>",
        f"<description>{escape(description)}</description>",
        f'<atom:link href="{escape(self_url)}" rel="self" type="application/rss+xml"/>',
        f"<lastBuildDate>{now}</lastBuildDate>",
        "<generator>insta-webui</generator>",
    ]
    for p in posts:
        link = f"https://www.instagram.com/p/{p['shortcode']}/"
        pub = format_datetime(datetime.fromisoformat(p["date_utc"]))
        out += [
            "<item>",
            f"<title>{escape(_title(p))}</title>",
            f"<link>{link}</link>",
            f'<guid isPermaLink="true">{link}</guid>',
            f"<pubDate>{pub}</pubDate>",
            f"<author>{escape(p.get('owner') or '')}@instagram.com ({escape(p.get('owner') or '')})</author>",
            f"<category>{escape(p['target_type'])}:{escape(p['target_name'])}</category>",
            f"<description>{_cdata(_html_body(p, base_url))}</description>",
            f"<content:encoded>{_cdata(_html_body(p, base_url))}</content:encoded>",
        ]
        if p["media"]:
            first = p["media"][0]
            thumb = first.get("poster") if first["type"] == "video" else first["path"]
            enc = first["path"]
            mime = mimetypes.guess_type(enc)[0] or "application/octet-stream"
            out.append(f'<enclosure url="{escape(media_url(base_url, enc))}" type="{mime}" length="{_size(enc)}"/>')
            if thumb:
                out.append(f'<media:thumbnail url="{escape(media_url(base_url, thumb))}"/>')
            for m in p["media"]:
                mt = "video" if m["type"] == "video" else "image"
                mm = mimetypes.guess_type(m["path"])[0] or ""
                out.append(f'<media:content url="{escape(media_url(base_url, m["path"]))}" medium="{mt}" type="{mm}"/>')
        out.append("</item>")
    out += ["</channel>", "</rss>"]
    return "\n".join(out)
