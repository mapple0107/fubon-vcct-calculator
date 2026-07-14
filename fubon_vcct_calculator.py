"""
富邦人壽真豐利變額年金保險（VCCT）月配息自動計算器
使用直接網址爬取，不需要 Selenium
=====================================================
安裝依賴套件：
    pip3 install requests beautifulsoup4

使用方式：
    python3 fubon_vcct_calculator.py
"""

import sys
import re

# ── 使用者設定區 ────────────────────────────────────────────────
PREMIUM   = 1_000_000   # 保費（台幣）
FEE_RATE  = 0.05        # 保費費用率（5% → 0.05）
USD_RATE  = 31.4        # 美金匯率

# 您要查詢的基金代碼清單（格式：基金代碼-商品代碼）
# 請至富邦網站查詢您的基金代碼，填入下方
# 範例：
#   VCCT 商品代碼 → product=VCCT
#   基金代碼 → a=ACAI168-PBE2
FUNDS = [
    {"name": "DSP5", "code": "ACAI168-PBE2", "product": "VCCT"},
    # 新增更多基金，格式如下：
    # {"name": "基金名稱", "code": "基金代碼", "product": "商品代碼"},
]
# ────────────────────────────────────────────────────────────────

BASE_URL = "https://invest.fubonlife.com.tw/w/wr"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://invest.fubonlife.com.tw/",
    "Accept-Language": "zh-TW,zh;q=0.9",
}


def check_dependencies():
    missing = []
    for pkg in ["requests", "bs4"]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        print("❌ 缺少套件，請先執行：")
        print(f"   pip3 install {' '.join(missing)}")
        sys.exit(1)


def fetch_nav(fund):
    """抓取基金單位淨值（wr02 頁面）"""
    import requests
    from bs4 import BeautifulSoup

    url = f"{BASE_URL}/wr02.djhtm?a={fund['code']}&product={fund['product']}"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.encoding = "big5"
    soup = BeautifulSoup(resp.text, "html.parser")

    # 找最新淨值：頁面標題連結包含最新淨值數字
    nav = None

    # 方法1：找表格第一行的淨值
    tables = soup.find_all("table")
    for table in tables:
        rows = table.find_all("tr")
        for row in rows:
            cells = [td.get_text(strip=True) for td in row.find_all("td")]
            if len(cells) >= 2:
                # 日期格式 YYYY/MM/DD + 數字
                if re.match(r"\d{4}/\d{2}/\d{2}", cells[0]):
                    try:
                        nav = float(cells[1])
                        date = cells[0]
                        return nav, date
                    except (ValueError, IndexError):
                        continue

    # 方法2：從頁面中找 a 標籤內的數字（頁面導覽列顯示最新淨值）
    for a in soup.find_all("a"):
        text = a.get_text(strip=True)
        if re.match(r"^\d+\.\d{2,4}$", text):
            try:
                nav = float(text)
                return nav, "最新"
            except ValueError:
                continue

    return None, None


def fetch_distribution(fund):
    """抓取每單位分配金額（wr10 配息資訊頁面）"""
    import requests
    from bs4 import BeautifulSoup

    url = f"{BASE_URL}/wr10.djhtm?a={fund['code']}&product={fund['product']}"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.encoding = "big5"
    soup = BeautifulSoup(resp.text, "html.parser")

    dist = None
    tables = soup.find_all("table")
    for table in tables:
        rows = table.find_all("tr")
        for row in rows:
            cells = [td.get_text(strip=True) for td in row.find_all("td")]
            # 配息表格通常有：基準日、每單位分配金額、...
            if len(cells) >= 2:
                for cell in cells:
                    # 找小數點後4位的小數（每單位分配金額格式）
                    if re.match(r"^0\.\d{3,4}$", cell) or re.match(r"^\d+\.\d{3,4}$", cell):
                        try:
                            val = float(cell)
                            if 0 < val < 10:  # 合理範圍
                                dist = val
                                return dist
                        except ValueError:
                            continue
    return dist


def calculate(nav, dist_per_unit, fund_name="基金",
              premium=PREMIUM, fee_rate=FEE_RATE, usd_rate=USD_RATE):
    fee_cost          = premium * fee_rate
    effective_premium = premium - fee_cost
    usd_invested      = effective_premium / usd_rate
    units             = usd_invested / nav
    monthly_usd       = units * dist_per_unit
    monthly_twd       = monthly_usd * usd_rate
    yearly_twd        = monthly_twd * 12
    yield_rate        = (yearly_twd / effective_premium) * 100

    return {
        "基金名稱":               fund_name,
        "基金單位淨值（美金）":   nav,
        "每單位分配金額（美金）": dist_per_unit,
        "每月配息（美金）":       monthly_usd,
        "每月配息（台幣）":       monthly_twd,
        "每年配息（台幣）":       yearly_twd,
        "年化報酬率":             yield_rate,
    }


def print_comparison(results):
    sorted_r = sorted(results, key=lambda x: x["年化報酬率"], reverse=True)
    medals = ["🥇", "🥈", "🥉"]

    print("\n" + "═" * 70)
    print("  📊 多檔基金比較排行（依年化報酬率排序）")
    print("═" * 70)
    print(f"  {'排名':<4} {'基金名稱':<16} {'淨值':>8} {'分配金額':>8} "
          f"{'月配息(TWD)':>12} {'年配息(TWD)':>12} {'報酬率':>8}")
    print(f"  {'─'*4} {'─'*16} {'─'*8} {'─'*8} {'─'*12} {'─'*12} {'─'*8}")

    for i, r in enumerate(sorted_r):
        medal = medals[i] if i < 3 else f"  {i+1}."
        print(
            f"  {medal:<4} "
            f"{r['基金名稱']:<16} "
            f"{r['基金單位淨值（美金）']:>8.4f} "
            f"{r['每單位分配金額（美金）']:>8.4f} "
            f"{r['每月配息（台幣）']:>12,.0f} "
            f"{r['每年配息（台幣）']:>12,.0f} "
            f"{r['年化報酬率']:>7.2f}%"
        )

    print("═" * 70)
    best = sorted_r[0]
    print(f"\n  🏆 最佳選擇：{best['基金名稱']}")
    print(f"     每月可領 TWD {best['每月配息（台幣）']:,.0f}，"
          f"年化報酬率 {best['年化報酬率']:.2f}%\n")


def manual_input_fund(index):
    print(f"\n── 第 {index} 檔基金（手動輸入）──────────────────")
    name = input("  基金名稱：").strip() or f"基金{index}"
    try:
        nav  = float(input("  基金單位淨值（美金）："))
        dist = float(input("  每單位分配金額（美金）："))
    except ValueError:
        print("  ❌ 輸入錯誤")
        return None
    return calculate(nav, dist, fund_name=name)


def main():
    print("═" * 60)
    print("  富邦 VCCT 月配息自動計算器")
    print("═" * 60)
    print(f"  保費：TWD {PREMIUM:,.0f}　費用率：{FEE_RATE*100:.1f}%　匯率：{USD_RATE}")
    print("═" * 60)

    check_dependencies()

    results = []

    # ── 自動爬取設定檔中的基金 ──
    if FUNDS:
        print(f"\n🌐 自動爬取 {len(FUNDS)} 檔基金資料...")
        for fund in FUNDS:
            print(f"  ⏳ {fund['name']}...", end=" ", flush=True)
            try:
                nav, date = fetch_nav(fund)
                dist      = fetch_distribution(fund)
                if nav and dist:
                    print(f"✅ 淨值={nav}，分配={dist}")
                    results.append(calculate(nav, dist, fund_name=fund["name"]))
                else:
                    print(f"⚠️  無法取得完整資料（淨值={nav}, 分配={dist}），改為手動輸入")
                    r = manual_input_fund(len(results)+1)
                    if r:
                        results.append(r)
            except Exception as e:
                print(f"❌ 錯誤：{e}，改為手動輸入")
                r = manual_input_fund(len(results)+1)
                if r:
                    results.append(r)

    # ── 是否繼續新增手動基金 ──
    while True:
        more = input("\n➕ 是否新增更多基金比較？（y/n）：").strip().lower()
        if more == "y":
            r = manual_input_fund(len(results)+1)
            if r:
                results.append(r)
        else:
            break

    if not results:
        print("❌ 沒有有效的基金資料。")
        return

    if len(results) == 1:
        r = results[0]
        print("\n" + "═" * 50)
        print("  富邦 VCCT 月配息計算結果")
        print("═" * 50)
        for k, v in r.items():
            if "率" in k:
                print(f"  {k:<22} {v:.2f}%")
            elif "美金" in k:
                print(f"  {k:<22} USD {v:>10.2f}")
            elif "單位" in k and "淨值" not in k and "分配" not in k:
                print(f"  {k:<22} {v:>10.4f} 單位")
            elif k != "基金名稱":
                print(f"  {k:<22} TWD {v:>10,.0f}")
        print("═" * 50)
    else:
        print_comparison(results)


if __name__ == "__main__":
    main()
