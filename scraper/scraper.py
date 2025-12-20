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
        self.setup_driver()

    # ---------------- DRIVER ----------------
    def setup_driver(self):
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-popup-blocking")
        options.add_argument("--disable-notifications")

        self.driver = webdriver.Chrome(service=Service(), options=options)
        self.driver.execute_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
        )

    # ---------------- HELPERS ----------------
    def generate_id(self, title):
        base = re.sub(r"[^a-z0-9]", "-", title.lower())
        return hashlib.md5(base.encode()).hexdigest()[:12]

    def find(self, box, selectors):
        for sel in selectors:
            try:
                el = box.find_element(By.CSS_SELECTOR, sel)
                if el:
                    return el
            except:
                pass
        return None

    def clean_price(self, text):
        if not text:
            return 0
        val = re.sub(r"[^\d]", "", text)
        return int(val) if val.isdigit() else 0

    # ---------------- EXTRACTORS ----------------
    def extract_title(self, box):
        el = self.find(box, ["p", "div.middle_sec p"])
        return el.text.strip() if el else ""

    def extract_image(self, box):
        el = self.find(box, ["img"])
        if not el:
            return ""
        src = el.get_attribute("src") or ""
        return src if src.startswith("http") else ""

    def extract_price(self, box):
        el = self.find(box, [".disc_price p", ".price p"])
        return el.text.strip() if el else ""

    def extract_mrp(self, box):
        el = self.find(box, ["strike", ".actual_price p"])
        return el.text.strip() if el else ""

    def extract_discount(self, box, price, mrp):
        for el in box.find_elements(By.XPATH, ".//*[contains(text(), '%')]"):
            if re.search(r"\d+%", el.text):
                return el.text.strip()

        p = self.clean_price(price)
        m = self.clean_price(mrp)
        if p > 0 and m > p:
            return f"{round(((m - p) / m) * 100)}% OFF"

        return "0% OFF"

    # ---------------- PLATFORM ----------------
    def detect_platform(self, final_url, image_url):
        text = f"{final_url} {image_url}".lower()

        platforms = {
            "amazon": ["amazon.in"],
            "flipkart": ["flipkart.com"],
            "myntra": ["myntra.com"],
            "ajio": ["ajio.com"],
            "meesho": ["meesho.com"],
            "nykaa": ["nykaa.com"],
            "jiomart": ["jiomart.com"],
        }

        for p, keys in platforms.items():
            for k in keys:
                if k in text:
                    return p

        if "flipshope.com/redirect" in final_url:
            if "/2" in final_url:
                return "amazon"
            if "/1" in final_url:
                return "flipkart"
            if "/7" in final_url:
                return "myntra"

        return "unknown"

    # ---------------- BUTTON CLICK LINK ----------------
    def extract_real_link(self, box):
        try:
            btn = self.find(box, ["button", "a"])
            if not btn:
                return ""

            self.driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'});", btn
            )
            time.sleep(0.5)

            old_handles = self.driver.window_handles
            self.driver.execute_script("arguments[0].click();", btn)

            # Wait for popup OR redirect
            for _ in range(20):
                time.sleep(0.5)
                if len(self.driver.window_handles) > len(old_handles):
                    break

            # New tab opened
            if len(self.driver.window_handles) > len(old_handles):
                self.driver.switch_to.window(self.driver.window_handles[-1])
                time.sleep(2)
                url = self.driver.current_url
                self.driver.close()
                self.driver.switch_to.window(old_handles[0])
                return url if url.startswith("http") else ""

            # Same tab redirect
            current = self.driver.current_url
            if "flipshope.com" not in current:
                self.driver.back()
                time.sleep(1)
                return current

            return ""

        except Exception as e:
            print("❌ Link error:", e)
            return ""

    # ---------------- SCRAPE ----------------
    def scrape(self):
        print("🔄 Loading FlipShope...")
        self.driver.get("https://flipshope.com/")
        time.sleep(6)

        for _ in range(6):
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(1)

        boxes = self.driver.find_elements(
            By.CSS_SELECTOR, "div.RecentPriceDropGridContainer > div"
        )
        print(f"📦 Deals Found: {len(boxes)}")

        deals = []

        for box in boxes:
            title = self.extract_title(box)
            if not title:
                continue

            link = self.extract_real_link(box)
            if not link:
                continue

            image = self.extract_image(box)
            price = self.extract_price(box)
            mrp = self.extract_mrp(box)

            p = self.clean_price(price)
            m = self.clean_price(mrp)
            if p == 0 or m == 0 or p > m:
                continue

            deal = {
                "id": self.generate_id(title),
                "title": title,
                "image": image,
                "price": price,
                "mrp": mrp,
                "discount": self.extract_discount(box, price, mrp),
                "platform": self.detect_platform(link, image),
                "original_link": link,
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }

            deals.append(deal)
            print(f"✔ {title[:40]} → {deal['platform']}")

        return deals

    # ---------------- SAVE ----------------
    def save_raw_only(self, deals):
        with open(self.raw_file, "w", encoding="utf-8") as f:
            json.dump(deals, f, indent=2, ensure_ascii=False)
        print(f"💾 RAW saved: {len(deals)} deals")

    def close(self):
        self.driver.quit()


def main():
    bot = DealScraper()
    deals = bot.scrape()
    bot.save_raw_only(deals)
    bot.close()


if __name__ == "__main__":
    main()
