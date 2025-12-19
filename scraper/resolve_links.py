import json
import os
import re
import time
import requests
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

# ENV vars
AMAZON_TAG = os.getenv("AMAZON_TAG", "buysasta0103-21")
VCOMMISSION_API_KEY = os.getenv("VCOMMISSION_API_KEY", "69422f99c7ca0d638b3bdba474469422f99c7cdc")

BASE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(BASE, "data", "deals_raw.json")
FINAL = os.path.join(BASE, "data", "deals.json")

MAX_DEALS = 300  # deals.json me max itne hi deals rahenge


def resolve_flipshope(url):
    """EXISTING LOGIC - UNTOUCHED"""
    m = re.search(r"/redirect/([^/]+)/(\d+)", url)
    if not m:
        return url, "unknown"

    pid, code = m.groups()

    MAP = {
        "7": ("myntra", f"https://www.myntra.com/product/p/p/{pid}/buy"),
        "1": ("flipkart", f"https://www.flipkart.com/p/p/item?pid={pid}"),
        "14": ("reliancedigital", f"https://www.reliancedigital.in/product/{pid}"),
        "2": ("amazon", f"https://www.amazon.in/dp/{pid}"),
        "6": ("ajio", f"https://www.ajio.com/p/{pid}"),
    }

    return MAP.get(code, (url, "unknown"))


def add_amazon_tag(url, tag):
    """Amazon tag add - simple & safe"""
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    query["tag"] = tag
    new_query = urlencode(query, doseq=True)
    new_url = urlunparse(
        (parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment)
    )
    return new_url


def vcommission_convert(url, platform):
    """VCommission Trackier API - Non-Amazon platforms"""
    try:
        print(f"🔄 VCommission {platform}: {url[:60]}...")

        coupon_api = f"https://api.trackier.com/v2/publishers/coupons?apikey={VCOMMISSION_API_KEY}"
        resp = requests.get(coupon_api, timeout=15)

        if resp.status_code == 200:
            coupons = resp.json().get("data", [])

            platform_keywords = {
                "flipkart": ["flipkart"],
                "myntra": ["myntra"],
                "ajio": ["ajio"],
                "reliancedigital": ["reliance", "digital"],
            }

            keywords = platform_keywords.get(platform.lower(), [platform.lower()])

            for coupon in coupons:
                coupon_name = coupon.get("name", "").lower()
                advertiser = coupon.get("advertiser", "").lower()

                if any(kw in coupon_name or kw in advertiser for kw in keywords):
                    affiliate_link = coupon.get("link", url)
                    print(f"✅ VCommission coupon: {coupon.get('name')[:40]}...")
                    return affiliate_link

            print(f"⚠️ No VCommission coupon for {platform}")
        else:
            print(f"❌ VCommission API: {resp.status_code}")

        return url  # Safe fallback

    except Exception as e:
        print(f"❌ VCommission error: {e}")
        return url


def merge_with_existing(new_deals):
    """
    new_deals: current run ke resolved deals (latest)
    deals.json: existing history

    Output: merged list (new on top, max 300, id-based dedupe)
    """
    try:
        if os.path.exists(FINAL):
            with open(FINAL, "r", encoding="utf-8") as f:
                old_deals = json.load(f)
        else:
            old_deals = []
    except json.JSONDecodeError:
        old_deals = []

    # New deals TOP par, purane niche
    combined = new_deals + old_deals

    # ID ke basis par dedupe: naya occurrence rakho, purana drop
    seen_ids = set()
    deduped = []
    for deal in combined:
        deal_id = deal.get("id")
        if not deal_id:
            deduped.append(deal)
            continue
        if deal_id in seen_ids:
            continue
        seen_ids.add(deal_id)
        deduped.append(deal)

    # Sirf max MAX_DEALS entries (latest upar)
    return deduped[:MAX_DEALS]


def main():
    time.sleep(2)

    print(f"🔧 AMAZON_TAG: {AMAZON_TAG}")
    print(f"🔧 VCOMMISSION_KEY: {VCOMMISSION_API_KEY[:8]}...\n")

    with open(RAW, "r", encoding="utf-8") as f:
        deals = json.load(f)

    final_deals = []
    print(f"🔗 Processing {len(deals)} deals...\n")

    for d in deals:
        original = d["original_link"]

        # STEP 1: RESOLVE FLIPSHOPE (SAME LOGIC)
        if "flipshope.com/redirect" in original:
            platform, resolved = resolve_flipshope(original)
        else:
            resolved = original
            platform = d.get("platform", "unknown")

        # STEP 2: AFFILIATE CONVERSION
        if platform == "amazon":
            affiliate = add_amazon_tag(resolved, AMAZON_TAG)
            print(f"✅ Amazon tag added: ?tag={AMAZON_TAG}")
        else:
            affiliate = vcommission_convert(resolved, platform)

        # PERFECT LOGGING
        print("ORIGINAL  :", original[:80] + "..." if len(original) > 80 else original)
        print("RESOLVED  :", resolved[:80] + "..." if len(resolved) > 80 else resolved)
        print("AFFILIATE :", affiliate[:80] + "..." if len(affiliate) > 80 else affiliate)
        print("PLATFORM  :", platform)
        print("-" * 70)

        # SAME JSON STRUCTURE - SIRF LINK + PLATFORM UPDATE
        new_d = d.copy()
        new_d["platform"] = platform
        new_d["original_link"] = affiliate  # CONVERTED LINK

        final_deals.append(new_d)

    # 🔁 Existing deals.json ke saath merge (rolling 300)
    merged_deals = merge_with_existing(final_deals)

    # SAVE EXACT SAME FORMAT
    with open(FINAL, "w", encoding="utf-8") as f:
        json.dump(merged_deals, f, indent=2, ensure_ascii=False)

    print(f"\n💾 ✅ Saved {len(merged_deals)} affiliate deals → {FINAL}")

    # 🧹 RAW JSON cleanup: keep only final deals.json
    try:
        if os.path.exists(RAW):
            os.remove(RAW)
            print(f"🧹 Deleted raw deals file → {RAW}")
    except Exception as e:
        print(f"⚠️ Could not delete RAW file: {e}")


if __name__ == "__main__":
    main()
