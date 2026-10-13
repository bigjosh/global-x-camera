"""Print document links from a public product page."""
from concurrent.futures import ThreadPoolExecutor
from html import unescape
import json
import re
import sys
from urllib.parse import urljoin
from fetch_datasheet import get_bytes

def inspect(url):
    try:
        body, resolved = get_bytes(url)
        links = re.findall(r'''href=["']([^"']+)''', body.decode("utf-8", errors="replace"))
        matches = [urljoin(resolved, unescape(link)) for link in links
                   if any(term in link.lower() for term in [".pdf", "datasheet", "document?", "specification"])]
        print(json.dumps({"page": url, "links": list(dict.fromkeys(matches))}, ensure_ascii=True))
    except Exception as exc:
        print(json.dumps({"page": url, "error": str(exc)}))

if __name__ == "__main__":
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(inspect, sys.argv[1:]))
