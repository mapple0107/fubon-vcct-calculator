"""
富邦 VCCT 月配息計算器
針對您持有的 5 檔基金，自動抓取淨值與配息並計算排行
=====================================================
安裝依賴套件：
    pip3 install selenium webdriver-manager

使用方式：
    python3 fubon_vcct_calculator.py
"""

import sys
import re
import time

# ── 使用者設定區 ────────────────────────────────────────────────
PREMIUM  = 1_000_000   # 保費（台幣）
FEE_RATE = 0.05        # 保費費用率（5% → 0.05）
USD_RATE = 31.4        # 美金匯率
PRODUCT  = "VCCT"      # 商品代碼

# 您持有的基金清單（名稱可自訂，代碼請勿修改）
# 若要新增基金：請至富邦網站找到基金頁面，複製網址中 a= 後的代碼
# 國內基金用 prefix="wr"，海外基金用 prefix="wb"
FUNDS = [
    {"name": "JFP11", "code": "JFP11-PBE2",     "prefix": "wb"},
    {"name": "ACC3",  "code": "ACC3-PBE2",       "prefix": "wb"},
    {"name": "IGB5",  "code": "IGB5-PBE2",       "prefix": "wb"},
    {"name": "FRP4",  "code": "FRP4-PBE2",       "prefix": "wb"},
    {"name": "DSP5",  "code": "ACAI168-PBE2",    "prefix": "wr"},
]
# ────────────────────────────────────────────────────────────────

BASE = "https://invest.fubonlife.com.tw"


def check_dependencies():
    missing = []
    for pkg in ["selenium", "webdriver_manager"]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        print("❌ 缺少套件，請先執行：")
        print(f"   pip3 install {' '.join(missing)}")
        sys.exit(1)


def make_driver():
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager

    opts = Options()
    opts.add_argument("--headless")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--ignore-certificate-errors")
    opts.add_argument("--window-size=1280,800")
    opts.add_argument(
        "user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    )
    svc = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=svc, options=opts)


def fetch_fund_data(driver, fund):
    """用 Selenium 抓取單一基金的淨值與配息"""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    p = fund["prefix"]

    # ── 抓淨值 ──
    nav_url = f"{BASE}/w/{p}/{p}02.djhtm?a={fund['code']}&product={PRODUCT}"
    driver.get(nav_url)
    nav, nav_date = None, None
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.TAG_NAME, "table"))
        )
        time.sleep(1)
        rows = driver.find_elements(By.CSS_SELECTOR, "table tr")
        for row in rows:
            cells = [td.text.strip() for td in row.find_elements(By.TAG_NAME, "td")]
            if len(cells) >= 2 and re.match(r"\d{2}/\d{2}|\d{4}/\d{2}/\d{2}", cells[0]):
                try:
                    nav = float(cells[1])
                    nav_date = cells[0]
                    break
                except ValueError:
                    continue
        # 備用：從導覽連結抓
        if not nav:
            for a in driver.find_elements(By.TAG_NAME, "a"):
                t = a.text.strip()
                if re.match(r"^\d+\.\d{2,6}$", t):
                    nav = float(t)
                    break
    except Exception:
        pass

    # ── 抓配息 ──
    dist_page = "wr10" if p == "wr" else "wb05"
    dist_url  = f"{BASE}/w/{p}/{dist_page}.djhtm?a={fund['code']}&product={PRODUCT}"
    driver.get(dist_url)
    dist = None
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.TAG_NAME, "table"))
        )
        time.sleep(1.5)   # 等 JS 渲染配息表格
        rows = driver.find_elements(By.CSS_SELECTOR, "table tr")
        for row in rows:
            cells = [td.text.strip() for td in row.find_elements(By.TAG_NAME, "td")]
            for cell in cells:
                if re.match(r"^\d+\.\d{3,6}$", cell):
                    val = float(cell)
                    if 0.001 < val < 100:
                        dist = val
                        break
            if dist:
                break
    except Exception:
        pass

    return nav, nav_date, dist


def calculate(nav, dist, name):
    fee       = PREMIUM * FEE_RATE
    effective = PREMIUM - fee
    usd_in    = effective / USD_RATE
    units     = usd_in / nav
    m_usd     = units * dist
    m_twd     = m_usd * USD_RATE
    y_twd     = m_twd * 12
    yield_r   = (y_twd / effective) * 100
    return {
        "基金名稱":    name,
        "淨值":        nav,
        "每單位分配":  dist,
        "月配息(TWD)": m_twd,
        "年配息(TWD)": y_twd,
        "年化報酬率":  yield_r,
    }


def print_results(results):
    ranked = sorted(results, key=lambda x: x["年化報酬率"], reverse=True)
    medals = ["🥇", "🥈", "🥉"]

    print("\n" + "═" * 76)
    print("  📊 基金比較排行（依年化報酬率排序）")
    print(f"  保費 TWD {PREMIUM:,.0f}　費用率 {FEE_RATE*100:.0f}%　匯率 {USD_RATE}")
    print("═" * 76)
    print(f"  {'排名':<4} {'基金名稱':<10} {'淨值':>10} {'分配金額':>9} "
          f"{'月配息(TWD)':>12} {'年配息(TWD)':>12} {'報酬率':>8}")
    print(f"  {'─'*4} {'─'*10} {'─'*10} {'─'*9} {'─'*12} {'─'*12} {'─'*8}")

    for i, r in enumerate(ranked):
        medal = medals[i] if i < 3 else f" {i+1:>2}."
        print(
            f"  {medal:<4} "
            f"{r['基金名稱']:<10} "
            f"{r['淨值']:>10.4f} "
            f"{r['每單位分配']:>9.4f} "
            f"{r['月配息(TWD)']:>12,.0f} "
            f"{r['年配息(TWD)']:>12,.0f} "
            f"{r['年化報酬率']:>7.2f}%"
        )

    print("═" * 76)
    best = ranked[0]
    print(f"\n  🏆 最佳選擇：{best['基金名稱']}")
    print(f"     每月可領 TWD {best['月配息(TWD)']:,.0f}　"
          f"年化報酬率 {best['年化報酬率']:.2f}%")
    if len(ranked) > 1:
        diff = best["月配息(TWD)"] - ranked[-1]["月配息(TWD)"]
        print(f"     vs 最低 {ranked[-1]['基金名稱']}：每月多 TWD {diff:,.0f}")
    print()


def main():
    print("═" * 60)
    print("  富邦 VCCT 月配息計算器")
    print("═" * 60)
    print(f"  保費：TWD {PREMIUM:,.0f}　費用率：{FEE_RATE*100:.1f}%　匯率：{USD_RATE}")
    print(f"  共 {len(FUNDS)} 檔基金待查詢")
    print("═" * 60)

    check_dependencies()

    print("\n🌐 啟動瀏覽器...")
    driver = make_driver()
    results = []
    errors  = []

    try:
        for i, fund in enumerate(FUNDS, 1):
            print(f"  [{i}/{len(FUNDS)}] {fund['name']:<10}", end=" ", flush=True)
            nav, nav_date, dist = fetch_fund_data(driver, fund)

            if nav and dist:
                r = calculate(nav, dist, fund["name"])
                results.append(r)
                print(f"✅ 淨值={nav:.4f}  分配={dist:.4f}  "
                      f"月配息 TWD {r['月配息(TWD)']:,.0f}  "
                      f"報酬率 {r['年化報酬率']:.2f}%")
            elif nav and not dist:
                print(f"⚠️  淨值={nav:.4f}  但無配息資料")
                errors.append(fund["name"])
            else:
                print("❌ 無法取得資料")
                errors.append(fund["name"])

    finally:
        driver.quit()
        print("🔒 瀏覽器已關閉")

    if errors:
        print(f"\n⚠️  以下基金代碼可能需要更新：{', '.join(errors)}")
        print("   請至富邦網站查詢正確代碼後更新程式頂部的 FUNDS 清單")

    if not results:
        print("\n❌ 沒有取得任何有效資料。")
        return

    print_results(results)


if __name__ == "__main__":
    main()
