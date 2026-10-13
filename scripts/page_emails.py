#!/usr/bin/env python3
"""Print the email addresses on a web page, with the text around each one.

Many race pages (OpenTrack included) hide addresses behind Cloudflare email
protection, so a normal fetch shows "[email protected]" instead of the address.
This decodes those as well as plain mailto: links.

  python3 scripts/page_emails.py URL

Standard library only.
"""
import html
import re
import sys
import urllib.request

CF_RE = re.compile(r'(?:data-cfemail="|/cdn-cgi/l/email-protection#)([0-9a-fA-F]+)')
MAILTO_RE = re.compile(r'mailto:([^"\'?<>\s]+@[^"\'?<>\s]+)')


def cf_decode(enc):
    key = int(enc[:2], 16)
    return "".join(chr(int(enc[i:i + 2], 16) ^ key) for i in range(2, len(enc), 2))


def page_emails(raw):
    """Return [(email, [context, ...])] for every distinct address on the page."""
    # Swap each protected address (and plain mailto link) for the real address
    # in place, so the surrounding text reads naturally.
    def swap(m):
        tag = m.group(0)
        enc = CF_RE.search(tag)
        if enc:
            return " " + cf_decode(enc.group(1)) + " "
        mailto = MAILTO_RE.search(tag)
        return " " + html.unescape(mailto.group(1)) + " " if mailto else tag

    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", raw, flags=re.S | re.I)
    text = re.sub(r"<a\b[^>]*>.*?</a>|<span\b[^>]*data-cfemail[^>]*>.*?</span>", swap, text, flags=re.S | re.I)
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    text = re.sub(r"\s+", " ", text)

    found = {}
    for m in re.finditer(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", text):
        mentions = found.setdefault(m.group(0).rstrip(".").lower(), [])
        if len(mentions) < 3:
            mentions.append(text[max(0, m.start() - 200):m.end() + 160].strip())
    return list(found.items())


def main(argv):
    if len(argv) != 2 or not argv[1].startswith(("http://", "https://")):
        print("usage: page_emails.py URL", file=sys.stderr)
        return 2
    req = urllib.request.Request(argv[1], headers={"User-Agent": "Mozilla/5.0 (Race Radar)"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8", "replace")
    results = page_emails(raw)
    if not results:
        print("No email addresses found.")
    for email, mentions in results:
        print(email)
        for context in mentions:
            print("  …" + context + "…")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
