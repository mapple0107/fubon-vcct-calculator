"""
富邦人壽真豐利變額年金保險（VCCT）月配息自動計算器
自動抓取所有基金清單 + 淨值 + 配息資料
=====================================================
安裝依賴套件：
    pip3 install requests beautifulsoup4

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

# 商品代碼（您持有的保險商品）
PRODUCT = "VCCT"

# 只顯示有配息資料的基金（True=只顯示有配息, False=全部顯示）
ONLY_WITH_DIST = True

# 最多爬取幾檔基金（None = 全部，數字 = 限制數量，節省時間）
MAX_FUNDS = None
# ────────────────────────────────────────────────────────────────

BASE    = "https://invest.fubonlife.com.tw"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Referer": BASE + "/",
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


def get_all_fund_codes():
    """
    從國內基金列表頁（wr01）和海外基金列表頁（wb01）
    抓取所有基金的代碼與名稱。
    富邦的基金清單頁在導覽列 <select> 或 <a> 連結中包含所有基金代碼。
    """
    import requests
    from bs4 import BeautifulSoup

    funds = []
    seen  = set()

    sources = [
        # (類型, 列表頁URL, 淨值頁前綴, 配息頁前綴)
        ("domestic", f"{BASE}/w/wr/wr01.djhtm?product={PRODUCT}", "wr", "wr"),
        ("overseas", f"{BASE}/w/wb/wb01.djhtm?product={PRODUCT}", "wb", "wb"),
    ]

    for fund_type, url, nav_prefix, dist_prefix in sources:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.encoding = "big5"
            soup = BeautifulSoup(resp.text, "html.parser")

            # 從頁面所有連結中抓取含基金代碼的 URL
            # 格式：/w/wr/wr01.djhtm?a=ACAI168-PBE2&product=VCCT
            for a in soup.find_all("a", href=True):
                href = a["href"]
                m = re.search(r"a=([A-Z0-9]+-[A-Z0-9]+)&product=", href)
                if m:
                    code = m.group(1)
                    if code not in seen:
                        seen.add(code)
                        name = a.get_text(strip=True) or code
                        funds.append({
                            "code":        code,
                            "name":        name,
                            "type":        fund_type,
                            "nav_prefix":  nav_prefix,
                            "dist_prefix": dist_prefix,
                        })

            # 也從下拉選單 <option> 抓
            for opt in soup.find_all("option"):
                val = opt.get("value", "")
                m = re.search(r"a=([A-Z0-9]+-[A-Z0-9]+)", val)
                if m:
                    code = m.group(1)
                    if code not in seen:
                        seen.add(code)
                        name = opt.get_text(strip=True) or code
                        funds.append({
                            "code":        code,
                            "name":        name,
                            "type":        fund_type,
                            "nav_prefix":  nav_prefix,
                            "dist_prefix": dist_prefix,
                        })

        except Exception as e:
            print(f"  ⚠️  無法取得{fund_type}基金清單：{e}")

    return funds


def fetch_nav(fund):
    """抓取基金最新淨值"""
    import requests
    from bs4 import BeautifulSoup

    p = fund["nav_prefix"]
    url = f"{BASE}/w/{p}/{p}02.djhtm?a={fund['code']}&product={PRODUCT}"

    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.encoding = "big5"
    soup = BeautifulSoup(resp.text, "html.parser")

    # 方法1：表格第一行日期+淨值
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = [td.get_text(strip=True) for td in row.find_all("td")]
            if len(cells) >= 2 and re.match(r"\d{4}/\d{2}/\d{2}", cells[0]):
                try:
                    return float(cells[1]), cells[0]
                except ValueError:
                    continue

    # 方法2：導覽連結中的最新淨值數字
    for a in soup.find_all("a", href=True):
        text = a.get_text(strip=True)
        if re.match(r"^\d+\.\d{2,6}$", text):
            try:
                return float(text), "最新"
            except ValueError:
                continue

    return None, None


def fetch_distribution(fund):
    """抓取最新每單位分配金額"""
    import requests
    from bs4 import BeautifulSoup

    p = fund["dist_prefix"]
    # 國內用 wr10，海外用 wb05
    page = "wr10" if p == "wr" else "wb05"
    url  = f"{BASE}/w/{p}/{page}.djhtm?a={fund['code']}&product={PRODUCT}"

    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.encoding = "big5"
    soup = BeautifulSoup(resp.text, "html.parser")

    # 從表格中找合理範圍內的小數（每單位分配金額）
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = [td.get_text(strip=True) for td in row.find_all("td")]
            for cell in cells:
                if re.match(r"^\d+\.\d{3,6}$", cell):
                    try:
                        val = float(cell)
                        if 0.001 < val < 100:
                            return val
                    except ValueError:
                        continue

    return None


def calculate(nav, dist, fund_name, premium=PREMIUM,
              fee_rate=FEE_RATE, usd_rate=USD_RATE):
    fee           = premium * fee_rate
    effective     = premium - fee
    usd_in        = effective / usd_rate
    units         = usd_in / nav
    monthly_usd   = units * dist
    monthly_twd   = monthly_usd * usd_rate
    yearly_twd    = monthly_twd * 12
    yield_rate    = (yearly_twd / effective) * 100
    return {
        "基金名稱":    fund_name,
        "淨值":        nav,
        "每單位分配":  dist,
        "月配息(USD)": monthly_usd,
        "月配息(TWD)": monthly_twd,
        "年配息(TWD)": yearly_twd,
        "年化報酬率":  yield_rate,
    }


def print_results(results):
    ranked = sorted(results, key=lambda x: x["年化報酬率"], reverse=True)
    medals = ["🥇", "🥈", "🥉"]

    print("\n" + "═" * 78)
    print("  📊 所有基金比較排行（依年化報酬率排序）")
    print(f"  保費 TWD {PREMIUM:,.0f}　費用率 {FEE_RATE*100:.0f}%　匯率 {USD_RATE}")
    print("═" * 78)
    print(f"  {'排名':<4} {'基金代碼':<12} {'淨值':>9} {'分配金額':>9} "
          f"{'月配息(TWD)':>12} {'年配息(TWD)':>12} {'報酬率':>8}")
    print(f"  {'─'*4} {'─'*12} {'─'*9} {'─'*9} {'─'*12} {'─'*12} {'─'*8}")

    for i, r in enumerate(ranked):
        medal = medals[i] if i < 3 else f" {i+1:>2}."
        print(
            f"  {medal:<4} "
            f"{r['基金名稱']:<12} "
            f"{r['淨值']:>9.4f} "
            f"{r['每單位分配']:>9.4f} "
            f"{r['月配息(TWD)']:>12,.0f} "
            f"{r['年配息(TWD)']:>12,.0f} "
            f"{r['年化報酬率']:>7.2f}%"
        )

    print("═" * 78)
    best = ranked[0]
    print(f"\n  🏆 最佳選擇：{best['基金名稱']}")
    print(f"     每月可領 TWD {best['月配息(TWD)']:,.0f}　"
          f"年化報酬率 {best['年化報酬率']:.2f}%")
    if len(ranked) > 1:
        worst = ranked[-1]
        diff  = best["月配息(TWD)"] - worst["月配息(TWD)"]
        print(f"     vs 最低 {worst['基金名稱']}：每月多 TWD {diff:,.0f}")
    print()


def main():
    print("═" * 60)
    print("  富邦 VCCT 月配息計算器｜全自動版")
    print("═" * 60)
    print(f"  商品代碼：{PRODUCT}")
    print(f"  保費：TWD {PREMIUM:,.0f}　費用率：{FEE_RATE*100:.1f}%　匯率：{USD_RATE}")
    print("═" * 60)

    check_dependencies()

    # 第一步：抓取所有基金代碼
    print(f"\n🔍 步驟 1｜自動取得 {PRODUCT} 所有基金清單...")
    all_funds = get_all_fund_codes()

    if not all_funds:
        print("❌ 無法取得基金清單，請確認網路連線或商品代碼是否正確。")
        sys.exit(1)

    if MAX_FUNDS:
        all_funds = all_funds[:MAX_FUNDS]

    print(f"✅ 共找到 {len(all_funds)} 檔基金\n")

    # 第二步：逐一抓取淨值與配息
    print(f"📡 步驟 2｜抓取各基金淨值與配息資料...")
    results = []
    skipped = 0

    for i, fund in enumerate(all_funds, 1):
        code = fund["code"]
        name = fund.get("name", code) or code
        # 名稱太長就截短，顯示用代碼
        display = code

        print(f"  [{i:>3}/{len(all_funds)}] {display:<14}", end=" ", flush=True)

        try:
            nav, date = fetch_nav(fund)
            if not nav:
                print("⚠️  無淨值")
                skipped += 1
                time.sleep(0.3)
                continue

            dist = fetch_distribution(fund)
            if not dist:
                if ONLY_WITH_DIST:
                    print(f"淨值={nav:.4f}  ⚠️  無配息資料，略過")
                    skipped += 1
                    time.sleep(0.3)
                    continue
                else:
                    dist = 0

            result = calculate(nav, dist, display)
            results.append(result)
            print(f"✅ 淨值={nav:.4f}  分配={dist:.4f}  "
                  f"月配息 TWD {result['月配息(TWD)']:,.0f}  "
                  f"報酬率 {result['年化報酬率']:.2f}%")

        except Exception as e:
            print(f"❌ {e}")
            skipped += 1

        time.sleep(0.4)   # 避免請求過快被封鎖

    print(f"\n✅ 完成｜成功 {len(results)} 檔，略過 {skipped} 檔")

    if not results:
        print("❌ 沒有取得任何有效資料。")
        return

    print_results(results)


if __name__ == "__main__":
    main()
