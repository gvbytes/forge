"""
Fetches data from gvbytes.com and extracts basic page information.
Requires: requests, beautifulsoup4 (install via: pip install requests beautifulsoup4)
"""

import sys
import subprocess
from urllib.parse import urljoin
from typing import Dict, List, Any

# Attempt to import requests, installing it if missing
try:
    import requests
except ImportError:
    print("⚠️ 'requests' library not found. Attempting to install via pip...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
        import requests  # type: ignore
        print("✅ 'requests' installed successfully.")
    except Exception as e:
        print(f"❌ Failed to install 'requests': {e}")
        sys.exit(1)

# Attempt to import BeautifulSoup, installing it if missing
try:
    from bs4 import BeautifulSoup
except ImportError:
    print("⚠️ 'beautifulsoup4' library not found. Attempting to install via pip...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "beautifulsoup4"])
        from bs4 import BeautifulSoup  # type: ignore
        print("✅ 'beautifulsoup4' installed successfully.")
    except Exception as e:
        print(f"❌ Failed to install 'beautifulsoup4': {e}")
        sys.exit(1)


def _safe_title(soup: BeautifulSoup) -> str:
    """
    Safely extract the page title, handling cases where the title tag is missing
    or empty.
    """
    if soup.title:
        title_text = soup.title.string
        if title_text:
            return title_text.strip()
    return "No title found"


def _extract_links(soup: BeautifulSoup, base_url: str) -> List[str]:
    """
    Extract all hyperlinks from the page, converting relative URLs to absolute ones.
    """
    links = []
    for a_tag in soup.find_all("a", href=True):
        href = a_tag.get("href")
        if href:
            absolute = urljoin(base_url, href)
            links.append(absolute)
    return links


def fetch_data_from_gvbytes(
    url: str = "https://gvbytes.com",
    verbose: bool = True,
    timeout: int = 10,
) -> Dict[str, Any]:
    """
    Fetches the given URL and returns a dictionary containing:
        - url: The requested URL
        - status_code: HTTP status code
        - content_type: MIME type of the response
        - content_length: Length of the response content in bytes
        - title: Page title
        - links: List of all extracted hyperlinks (absolute URLs)

    Parameters
    ----------
    url : str
        The URL to fetch.
    verbose : bool
        If True, prints detailed information to stdout.
    timeout : int
        Timeout in seconds for the HTTP request.

    Returns
    -------
    dict
        Dictionary with the extracted data. In case of an error, the dictionary
        will contain an 'error' key with a descriptive message.
    """
    result: Dict[str, Any] = {"url": url}
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()

        if verbose:
            print(f"✅ Successfully fetched data from {url}")
            print(f"   Status Code: {response.status_code}")
            print(f"   Content Type: {response.headers.get('content-type', 'unknown')}")
            print(f"   Content Length: {len(response.content)} bytes\n")

        # Populate basic response info
        result.update(
            {
                "status_code": response.status_code,
                "content_type": response.headers.get("content-type", "unknown"),
                "content_length": len(response.content),
            }
        )

        # Parse HTML content
        soup = BeautifulSoup(response.text, "html.parser")

        # Extract page title
        title = _safe_title(soup)
        result["title"] = title
        if verbose:
            print(f"📄 Page Title: {title}")

        # Extract all hyperlinks
        links = _extract_links(soup, url)
        result["links"] = links
        if verbose:
            print(f"🔗 Found {len(links)} links on the page.\n")
            for i, link in enumerate(links[:5], 1):
                print(f"   {i}. {link}")

    except requests.exceptions.HTTPError as e:
        error_msg = f"❌ HTTP Error: {e}"
        if verbose:
            print(error_msg)
            print("   The server returned an invalid or unexpected response.")
        result["error"] = error_msg
    except requests.exceptions.ConnectionError as e:
        error_msg = f"🌐 Connection Error: Could not reach {url}."
        if verbose:
            print(error_msg)
            print("   Check your internet connection or the domain spelling.")
        result["error"] = error_msg
    except requests.exceptions.Timeout as e:
        error_msg = f"⏱️ Timeout Error: The request to {url} timed out after {timeout} seconds."
        if verbose:
            print(error_msg)
            print("   Try increasing the timeout or checking network stability.")
        result["error"] = error_msg
    except requests.exceptions.RequestException as e:
        error_msg = f"⚠️ Request Error: {e}"
        if verbose:
            print(error_msg)
        result["error"] = error_msg
    except Exception as e:
        error_msg = f"🚨 Unexpected Error: {e}"
        if verbose:
            print(error_msg)
        result["error"] = error_msg

    return result


if __name__ == "__main__":
    data = fetch_data_from_gvbytes()
    # Optionally, you can process `data` further here