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
import urllib3

# 關閉 SSL 憑證警告（富邦網站憑證問題）
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ── 使用者設定區 ────────────────────────────────────────────────
PREMIUM  = 1_000_000   # 保費（台幣）
FEE_RATE = 0.05        # 保費費用率（5% → 0.05）
USD_RATE = 31.4        # 美金匯率
PRODUCT  = "VCCT"      # 商品代碼
ONLY_WITH_DIST = True  # True=只顯示有配息的基金
MAX_FUNDS = None       # None=全部，數字=限制筆數（例：10）
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


def get(url):
    """統一的 HTTP 請求，關閉 SSL 驗證"""
    import requests
    resp = requests.get(url, headers=HEADERS, timeout=15, verify=False)
    resp.encoding = "big5"
    return resp


def get_all_fund_codes():
    """從國內/海外基金列表頁抓取所有基金代碼"""
    from bs4 import BeautifulSoup

    funds = []
    seen  = set()

    sources = [
        ("domestic", f"{BASE}/w/wr/wr01.djhtm?product={PRODUCT}", "wr"),
        ("overseas", f"{BASE}/w/wb/wb01.djhtm?product={PRODUCT}", "wb"),
    ]

    for fund_type, url, prefix in sources:
        try:
            soup = BeautifulSoup(get(url).text, "html.parser")

            # 從所有 <a> 連結抓含基金代碼的 URL
            for a in soup.find_all("a", href=True):
                m = re.search(r"a=([A-Z0-9]+-[A-Z0-9]+)&product=", a["href"])
                if m:
                    code = m.group(1)
                    if code not in seen:
                        seen.add(code)
                        funds.append({
                            "code":   code,
                            "name":   a.get_text(strip=True) or code,
                            "type":   fund_type,
                            "prefix": prefix,
                        })

            # 從下拉選單 <option> 抓
            for opt in soup.find_all("option"):
                m = re.search(r"a=([A-Z0-9]+-[A-Z0-9]+)", opt.get("value", ""))
                if m:
                    code = m.group(1)
                    if code not in seen:
                        seen.add(code)
                        funds.append({
                            "code":   code,
                            "name":   opt.get_text(strip=True) or code,
                            "type":   fund_type,
                            "prefix": prefix,
                        })

        except Exception as e:
            print(f"  ⚠️  無法取得{fund_type}基金清單：{e}")

    return funds


def fetch_nav(fund):
    """抓取基金最新淨值"""
    from bs4 import BeautifulSoup
    p   = fund["prefix"]
    url = f"{BASE}/w/{p}/{p}02.djhtm?a={fund['code']}&product={PRODUCT}"
    soup = BeautifulSoup(get(url).text, "html.parser")

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
    from bs4 import BeautifulSoup
    p    = fund["prefix"]
    page = "wr10" if p == "wr" else "wb05"
    url  = f"{BASE}/w/{p}/{page}.djhtm?a={fund['code']}&product={PRODUCT}"
    soup = BeautifulSoup(get(url).text, "html.parser")

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

    print("\n" + "═" * 78)
    print("  📊 所有基金比較排行（依年化報酬率排序）")
    print(f"  保費 TWD {PREMIUM:,.0f}　費用率 {FEE_RATE*100:.0f}%　匯率 {USD_RATE}")
    print("═" * 78)
    print(f"  {'排名':<4} {'基金代碼':<14} {'淨值':>9} {'分配金額':>9} "
          f"{'月配息(TWD)':>12} {'年配息(TWD)':>12} {'報酬率':>8}")
    print(f"  {'─'*4} {'─'*14} {'─'*9} {'─'*9} {'─'*12} {'─'*12} {'─'*8}")

    for i, r in enumerate(ranked):
        medal = medals[i] if i < 3 else f" {i+1:>2}."
        print(
            f"  {medal:<4} "
            f"{r['基金名稱']:<14} "
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
        diff = best["月配息(TWD)"] - ranked[-1]["月配息(TWD)"]
        print(f"     vs 最低 {ranked[-1]['基金名稱']}：每月多 TWD {diff:,.0f}")
    print()


def main():
    print("═" * 60)
    print("  富邦 VCCT 月配息計算器｜全自動版")
    print("═" * 60)
    print(f"  商品代碼：{PRODUCT}")
    print(f"  保費：TWD {PREMIUM:,.0f}　費用率：{FEE_RATE*100:.1f}%　匯率：{USD_RATE}")
    print("═" * 60)

    check_dependencies()

    # 第一步：取得所有基金代碼
    print(f"\n🔍 步驟 1｜自動取得 {PRODUCT} 所有基金清單...")
    all_funds = get_all_fund_codes()

    if not all_funds:
        print("❌ 無法取得基金清單，請確認網路連線。")
        sys.exit(1)

    if MAX_FUNDS:
        all_funds = all_funds[:MAX_FUNDS]

    print(f"✅ 共找到 {len(all_funds)} 檔基金\n")

    # 第二步：逐一抓取淨值與配息
    print("📡 步驟 2｜抓取各基金淨值與配息資料...")
    results = []
    skipped = 0

    for i, fund in enumerate(all_funds, 1):
        code = fund["code"]
        print(f"  [{i:>3}/{len(all_funds)}] {code:<16}", end=" ", flush=True)

        try:
            nav, date = fetch_nav(fund)
            if not nav:
                print("⚠️  無淨值，略過")
                skipped += 1
                time.sleep(0.3)
                continue

            dist = fetch_distribution(fund)
            if not dist:
                if ONLY_WITH_DIST:
                    print(f"淨值={nav:.4f}  ⚠️  無配息，略過")
                    skipped += 1
                    time.sleep(0.3)
                    continue
                else:
                    dist = 0

            r = calculate(nav, dist, code)
            results.append(r)
            print(f"✅ 淨值={nav:.4f}  分配={dist:.4f}  "
                  f"月配息 TWD {r['月配息(TWD)']:,.0f}  "
                  f"報酬率 {r['年化報酬率']:.2f}%")

        except Exception as e:
            print(f"❌ {str(e)[:60]}")
            skipped += 1

        time.sleep(0.4)

    print(f"\n✅ 完成｜成功 {len(results)} 檔，略過 {skipped} 檔")

    if not results:
        print("❌ 沒有取得任何有效資料。")
        return

    print_results(results)


if __name__ == "__main__":
    main()
