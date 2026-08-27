#!/usr/bin/env python3
"""
Solution script to scrape data from gvbytes.com and store it in a Markdown file.
"""

import json
from pathlib import Path
from typing import Dict, Any

# Import the helper function from fetch_gvbytes_data.py
try:
    from fetch_gvbytes_data import fetch_data_from_gvbytes
except ImportError as exc:
    raise ImportError(
        "Could not import fetch_data_from_gvbytes. "
        "Ensure fetch_gvbytes_data.py is in the same directory."
    ) from exc


def _format_markdown(data: Dict[str, Any]) -> str:
    """
    Convert the dictionary returned by fetch_data_from_gvbytes into a Markdown string.
    """
    lines = []

    # Header
    lines.append(f"# gvbytes.com Data")
    lines.append(f"**URL**: {data.get('url', 'N/A')}")
    lines.append("")

    if "error" in data:
        lines.append("## ❌ Error")
        lines.append(f"{data['error']}")
        return "\n".join(lines)

    # Basic info
    lines.append("## 📊 Basic Information")
    lines.append(f"- **Status Code**: {data.get('status_code', 'N/A')}")
    lines.append(f"- **Content Type**: {data.get('content_type', 'N/A')}")
    lines.append(f"- **Content Length**: {data.get('content_length', 'N/A')} bytes")
    lines.append("")

    # Page title
    title = data.get("title", "N/A")
    lines.append("## 📄 Page Title")
    lines.append(f"{title}")
    lines.append("")

    # Links
    links = data.get("links", [])
    lines.append(f"## 🔗 Links ({len(links)})")
    if links:
        for i, link in enumerate(links, start=1):
            lines.append(f"{i}. [{link}]({link})")
    else:
        lines.append("No links found.")
    lines.append("")

    # Raw JSON for reference
    lines.append("## 📦 Raw JSON")
    lines.append("