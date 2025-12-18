import os
import urllib.parse
import requests

VCOMMISSION_API_KEY = os.getenv("VCOMMISSION_API_KEY")
AMAZON_TAG = os.getenv("AMAZON_TAG")


def amazon_affiliate(url: str) -> str:
    if "amazon." not in url or not AMAZON_TAG:
        return url

    base = url.split("?")[0]
    return f"{base}?tag={AMAZON_TAG}"


def vcommission_affiliate(url: str) -> str:
    if not VCOMMISSION_API_KEY:
        return url

    api = "https://api.vcommission.com/v2/publisher/deeplink"
    payload = {
        "apiKey": VCOMMISSION_API_KEY,
        "url": url
    }

    try:
        r = requests.post(api, json=payload, timeout=10)
        if r.status_code == 200:
            data = r.json()
            return data.get("shortUrl") or data.get("url") or url
    except Exception:
        pass

    return url


def convert_to_affiliate(url: str, platform: str) -> str:
    if platform == "amazon":
        return amazon_affiliate(url)

    return vcommission_affiliate(url)
