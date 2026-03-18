<div align="center">

# 🔍 URLSFETCHER

**A high-performance URL enumeration & crawling tool for bug bounty and recon**

![Python](https://img.shields.io/badge/Python-3.8%2B-blue?style=flat-square&logo=python)
![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)
![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20macOS%20%7C%20Windows-lightgrey?style=flat-square)
![Status](https://img.shields.io/badge/Status-Active-brightgreen?style=flat-square)

*Combines Wayback Machine, Common Crawl, live HTML crawling, and JS endpoint extraction - all in a single lightweight script.*

</div>

---

## 📸 Preview

```
██╗   ██╗██████╗ ██╗        ███████╗███████╗████████╗ ██████╗██╗  ██╗███████╗██████╗
██║   ██║██╔══██╗██║        ██╔════╝██╔════╝╚══██╔══╝██╔════╝██║  ██║██╔════╝██╔══██╗
██║   ██║██████╔╝██║        █████╗  █████╗     ██║   ██║     ███████║█████╗  ██████╔╝
██║   ██║██╔══██╗██║        ██╔══╝  ██╔══╝     ██║   ██║     ██╔══██║██╔══╝  ██╔══██╗
╚██████╔╝██║  ██║███████╗S  ██║     ███████╗   ██║   ╚██████╗██║  ██║███████╗██║  ██║
 ╚═════╝ ╚═╝  ╚═╝╚══════╝   ╚═╝     ╚══════╝   ╚═╝    ╚═════╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝


  URL Enumeration & Crawling Tool  | Author: hkmj
────────────────────────────────────────────────────────────────────────────────

================================================================================
  TARGET : example.com
  SCOPE  : example.com  +  *.example.com  (all subdomains)
================================================================================

[+] Resolved base URL: https://example.com

[+] Fetching Wayback Machine for example.com (+ subdomains) ...
[+] Crawling example.com (follows *.example.com subdomains) ...
[+] Fetching Common Crawl for example.com (+ subdomains) ...
[+] Crawling: https://example.com
  > https://example.com/english
  > https://admin.example.com/
  > https://accounts.example.com/
[+] Wayback -> 400 URLs
[+] Common Crawl -> 200 URLs
[+] Crawler -> 300 URLs
--------------------------------------------------------------------------------
[OK]  Total unique URLs: 900    Saved -> example.com_urls.txt
--------------------------------------------------------------------------------
```

---

## ✨ Features

| Feature | Detail |
|---|---|
| 🏛️ **Wayback Machine** | CDX API - up to 50,000 historical URLs per query × 2 (domain + subdomains) |
| 🕸️ **Common Crawl** | Latest crawl index - up to 20,000 URLs × 2 (domain + subdomains) |
| 🤖 **Live Crawler** | Parses `<a>`, `<script>`, `<form>`, `<img>`, `<iframe>`, `data-*` tags |
| 📜 **JS Endpoint Extraction** | Regex-mines paths and URLs from all `.js` files found during crawl |
| 🌐 **Subdomain Scope** | All sources query `*.domain/*` - captures every subdomain automatically |
| 🔒 **Domain Filtering** | External URLs (e.g. `opensource.org`, `nic.in`) are hard-filtered at every source |
| ⚡ **Concurrent Execution** | Wayback, Common Crawl and Crawler run in parallel via `ThreadPoolExecutor` |
| 🔁 **Retry + SSL Fallback** | 3 retries with backoff + automatic `verify=False` for broken-cert sites (`.com` etc) |
| 🛡️ **Safe Encoding** | `decode_response()` never crashes - tries charset → utf-8 → latin-1 |
| 💾 **UTF-8 Output** | Output file always written as UTF-8 - no `charmap` errors |
| ⛔ **Clean Ctrl+C** | `signal.SIGINT` handler + `_SHUTDOWN` event stops all threads instantly |
| 🎨 **Colored CLI** | colorama - works on Windows, macOS, Linux |

---

## 📦 Installation

```bash
# 1. Clone the repository
git clone https://github.com/hkmj/urlsfetcher.git
cd urlsfetcher

# 2. (Recommended) Create a virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt
```

**requirements.txt**
```
requests
beautifulsoup4
colorama
```

---

## 🚀 Usage

### Single domain
```bash
python urlsfetcher.py -u example.com
```

### Multiple domains from a file
```bash
python urlsfetcher.py -l domains.txt
```

### Skip Common Crawl (faster)
```bash
python urlsfetcher.py -u example.com --no-cc
```

### Help menu
```bash
python urlsfetcher.py -h
```

---

## ⚙️ CLI Options

| Flag | Description |
|------|-------------|
| `-u`, `--url` | Single target domain (e.g. `example.com`) |
| `-l`, `--list` | Path to a file with one domain per line |
| `--no-cc` | Skip Common Crawl (speeds up execution) |
| `-h`, `--help` | Show help and exit |

---

## 🌐 Scope - What Gets Collected

For a target like `example.com`, URLSFETCHER collects URLs **only** from:

```
example.com
*.example.com                →  revenue.example.com
                             →  transport.example.com
                             →  police.example.com
                             →  ...and all other subdomains
```

URLs from unrelated domains (`nic.in`, `com`, `opensource.org` etc.) are **always discarded** - at every source, at every stage.

---

## 📁 Output

Results are saved to a file named after the target:

```
example.com_urls.txt
```

Each line = one unique, normalized URL:

```
https://example.com/
https://example.com/english
https://example.com/news/2024
https://revenue.example.com/
https://revenue.example.com/services
...
```

- Always written as **UTF-8** (no charmap crash)
- Sorted alphabetically
- Deduplicated

---

## 🗂️ Project Structure

```
urlsfetcher/
├── urlsfetcher.py      # Single-file tool (all logic here)
├── requirements.txt    # Python dependencies
├── README.md           # This file
├── LICENSE             # MIT License
└── domains.txt         # (Optional) example domains list
```

---

## 🔍 How It Works

```
Target: example.com
         │
         ├──► Wayback CDX  → domain/* + *.domain/*  →  filter: same_domain() only
         │
         ├──► Common Crawl → domain/* + *.domain/*  →  filter: same_domain() only
         │
         └──► Live Crawler → HTML parse → same_domain() filter
                   │
                   └──► .js files → regex endpoint extraction → same_domain() filter
                                          │
                                          ▼
                              Deduplicate with set()
                                          │
                                          ▼
                              Normalize (lowercase, no fragment)
                                          │
                                          ▼
                         example.com_urls.txt  +  live terminal output
```

All 3 sources run **concurrently**. JS files are scanned in a separate parallel pool. Every single URL passes through `same_domain()` before being stored.

---

## ⚠️ Disclaimer

> This tool is intended for **authorized security testing, bug bounty programs, and educational purposes only.**
>
> Do **not** use this tool against systems you do not own or have explicit written permission to test. Unauthorized scanning may violate computer crime laws in your jurisdiction (e.g. CFAA, Computer Misuse Act, IT Act 2000).
>
> The author is not responsible for any misuse or damage caused by this tool.

---

## 🤝 Contributing

Contributions, issues, and feature requests are welcome!

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Commit your changes (`git commit -m 'Add: your feature'`)
4. Push and open a Pull Request

**Ideas for contributions:**
- OTX AlienVault / VirusTotal as URL sources
- Depth control flag (`--depth N`)
- Output formats: JSON, CSV
- Filter by file extension (`--ext php,js,json`)
- Proxy support (`--proxy http://127.0.0.1:8080`)
- Rate limiting (`--delay 0.5`)

---

## 📄 License

This project is licensed under the **MIT License** - see the [LICENSE](LICENSE) file for details.

---

<div align="center">

Made with ❤️ by **hkmj**
If this tool helped you, give it a ⭐ on GitHub!

</div>
