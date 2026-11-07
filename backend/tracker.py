"""Visitor tracking: geo lookup, UA parsing, crawler detection."""

import httpx
import re


def parse_user_agent(ua: str) -> dict:
    """Parse user agent into device, os, browser."""
    ua_lower = ua.lower()
    device = "Desktop"
    os_name = "Unknown"
    browser = "Unknown"

    # Device
    if "mobile" in ua_lower or "android" in ua_lower and "mobile" in ua_lower:
        device = "Mobile"
    elif "tablet" in ua_lower or "ipad" in ua_lower:
        device = "Tablet"
    elif "android" in ua_lower:
        device = "Mobile"

    # OS
    if "windows" in ua_lower:
        os_name = "Windows"
    elif "mac os" in ua_lower or "macos" in ua_lower:
        os_name = "macOS"
    elif "iphone" in ua_lower or "ipad" in ua_lower:
        os_name = "iOS"
    elif "android" in ua_lower:
        os_name = "Android"
    elif "linux" in ua_lower:
        os_name = "Linux"

    # Browser
    if "chrome" in ua_lower and "edg" not in ua_lower:
        browser = "Chrome"
    elif "firefox" in ua_lower:
        browser = "Firefox"
    elif "safari" in ua_lower and "chrome" not in ua_lower:
        browser = "Safari"
    elif "edg" in ua_lower:
        browser = "Edge"
    elif "opera" in ua_lower or "opr" in ua_lower:
        browser = "Opera"

    return {"device": device, "os": os_name, "browser": browser}


def is_crawler(ua: str) -> bool:
    """Detect if the visitor is a crawler/bot (link preview fetcher)."""
    ua_lower = ua.lower()
    crawler_keywords = [
        "bot",
        "crawler",
        "spider",
        "preview",
        "facebookexternalhit",
        "whatsapp",
        "telegram",
        "slack",
        "discord",
        "twitterbot",
        "linkedinbot",
        "googlebot",
        "bingbot",
        "applebot",
        "curl",
        "wget",
        "python",
        "java",
        "go-http",
    ]
    return any(kw in ua_lower for kw in crawler_keywords)


def detect_referrer_app(referrer: str, ua: str) -> str:
    """Detect which app the link was opened from."""
    ua_lower = ua.lower()
    ref_lower = (referrer or "").lower()

    if "whatsapp" in ua_lower or "whatsapp" in ref_lower:
        return "WhatsApp"
    if "telegram" in ua_lower or "telegram" in ref_lower:
        return "Telegram"
    if "discord" in ua_lower or "discord" in ref_lower:
        return "Discord"
    if "slack" in ua_lower or "slack" in ref_lower:
        return "Slack"
    if "facebook" in ua_lower or "facebook" in ref_lower or "fbav" in ua_lower:
        return "Facebook"
    if "instagram" in ua_lower:
        return "Instagram"
    if "twitter" in ua_lower or "x.com" in ref_lower:
        return "Twitter/X"
    if referrer:
        return "Browser"
    return "Direct"


async def geo_lookup(ip: str) -> dict:
    """Look up city/country for an IP address."""
    if not ip or ip in ("127.0.0.1", "::1", "localhost", "0.0.0.0"):
        return {"city": "Local", "country": "Local", "region": ""}

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"http://ip-api.com/json/{ip}?fields=status,city,regionName,country"
            )
            data = resp.json()
            if data.get("status") == "success":
                return {
                    "city": data.get("city", "Unknown"),
                    "country": data.get("country", "Unknown"),
                    "region": data.get("regionName", ""),
                }
    except Exception:
        pass
    return {"city": "Unknown", "country": "Unknown", "region": ""}


