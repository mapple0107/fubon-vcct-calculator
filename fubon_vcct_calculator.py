"""
富邦人壽真豐利變額年金保險（VCCT）月配息自動計算器
=====================================================
自動從富邦網站爬取基金淨值與每單位分配金額，並計算配息。

安裝依賴套件：
    pip install requests beautifulsoup4 selenium webdriver-manager

使用方式：
    python fubon_vcct_calculator.py

注意：富邦網站為動態 JavaScript 渲染，需使用 Selenium。
"""

import time
import sys

# ── 使用者設定區 ────────────────────────────────────────────────
PREMIUM       = 1_000_000   # 保費（台幣）
FEE_RATE      = 0.05        # 保費費用率（5% → 0.05）
USD_RATE      = 31.4        # 美金匯率

# 富邦 VCCT 基金名稱關鍵字（用來篩選您持有的基金）
# 留空 "" 則列出全部基金
FUND_KEYWORD  = ""
# ────────────────────────────────────────────────────────────────

FUBON_URL = "https://invest.fubonlife.com.tw/index.html"


def check_dependencies():
    """檢查必要套件是否已安裝"""
    missing = []
    for pkg in ["requests", "bs4", "selenium", "webdriver_manager"]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        print("❌ 缺少套件，請先執行：")
        print(f"   pip install {' '.join(missing)}")
        sys.exit(1)


def fetch_fund_data_selenium():
    """使用 Selenium 爬取富邦網站的基金數據"""
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from webdriver_manager.chrome import ChromeDriverManager

    print("🌐 啟動瀏覽器，連線至富邦網站...")

    options = Options()
    options.add_argument("--headless")          # 背景執行（不顯示視窗）
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    funds = []
    try:
        driver.get(FUBON_URL)
        print("⏳ 等待頁面載入...")

        # 等待基金表格出現（最多 20 秒）
        wait = WebDriverWait(driver, 20)

        # 嘗試多種可能的表格選擇器
        selectors = [
            "table",
            ".fund-table",
            "[class*='fund']",
            "[class*='table']",
        ]

        table_found = False
        for sel in selectors:
            try:
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, sel)))
                table_found = True
                break
            except Exception:
                continue

        if not table_found:
            time.sleep(5)   # 額外等待 JS 渲染

        # 取得頁面原始碼交給 BeautifulSoup 解析
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(driver.page_source, "html.parser")

        # 解析所有表格
        tables = soup.find_all("table")
        print(f"📊 找到 {len(tables)} 個資料表格")

        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
                if len(cells) < 3:
                    continue

                # 嘗試識別含有基金名稱、淨值、分配金額的行
                row_text = " ".join(cells)
                if any(kw in row_text for kw in ["淨值", "分配", "NAV", "基金"]):
                    funds.append(cells)

        # 若無法從表格取得，嘗試直接搜尋包含數字的基金相關元素
        if not funds:
            fund_elements = soup.find_all(
                attrs={"class": lambda c: c and any(
                    kw in c.lower() for kw in ["fund", "nav", "dist", "基金"]
                ) if c else False}
            )
            for el in fund_elements:
                text = el.get_text(strip=True)
                if text:
                    funds.append([text])

    finally:
        driver.quit()

    return funds


def parse_fund_info(raw_data):
    """從爬取的原始資料中解析基金淨值與分配金額"""
    import re

    parsed = []
    nav_pattern      = re.compile(r"\d+\.\d{2,6}")
    percent_pattern  = re.compile(r"\d+\.?\d*%")

    for row in raw_data:
        row_str = " | ".join(str(c) for c in row)

        # 篩選基金關鍵字
        if FUND_KEYWORD and FUND_KEYWORD not in row_str:
            continue

        numbers = nav_pattern.findall(row_str)
        if len(numbers) >= 2:
            parsed.append({
                "raw":  row_str,
                "nums": numbers,
            })

    return parsed


def calculate(nav, dist_per_unit, premium=PREMIUM,
              fee_rate=FEE_RATE, usd_rate=USD_RATE):
    """計算配息金額與報酬率"""
    fee_cost          = premium * fee_rate
    effective_premium = premium - fee_cost
    usd_invested      = effective_premium / usd_rate
    units             = usd_invested / nav
    monthly_usd       = units * dist_per_unit
    monthly_twd       = monthly_usd * usd_rate
    yearly_twd        = monthly_twd * 12
    yield_rate        = (yearly_twd / effective_premium) * 100

    return {
        "保費（台幣）":           premium,
        "保費費用":               fee_cost,
        "實際投入保費（台幣）":   effective_premium,
        "換算美金投入":           usd_invested,
        "可購買單位數":           units,
        "基金單位淨值（美金）":   nav,
        "每單位分配金額（美金）": dist_per_unit,
        "每月配息（美金）":       monthly_usd,
        "每月配息（台幣）":       monthly_twd,
        "每年配息（台幣）":       yearly_twd,
        "年化報酬率":             yield_rate,
    }


def print_result(result):
    """格式化輸出計算結果"""
    print("\n" + "═" * 50)
    print("  富邦 VCCT 月配息計算結果")
    print("═" * 50)
    for k, v in result.items():
        if "率" in k:
            print(f"  {k:<20} {v:.2f}%")
        elif "美金" in k or "USD" in k:
            print(f"  {k:<20} USD {v:>12,.2f}")
        elif "單位" in k and "淨值" not in k and "分配" not in k:
            print(f"  {k:<20} {v:>12,.4f} 單位")
        else:
            print(f"  {k:<20} TWD {v:>12,.0f}")
    print("═" * 50)


def manual_mode():
    """手動輸入模式（備用）"""
    print("\n📝 手動輸入模式")
    print("─" * 40)
    try:
        nav           = float(input("請輸入基金單位淨值（美金）："))
        dist_per_unit = float(input("請輸入每單位分配金額（美金）："))
    except ValueError:
        print("❌ 輸入格式錯誤，請輸入數字。")
        sys.exit(1)

    result = calculate(nav, dist_per_unit)
    print_result(result)


def main():
    print("=" * 50)
    print("  富邦 VCCT 月配息自動計算器")
    print("=" * 50)
    print(f"  保費：TWD {PREMIUM:,.0f}")
    print(f"  費用率：{FEE_RATE*100:.1f}%")
    print(f"  美金匯率：{USD_RATE}")
    print("=" * 50)

    # 檢查依賴
    check_dependencies()

    # 嘗試自動爬取
    auto_success = False
    try:
        raw_data   = fetch_fund_data_selenium()
        parsed     = parse_fund_info(raw_data)

        if parsed:
            print(f"\n✅ 成功取得 {len(parsed)} 筆基金資料\n")
            for i, fund in enumerate(parsed):
                print(f"[{i+1}] {fund['raw'][:80]}")
                print(f"     數值：{fund['nums']}")

            # 若只有一筆，直接使用；多筆則讓使用者選擇
            if len(parsed) == 1:
                idx = 0
            else:
                print()
                idx_str = input("請選擇要計算的基金編號（輸入數字）：")
                idx     = int(idx_str) - 1

            nums          = parsed[idx]["nums"]
            nav           = float(nums[0])
            dist_per_unit = float(nums[1])

            print(f"\n📌 使用資料：淨值 {nav}，每單位分配 {dist_per_unit}")
            result = calculate(nav, dist_per_unit)
            print_result(result)
            auto_success = True
        else:
            print("⚠️  自動解析未找到基金資料，切換至手動模式...")

    except Exception as e:
        print(f"⚠️  自動爬取失敗：{e}")
        print("   切換至手動輸入模式...")

    if not auto_success:
        manual_mode()


if __name__ == "__main__":
    main()
