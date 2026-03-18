#!/usr/bin/env python3
"""
URLSFETCHER - URL Enumeration & Crawling Tool
Author: hkmj
"""

import argparse
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup
from colorama import Fore, Style, init


init(autoreset=True)
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# - Silence thread exception noise on Ctrl+C -
threading.excepthook = lambda _args: None

# - Global shutdown flag — set on Ctrl+C -
_SHUTDOWN = threading.Event()

# -----------------------
# Config
# -----------------------
TIMEOUT         = 12
MAX_RETRIES     = 3
MAX_CRAWL_PAGES = 40
MAX_WORKERS     = 10

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

JUNK_SCHEMES = {"mailto", "javascript", "data", "tel", "ftp", "irc", "about", "void"}


# -----------------------
# Safe printing — never crashes on any terminal encoding
# -----------------------
def safe_print(msg: str):
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("utf-8", errors="replace").decode("ascii", errors="replace"))


def info(msg):  safe_print(f"{Fore.GREEN}[+]{Style.RESET_ALL} {msg}")
def warn(msg):  safe_print(f"{Fore.YELLOW}[!]{Style.RESET_ALL} {msg}")
def error(msg): safe_print(f"{Fore.RED}[-]{Style.RESET_ALL} {msg}")
def found(url): safe_print(f"  {Fore.CYAN}>{Style.RESET_ALL} {url}")


# -----------------------
# Banner — flushed immediately so it shows before sleep
# -----------------------
def print_banner():
    lines = [
        "",
        f"{Fore.CYAN}{Style.BRIGHT}",
        " ██╗   ██╗██████╗ ██╗       ███████╗███████╗████████╗ ██████╗██╗  ██╗███████╗██████╗",
        " ██║   ██║██╔══██╗██║       ██╔════╝██╔════╝╚══██╔══╝██╔════╝██║  ██║██╔════╝██╔══██╗",
        " ██║   ██║██████╔╝██║       █████╗  █████╗     ██║   ██║     ███████║█████╗  ██████╔╝",
        " ██║   ██║██╔══██╗██║       ██╔══╝  ██╔══╝     ██║   ██║     ██╔══██║██╔══╝  ██╔══██╗",
        " ╚██████╔╝██║  ██║███████╗S ██║     ███████╗   ██║   ╚██████╗██║  ██║███████╗██║  ██║",
        "  ╚═════╝ ╚═╝  ╚═╝╚══════╝  ╚═╝     ╚══════╝   ╚═╝    ╚═════╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝",
        f"{Style.RESET_ALL}",
        f"{Fore.YELLOW}  URL Enumeration & Crawling Tool  {Fore.MAGENTA}| Author: hkmj{Style.RESET_ALL}",
        f"{Fore.WHITE}  Sources: Wayback Machine · Common Crawl · Subdomain Crawl · JS Endpoints{Style.RESET_ALL}",
        "-" * 80,
        "",
    ]
    for line in lines:
        safe_print(line)
    sys.stdout.flush()   # force terminal to render banner immediately
    time.sleep(2)        


# -----------------------
# HTTP helpers
# -----------------------
def decode_response(resp: requests.Response) -> str:
    """
    Safely decode HTTP response to str.
    Tries declared charset -> utf-8 -> latin-1.
    NEVER raises charmap / UnicodeDecodeError.
    """
    for enc in [resp.encoding, "utf-8", "utf-8-sig", "latin-1"]:
        if not enc:
            continue
        try:
            return resp.content.decode(enc, errors="replace")
        except (LookupError, UnicodeDecodeError):
            continue
    return resp.content.decode("latin-1", errors="replace")


def fetch(url: str, retries: int = MAX_RETRIES,
          timeout: int = TIMEOUT) -> requests.Response:
    """
    GET with:
      - retry (exponential backoff)
      - SSL fallback  (verify=True first, then verify=False for .gov.in etc)
      - _SHUTDOWN check so Ctrl+C aborts mid-retry
    """
    last_exc = None
    for attempt in range(1, retries + 1):
        if _SHUTDOWN.is_set():
            raise RuntimeError("Shutdown requested")
        for verify_ssl in (True, False):
            try:
                resp = requests.get(
                    url,
                    headers=HEADERS,
                    timeout=timeout,
                    allow_redirects=True,
                    verify=verify_ssl,
                )
                resp.raise_for_status()
                return resp
            except requests.exceptions.SSLError:
                if verify_ssl:
                    continue          # try again without SSL
                last_exc = requests.exceptions.SSLError(f"SSL error: {url}")
                break
            except requests.RequestException as exc:
                last_exc = exc
                break

        if attempt < retries and not _SHUTDOWN.is_set():
            time.sleep(0.6 * attempt)

    raise last_exc or RuntimeError(f"Failed to fetch: {url}")


def resolve_base_url(domain: str) -> str:
    """Try https then http; follow redirects; return final landing URL."""
    for scheme in ("https", "http"):
        url = f"{scheme}://{domain}"
        try:
            resp = requests.get(
                url, headers=HEADERS, timeout=TIMEOUT,
                allow_redirects=True, verify=False,
            )
            return resp.url.rstrip("/")
        except requests.RequestException:
            continue
    return f"https://{domain}"


# -----------------------
# URL utilities
# -----------------------
def is_valid_url(url: str) -> bool:
    if not url or not isinstance(url, str):
        return False
    url = url.strip()
    try:
        parsed = urlparse(url)
        if parsed.scheme in JUNK_SCHEMES:
            return False
        if parsed.scheme not in ("http", "https", ""):
            return False
        if not parsed.netloc and not parsed.path:
            return False
        if not parsed.netloc and "/" not in parsed.path:
            return False
        return True
    except Exception:
        return False


def normalize(url: str) -> str:
    """Lowercase scheme+host, drop fragment, strip trailing slash."""
    try:
        url = url.strip()
        p = urlparse(url)
        path = p.path.rstrip("/") or "/"
        return urlunparse((
            p.scheme.lower(),
            p.netloc.lower(),
            path,
            p.params,
            p.query,
            "",
        ))
    except Exception:
        return url


def same_domain(url: str, root_domain: str) -> bool:
    """
    True if url host == root_domain OR any subdomain of it.
    e.g.  revenue.karnataka.gov.in  →  karnataka.gov.in  ✓
          amritmahotsav.nic.in      →  karnataka.gov.in  ✗
    """
    try:
        host = urlparse(url).netloc.lower().split(":")[0]
        root = root_domain.lower()
        return host == root or host.endswith("." + root)
    except Exception:
        return False


# -----------------------
# HTML & JS extractors
# -----------------------
def extract_urls_from_html(html: str, base_url: str) -> set:
    """Return absolute, normalized URLs found in HTML tags."""
    urls = set()
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception as exc:
        warn(f"HTML parse error: {exc}")
        return urls

    tag_attr = {
        "a": "href",    "link": "href",   "script": "src",
        "img": "src",   "form": "action", "iframe": "src",
        "frame": "src", "area": "href",   "source": "src",
        "track": "src", "embed": "src",   "object": "data",
    }
    for tag, attr in tag_attr.items():
        for el in soup.find_all(tag, **{attr: True}):
            try:
                raw = str(el[attr]).strip()
                if not raw:
                    continue
                abs_url = urljoin(base_url, raw)
                if is_valid_url(abs_url):
                    urls.add(normalize(abs_url))
            except Exception:
                continue

    # data-* attributes
    for el in soup.find_all(True):
        for attr in ("data-href", "data-url", "data-src", "data-link"):
            try:
                val = el.get(attr, "").strip()
                if val:
                    abs_url = urljoin(base_url, val)
                    if is_valid_url(abs_url):
                        urls.add(normalize(abs_url))
            except Exception:
                continue
    return urls


def extract_js_endpoints(js_text: str, base_url: str) -> set:
    """Regex-mine JS source for URL paths and full URLs."""
    urls = set()
    if not js_text:
        return urls
    patterns = [
        r'(?:url|href|src|endpoint|path|route|api|baseUrl|baseURL)\s*[:=]\s*["\x60]([^"\x60]{4,})["\x60]',
        r'fetch\s*\(\s*["\x60]([^"\x60]{4,})["\x60]',
        r'axios\.\w+\s*\(\s*["\x60]([^"\x60]{4,})["\x60]',
        r'["\x60](\/[\w\-./?=%&#+@:]{3,})["\x60]',
        r'https?://[^\s"\'`<>{}\[\]\\]{8,}',
    ]
    for pat in patterns:
        try:
            for match in re.findall(pat, js_text):
                raw = (match if isinstance(match, str) else match[0]).strip().rstrip(",'\"")
                if not raw:
                    continue
                abs_url = urljoin(base_url, raw)
                if is_valid_url(abs_url):
                    urls.add(normalize(abs_url))
        except Exception:
            continue
    return urls


# -----------------------
# Source 1 – Wayback Machine CDX API
# Queries domain/* AND *.domain/* for subdomains
# -----------------------
def fetch_wayback(domain: str) -> set:
    if _SHUTDOWN.is_set():
        return set()
    info(f"Fetching Wayback Machine for {Fore.YELLOW}{domain}{Style.RESET_ALL} (+ subdomains) ...")
    urls = set()
    queries = [
        f"https://web.archive.org/cdx/search/cdx?url={domain}/*"
        f"&output=text&fl=original&collapse=urlkey&limit=50000",
        f"https://web.archive.org/cdx/search/cdx?url=*.{domain}/*"
        f"&output=text&fl=original&collapse=urlkey&limit=50000",
    ]
    for api in queries:
        if _SHUTDOWN.is_set():
            break
        try:
            resp = fetch(api, timeout=40)
            text = decode_response(resp)
            for line in text.splitlines():
                line = line.strip()
                # Only keep URLs belonging to target domain / its subdomains
                if line and is_valid_url(line) and same_domain(line, domain):
                    urls.add(normalize(line))
        except Exception as exc:
            if not _SHUTDOWN.is_set():
                warn(f"Wayback error: {type(exc).__name__}: {exc}")
    info(f"Wayback -> {Fore.MAGENTA}{len(urls)}{Style.RESET_ALL} URLs")
    return urls


# -----------------------
# Source 2 – Common Crawl (latest index)
# Queries domain/* AND *.domain/*
# -----------------------
def fetch_commoncrawl(domain: str) -> set:
    if _SHUTDOWN.is_set():
        return set()
    info(f"Fetching Common Crawl for {Fore.YELLOW}{domain}{Style.RESET_ALL} (+ subdomains) ...")
    sys.stdout.flush()
    urls = set()
    try:
        idx_resp = fetch("https://index.commoncrawl.org/collinfo.json", timeout=15)
        indexes  = idx_resp.json()
        latest   = indexes[0]["cdx-api"]
    except Exception as exc:
        warn(f"Common Crawl index lookup failed: {type(exc).__name__}: {exc}")
        return urls

    for pattern in [f"{domain}/*", f"*.{domain}/*"]:
        if _SHUTDOWN.is_set():
            break
        api = f"{latest}?url={pattern}&output=text&fl=url&limit=20000"
        try:
            resp = fetch(api, timeout=40)
            text = decode_response(resp)
            for line in text.splitlines():
                line = line.strip()
                # Only keep URLs belonging to target domain / its subdomains
                if line and is_valid_url(line) and same_domain(line, domain):
                    urls.add(normalize(line))
        except Exception as exc:
            if not _SHUTDOWN.is_set():
                warn(f"Common Crawl error ({pattern}): {type(exc).__name__}: {exc}")

    info(f"Common Crawl -> {Fore.MAGENTA}{len(urls)}{Style.RESET_ALL} URLs")
    return urls


# -----------------------
# Source 3 – Live HTML crawler + JS endpoint scanner
# Follows links only within target domain + its subdomains
# -----------------------
def crawl_website(domain: str, base_url: str) -> set:
    if _SHUTDOWN.is_set():
        return set()
    info(f"Crawling {Fore.YELLOW}{domain}{Style.RESET_ALL} (follows *.{domain} subdomains) ...")
    visited    = set()
    to_visit   = {base_url}
    all_urls   = set()
    js_to_scan = set()

    while to_visit and len(visited) < MAX_CRAWL_PAGES:
        if _SHUTDOWN.is_set():
            break
        url = to_visit.pop()
        if url in visited:
            continue
        visited.add(url)

        try:
            resp = fetch(url)
            ct   = resp.headers.get("Content-Type", "")
            if "html" not in ct.lower():
                continue

            html = decode_response(resp)
            info(f"Crawling: {url}")
            sys.stdout.flush() 
            found_urls = extract_urls_from_html(html, url)

            for furl in found_urls:
                # - HARD FILTER: discard anything outside target domain -
                if not same_domain(furl, domain):
                    continue
                all_urls.add(furl)
                found(furl)
                if furl.lower().endswith(".js"):
                    js_to_scan.add(furl)
                elif furl not in visited:
                    to_visit.add(furl)

        except requests.exceptions.Timeout:
            warn(f"Timeout: {url}")
        except requests.exceptions.ConnectionError as exc:
            warn(f"Connection error {url}: {type(exc).__name__}")
        except requests.exceptions.HTTPError as exc:
            code = exc.response.status_code if exc.response else "?"
            warn(f"HTTP {code}: {url}")
        except Exception as exc:
            if not _SHUTDOWN.is_set():
                warn(f"Crawl error {url}: {type(exc).__name__}: {exc}")

    # - Parallel JS scanning -
    if js_to_scan and not _SHUTDOWN.is_set():
        info(f"Scanning {len(js_to_scan)} JS file(s) for endpoints ...")
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = {
                pool.submit(_fetch_js_endpoints, jurl, base_url): jurl
                for jurl in js_to_scan
            }
            for future in as_completed(futures):
                if _SHUTDOWN.is_set():
                    break
                try:
                    for u in future.result():
                        # HARD FILTER: only same-domain JS endpoints
                        if same_domain(u, domain):
                            all_urls.add(u)
                            found(u)
                except Exception as exc:
                    if not _SHUTDOWN.is_set():
                        warn(f"JS scan error: {type(exc).__name__}: {exc}")

    info(f"Crawler -> {Fore.MAGENTA}{len(all_urls)}{Style.RESET_ALL} URLs")
    return all_urls


def _fetch_js_endpoints(js_url: str, base_url: str) -> set:
    if _SHUTDOWN.is_set():
        return set()
    try:
        resp = fetch(js_url, timeout=10)
        text = decode_response(resp)
        return extract_js_endpoints(text, base_url)
    except Exception:
        return set()


# -----------------------
# Per-domain orchestrator
# -----------------------
def process_domain(domain: str, skip_cc: bool = False):
    domain = domain.strip().lower()
    domain = re.sub(r"^https?://", "", domain).strip("/")

    if not domain or "." not in domain:
        error(f"Invalid domain: '{domain}' — skipping.")
        return

    sep = "=" * 80
    safe_print(f"\n{sep}")
    safe_print(f"{Fore.CYAN}{Style.BRIGHT}  TARGET : {domain}{Style.RESET_ALL}")
    safe_print(f"  SCOPE  : {domain}  +  *.{domain}  (all subdomains)")
    safe_print(f"{sep}\n")

    base_url = resolve_base_url(domain)
    info(f"Resolved base URL: {Fore.WHITE}{base_url}{Style.RESET_ALL}")
    sys.stdout.flush()

    # 2-sec pause AFTER showing target info, BEFORE spawning threads
    time.sleep(2)

    all_urls: set = set()

    # - ThreadPoolExecutor with daemon threads so Ctrl+C kills them -
    with ThreadPoolExecutor(max_workers=3, thread_name_prefix="uf") as pool:
        futures_map = {
            pool.submit(fetch_wayback, domain):           "Wayback",
            pool.submit(crawl_website, domain, base_url): "Crawler",
        }
        if not skip_cc:
            futures_map[pool.submit(fetch_commoncrawl, domain)] = "CommonCrawl"

        for future in as_completed(futures_map):
            if _SHUTDOWN.is_set():
                break
            name = futures_map[future]
            try:
                all_urls.update(future.result())
            except Exception as exc:
                if not _SHUTDOWN.is_set():
                    warn(f"{name} failed: {type(exc).__name__}: {exc}")

    if _SHUTDOWN.is_set():
        warn("Scan interrupted — saving partial results ...")

    # - Write results — UTF-8 always, never crashes -
    safe_domain = re.sub(r"[^\w.\-]", "_", domain)
    outfile = f"{safe_domain}_urls.txt"
    try:
        with open(outfile, "w", encoding="utf-8", errors="replace") as fh:
            for url in sorted(all_urls):
                fh.write(url + "\n")

        safe_print("\n" + "-" * 80)
        safe_print(
            f"{Fore.GREEN}{Style.BRIGHT}[OK]{Style.RESET_ALL}  "
            f"Total unique URLs: {Fore.YELLOW}{len(all_urls)}{Style.RESET_ALL}  "
            f"  Saved -> {Fore.CYAN}{outfile}{Style.RESET_ALL}"
        )
        safe_print("-" * 80 + "\n")

    except IOError as exc:
        error(f"Could not write '{outfile}': {exc}")


# -----------------------
# Entry point
# -----------------------
def main():
    print_banner()   # shows banner
    parser = argparse.ArgumentParser(
        prog="urlsfetcher",
        description="URLSFETCHER - URL Enumeration & Crawling Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python urlsfetcher.py -u example.com
  python urlsfetcher.py -u karnataka.gov.in
  python urlsfetcher.py -l domains.txt
  python urlsfetcher.py -u example.com --no-cc    (skip Common Crawl for speed)

Sources per domain:
  - Wayback Machine CDX  : domain/* + *.domain/*
  - Common Crawl index   : domain/* + *.domain/*
  - Live HTML crawler    : follows subdomains automatically
  - JS endpoint scanner  : regex extraction from .js files
        """,
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-u", "--url",  metavar="DOMAIN", help="Single target domain")
    group.add_argument("-l", "--list", metavar="FILE",   help="File with one domain per line")
    parser.add_argument("--no-cc", action="store_true",
                        help="Skip Common Crawl (faster execution)")

    args = parser.parse_args()

    domains = []
    if args.url:
        domains = [args.url]
    elif args.list:
        try:
            with open(args.list, encoding="utf-8", errors="replace") as fh:
                domains = [
                    ln.strip() for ln in fh
                    if ln.strip() and not ln.startswith("#")
                ]
        except FileNotFoundError:
            error(f"File not found: {args.list}")
            sys.exit(1)

    if not domains:
        error("No valid domains found.")
        sys.exit(1)

    # - Outer try/except catches Ctrl+C from ANYWHERE including threads -
    try:
        for domain in domains:
            if _SHUTDOWN.is_set():
                break
            process_domain(domain, skip_cc=args.no_cc)
    except KeyboardInterrupt:
        _SHUTDOWN.set()
        warn("\nCtrl+C received — stopping cleanly ...")
        sys.exit(0)
    except Exception as exc:
        error(f"Fatal error: {type(exc).__name__}: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    # Make Ctrl+C set the shutdown flag before Python's signal handler fires
    import signal
    def _sig_handler(sig, frame):
        _SHUTDOWN.set()
        warn("\nCtrl+C received — stopping cleanly ...")
        sys.exit(0)
    signal.signal(signal.SIGINT, _sig_handler)

    main()
