import os
import re
import urllib.parse
from typing import Dict, Any, List, Optional
import httpx
from html.parser import HTMLParser

class HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.result = []
        self.ignore_tags = {"script", "style", "nav", "footer", "noscript", "svg", "header", "form"}
        self.current_ignore = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self.ignore_tags:
            self.current_ignore += 1
        elif tag.lower() in ["p", "div", "br", "h1", "h2", "h3", "h4", "li", "tr", "section", "article"]:
            self.result.append("\n")

    def handle_endtag(self, tag):
        if tag.lower() in self.ignore_tags:
            self.current_ignore = max(0, self.current_ignore - 1)
        elif tag.lower() in ["p", "div", "h1", "h2", "h3", "h4", "li", "tr", "section", "article"]:
            self.result.append("\n")

    def handle_data(self, data):
        if self.current_ignore == 0:
            text = data.strip()
            if text:
                self.result.append(data)

    def get_text(self) -> str:
        raw = "".join(self.result)
        cleaned = re.sub(r'[ \t]+', ' ', raw)
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
        return cleaned.strip()

class WebScraperTool:
    def __init__(self):
        self.browser_headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        self.api_headers = {
            "User-Agent": "ForgeAgent/1.0 (https://forge.ai; dev@forge.io)",
            "Accept": "application/json",
        }

    async def scrape_url(self, url: str, max_chars: int = 8000) -> Dict[str, Any]:
        """Directly fetches and parses web pages, extracting title, text content, and code blocks."""
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        try:
            async with httpx.AsyncClient(timeout=12.0, follow_redirects=True, verify=False) as client:
                resp = await client.get(url, headers=self.browser_headers)
                if resp.status_code != 200:
                    return {
                        "status": "error",
                        "url": url,
                        "error": f"HTTP {resp.status_code}: Failed to fetch page",
                        "content": ""
                    }
                
                content_type = resp.headers.get("content-type", "")
                if "text/html" in content_type or "<html" in resp.text.lower():
                    parser = HTMLTextExtractor()
                    parser.feed(resp.text)
                    extracted_text = parser.get_text()
                else:
                    extracted_text = resp.text

                # Extract title
                title_match = re.search(r'<title[^>]*>(.*?)</title>', resp.text, re.IGNORECASE)
                title = title_match.group(1).strip() if title_match else url

                # Extract potential code blocks
                code_blocks = re.findall(r'<pre[^>]*><code[^>]*>(.*?)</code></pre>|<pre[^>]*>(.*?)</pre>', resp.text, re.DOTALL | re.IGNORECASE)
                extracted_code = []
                for c1, c2 in code_blocks:
                    code = (c1 or c2).strip()
                    if 20 < len(code) < 3000:
                        clean_c = re.sub(r'<[^>]+>', '', code)
                        extracted_code.append(clean_c)

                truncated = extracted_text[:max_chars]
                if len(extracted_text) > max_chars:
                    truncated += f"\n... [Truncated {len(extracted_text) - max_chars} characters for context economy]"

                return {
                    "status": "success",
                    "url": url,
                    "title": title,
                    "content": truncated,
                    "code_snippets": extracted_code[:5],
                    "char_count": len(truncated)
                }
        except Exception as e:
            return {
                "status": "error",
                "url": url,
                "error": str(e),
                "content": ""
            }

    async def search_wikipedia(self, query: str) -> Optional[Dict[str, Any]]:
        """Searches Wikipedia REST API for accurate biographical, technical, or factual information."""
        clean_q = re.sub(r'^(?:who\s+is|what\s+is|tell\s+me\s+about|search\s+for)\s+', '', query.strip(), flags=re.IGNORECASE).strip(' ?.')
        encoded = urllib.parse.quote(clean_q.replace(' ', '_'))
        
        try:
            async with httpx.AsyncClient(timeout=6.0, follow_redirects=True, verify=False) as client:
                # 1. Try direct summary
                r = await client.get(f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded}", headers=self.api_headers)
                if r.status_code == 200:
                    data = r.json()
                    if data.get("extract"):
                        return {
                            "title": data.get("title", clean_q),
                            "description": data.get("description", ""),
                            "extract": data.get("extract", ""),
                            "url": data.get("content_urls", {}).get("desktop", {}).get("page", f"https://en.wikipedia.org/wiki/{encoded}")
                        }
                
                # 2. Try search if direct title not found
                search_url = f"https://en.wikipedia.org/w/api.php?action=opensearch&search={urllib.parse.quote(clean_q)}&limit=1&namespace=0&format=json"
                sr = await client.get(search_url, headers=self.api_headers)
                if sr.status_code == 200:
                    sdata = sr.json()
                    if len(sdata) >= 4 and sdata[1] and sdata[3]:
                        top_title = sdata[1][0]
                        top_url = sdata[3][0]
                        enc_top = urllib.parse.quote(top_title.replace(' ', '_'))
                        sum_r = await client.get(f"https://en.wikipedia.org/api/rest_v1/page/summary/{enc_top}", headers=self.api_headers)
                        if sum_r.status_code == 200:
                            sum_data = sum_r.json()
                            return {
                                "title": sum_data.get("title", top_title),
                                "description": sum_data.get("description", ""),
                                "extract": sum_data.get("extract", sdata[2][0] if sdata[2] else ""),
                                "url": top_url
                            }
        except Exception:
            pass
        return None

    async def search_and_scrape(self, query: str, max_results: int = 4) -> Dict[str, Any]:
        """Universal research tool: handles direct URLs, Wikipedia knowledge, PyPI docs, and Web Search."""
        results = []
        clean_q = query.strip()

        # 1. If query contains a direct URL, scrape it first
        url_match = re.search(r'https?://[^\s<>"]+', clean_q)
        if url_match:
            scraped = await self.scrape_url(url_match.group(0))
            if scraped.get("status") == "success":
                results.append({
                    "title": scraped.get("title", "Direct Web Page"),
                    "url": scraped.get("url"),
                    "snippet": scraped.get("content", "")[:1200]
                })

        # 2. Check Wikipedia for entities / people / concepts
        wiki_data = await self.search_wikipedia(clean_q)
        if wiki_data:
            results.append({
                "title": f"Wikipedia: {wiki_data['title']} ({wiki_data.get('description', '')})",
                "url": wiki_data["url"],
                "snippet": wiki_data["extract"]
            })

        # 3. Check PyPI if query relates to Python packages
        pkg_match = re.search(r'(?:python|pypi|package|library|install|pip)\s+([a-zA-Z0-9_\-]+)', clean_q.lower())
        if pkg_match:
            target_pkg = pkg_match.group(1)
            try:
                async with httpx.AsyncClient(timeout=4.0, follow_redirects=True, verify=False) as client:
                    pypi_res = await client.get(f"https://pypi.org/pypi/{target_pkg}/json")
                    if pypi_res.status_code == 200:
                        pdata = pypi_res.json()
                        info = pdata.get("info", {})
                        results.append({
                            "title": f"PyPI: {info.get('name', target_pkg)} ({info.get('version', '')})",
                            "url": info.get("package_url", f"https://pypi.org/project/{target_pkg}/"),
                            "snippet": (info.get("summary") or "") + "\nDocs: " + (info.get("project_urls", {}).get("Documentation") or info.get("home_page") or "")
                        })
            except Exception:
                pass

        # 4. DuckDuckGo Lite search for live general results
        search_url = "https://lite.duckduckgo.com/lite/"
        try:
            async with httpx.AsyncClient(timeout=5.0, follow_redirects=True, verify=False, headers=self.browser_headers) as client:
                res = await client.post(search_url, data={"q": clean_q})
                if res.status_code == 200:
                    links = re.findall(r'<a class="result-link"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', res.text)
                    snippets = re.findall(r'<td class="result-snippet"[^>]*>(.*?)</td>', res.text)
                    for idx, (url_m, title_m) in enumerate(links[:max_results]):
                        snippet_text = snippets[idx] if idx < len(snippets) else ""
                        clean_snippet = re.sub(r'<[^>]+>', '', snippet_text).strip()
                        clean_title = re.sub(r'<[^>]+>', '', title_m).strip()
                        if clean_title and clean_snippet:
                            results.append({
                                "title": clean_title,
                                "url": url_m,
                                "snippet": clean_snippet
                            })
        except Exception:
            pass

        return {
            "status": "success" if results else "error",
            "query": query,
            "results": results[:max_results],
            "error": "No results retrieved" if not results else None
        }

web_scraper = WebScraperTool()
