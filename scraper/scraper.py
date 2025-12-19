import sys
import os
import json
import time
import hashlib
import re
from datetime import datetime

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait


class DealScraper:
    def __init__(self):
        self.driver = None
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.data_dir = os.path.join(self.base_dir, "data")
        os.makedirs(self.data_dir, exist_ok=True)

        self.raw_file = os.path.join(self.data_dir, "deals_raw.json")
        self.final_file = os.path.join(self.data_dir, "deals.json")

        self.setup_driver()

    # ---------------- DRIVER ----------------
    def setup_driver(self):
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_argument(
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        )

        self.driver = webdriver.Chrome(service=Service(), options=options)
        self.driver.execute_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
        )

    # ---------------- HELPERS ----------------
    def generate_id(self, title):
        base = re.sub(r"[^a-z0-9]", "-", title.lower()[:40])
        return hashlib.md5(base.encode()).hexdigest()[:12]

    def find(self, box, selectors):
        for sel in selectors:
            try:
                return box.find_element(By.CSS_SELECTOR, sel)
            except:
                pass
        return None

    # ---------------- EXTRACTORS ----------------
    def extract_title(self, box):
        el = self.find(box, ["p", "div.middle_sec p"])
        return el.text.strip() if el else ""

    def extract_image(self, box):
        el = self.find(box, ["img"])
        return el.get_attribute("src") if el else ""

    def extract_price(self, box):
        el = self.find(box, [".disc_price p", ".price p"])
        return el.text.strip() if el else ""

    def extract_mrp(self, box):
        el = self.find(box, ["strike", ".actual_price p"])
        return el.text.strip() if el else ""

    def extract_discount(self, box):
        el = self.find(
            box,
            [
                "div.flex.gap-1.font-semibold.text-[10px].md\\:text-[12px].leading-[14px].md\\:leading-[16px].text-[#828282] > div:nth-child(2)",
                "[class*='discount']",
                ".flex.gap-1",
            ],
        )
        return el.text.strip() if el else ""

    # ---------------- PLATFORM FROM FINAL URL (FIXED) ----------------
    def extract_platform_from_url(self, url: str):
        if not url:
            return "unknown"

        u = url.lower()

        PLATFORM_MAP = {
            "amazon": ["amazon.in", "amazon.com"],
            "flipkart": ["flipkart.com"],
            "myntra": ["myntra.com"],
            "ajio": ["ajio.com"],
            "tatacliq": ["tatacliq.com"],
            "meesho": ["meesho.com"],
            "reliancedigital": ["reliancedigital.in"],
            "jiomart": ["jiomart.com"],
            "nykaa": ["nykaa.com"],
            "pepperfry": ["pepperfry.com"],
            "firstcry": ["firstcry.com"],
            "croma": ["croma.com"],
            "snapdeal": ["snapdeal.com"],
            "shopclues": ["shopclues.com"],
            "adidas": ["adidas"],
        }

        for platform, keywords in PLATFORM_MAP.items():
            for kw in keywords:
                if kw in u:
                    return platform

        return "unknown"

    # ---------------- REAL LINK (JS CLICK) ----------------
    def extract_real_link(self, box):
        try:
            btn = self.find(box, ["button"])
            if not btn:
                return ""

            self.driver.execute_script("arguments[0].click();", btn)

            WebDriverWait(self.driver, 12).until(
                lambda d: len(d.window_handles) > 1
            )

            self.driver.switch_to.window(self.driver.window_handles[1])

            WebDriverWait(self.driver, 20).until(
                lambda d: d.execute_script("return document.readyState")
                == "complete"
            )

            final_url = self.driver.current_url

            self.driver.close()
            self.driver.switch_to.window(self.driver.window_handles[0])

            return final_url

        except Exception as e:
            print("⚠ link error:", show)
            return ""

    # ---------------- SCRAPER ----------------
    def scrape(self):
        print("🔄 Loading FlipShope...")
        self.driver.get("https://flipshope.com/")

        WebDriverWait(self.driver, 25).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )

        for _ in range(6):
            self.driver.execute_script(
                "window.scrollTo(0, document.body.scrollHeight);"
            )
            time.sleep(1.5)

        boxes = self.driver.find_elements(
            By.CSS_SELECTOR, "div.RecentPriceDropGridContainer > div"
        )

        print(f"📦 Deals Found: {len(boxes)}")

        raw_deals = []

        for box in boxes:
            title = self.extract_title(box)
            if not title:
                continue

            real_link = self.extract_real_link(box)
            if not real_link:
                continue

            deal = {
                "id": self.generate_id(title),
                "title": title,
                "image": self.extract_image(box),
                "price": self.extract_price(box),
                "mrp": self.extract_mrp(box),
                "discount": self.extract_discount(box),
                "platform": self.extract_platform_from_url(real_link),
                "original_link": real_link,
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }

            raw_deals.append(deal)
            print(f"✔ {title[:45]} → {deal['platform']}")

        return raw_deals

    # ---------------- SAVE ----------------
    def save_raw_only(self, new_deals):
        try:
            if os.path.exists(self.raw_file):
                with open(self.raw_file, "r", encoding="utf-8") as f:
                    old_deals = json.load(f)
            else:
                old_deals = []
        except json.JSONDecodeError:
            old_deals = []

        combined = new_deals + old_deals

        seen_ids = set()
        deduped = []
        for deal in combined:
            deal_id = deal.get("id")
            if deal_id in seen_ids:
                continue
            seen_ids.add(deal_id)
            deduped.append(deal)

        deduped = deduped[:200]

        with open(self.raw_file, "w", encoding="utf-8") as f:
            json.dump(deduped, f, indent=2, ensure_ascii=False)

        print(
            f"💾 RAW saved: {len(deduped)} deals "
            "(new on top, max 200, no duplicate ids)"
        )
        print("📁 RAW  :", self.raw_file)

    def close(self):
        self.driver.quit()


def main():
    bot = DealScraper()
    deals = bot.scrape()
    bot.save_raw_only(deals)
    bot.close()


if __name__ == "__main__":
    main()
