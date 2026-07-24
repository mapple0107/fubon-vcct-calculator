"""
富邦 VCCT 月配息計算器
針對您持有的 8 檔基金，自動抓取淨值與配息並計算排行
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

# 網址解析規則：
# $W$WB$WB01]DJHTM{A}JF^N3-JFP11 → prefix=wb, code=JFN3-JFP11  (^=英文字母，需對照)
# $W$WR$WR01]DJHTM{A}ACTI71-ACC3 → prefix=wr, code=ACTI71-ACC3
# ^ 符號代表特殊字元編碼，實際代碼需從網站確認
# 以下為正確解析後的代碼：
FUNDS = [
    {"name": "JFP11", "code": "JFZN3-JFP11",  "prefix": "wb"},  # $W$WB → wb, JF^N3 → JFN3
    {"name": "ACC3",  "code": "ACTI71-ACC3",     "prefix": "wr"},  # $W$WR → wr
    {"name": "IGB5",  "code": "CTZP0-IGB5",  "prefix": "wb"},  # CT^P0 → CTP0
    {"name": "FRP4",  "code": "FLZ92-FRP4",  "prefix": "wb"},  # FL^92 → FL92
    {"name": "DSP5",  "code": "TLZ64-DSP5",  "prefix": "wb"},  # TL^64 → TL64
    {"name": "SCP6",  "code": "PYZW3-SCP6",  "prefix": "wb"},  # PY^W3 → PYW3
    {"name": "ESC1",  "code": "ACCP138-ESC1",    "prefix": "wr"},  # $W$WR → wr
    {"name": "MLE24", "code": "SHZV9-MLE24", "prefix": "wb"},  # SH^V9 → SHV9
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
        time.sleep(1.5)
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
        if not nav:
            for a in driver.find_elements(By.TAG_NAME, "a"):
                t = a.text.strip()
                if re.match(r"^\d+\.\d{2,6}$", t):
                    try:
                        nav = float(t)
                        break
                    except ValueError:
                        continue
    except Exception:
        pass

    # 確認是否被導向預設頁（淨值 = 7.94 是預設值）
    if nav == 7.94 or nav == 7.9400:
        nav = None

    # ── 抓配息 ──
    dist_page = "wr10" if p == "wr" else "wb05"
    dist_url  = f"{BASE}/w/{p}/{dist_page}.djhtm?a={fund['code']}&product={PRODUCT}"
    driver.get(dist_url)
    dist = None
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.TAG_NAME, "table"))
        )
        time.sleep(2)
        rows = driver.find_elements(By.CSS_SELECTOR, "table tr")
        for row in rows:
            cells = [td.text.strip() for td in row.find_elements(By.TAG_NAME, "td")]
            for cell in cells:
                if re.match(r"^\d+\.\d{3,6}$", cell):
                    try:
                        val = float(cell)
                        if 0.001 < val < 100:
                            dist = val
                            break
                    except ValueError:
                        continue
            if dist:
                break
    except Exception:
        pass

    return nav, nav_date, dist


def diagnose_url(driver, fund):
    """診斷用：直接抓取頁面標題確認代碼是否正確"""
    from selenium.webdriver.common.by import By
    p   = fund["prefix"]
    url = f"{BASE}/w/{p}/{p}01.djhtm?a={fund['code']}&product={PRODUCT}"
    driver.get(url)
    time.sleep(2)
    try:
        h3 = driver.find_elements(By.TAG_NAME, "h3")
        if h3:
            return h3[0].text.strip()
    except Exception:
        pass
    return driver.title


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



def update_html(results, html_path):
    """把最新淨值和分配金額寫入 index.html"""
    import re

    with open(html_path, "r", encoding="utf-8") as f:
        content = f.read()

    updated = False
    for r in results:
        name = r["基金名稱"]
        nav  = r["淨值"]
        dist = r["每單位分配"]

        # 比對 PRESET_FUNDS 陣列中的基金，更新 nav 和 dist
        # 格式彈性：name:"JFP11", label:"...", nav:任意數字, dist:任意數字
        pattern = r'(name:"' + re.escape(name) + r'"[^}]*?nav:)([\d.]+)([^}]*?dist:)([\d.]+)'
        replacement = rf'\g<1>{nav}\g<3>{dist}'
        new_content = re.sub(pattern, replacement, content)

        if new_content != content:
            content = new_content
            updated = True
            print(f"  ✅ {name}：淨值={nav}，分配={dist}")
        else:
            print(f"  ⚠️  {name}：找不到對應欄位，略過")

    if updated:
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(content)
    return updated


def push_to_github(repo_name, html_path, token, username, date_str):
    """把更新後的 index.html 推送到 GitHub"""
    import base64
    import urllib.request
    import json

    with open(html_path, "rb") as f:
        content_b64 = base64.b64encode(f.read()).decode("utf-8")

    # 取得目前 SHA
    url = f"https://api.github.com/repos/{username}/{repo_name}/contents/index.html"
    req = urllib.request.Request(url, headers={
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    })
    with urllib.request.urlopen(req) as resp:
        sha = json.loads(resp.read())["sha"]

    # 推送新版本
    data = json.dumps({
        "message": f"自動更新基金淨值 {date_str}",
        "content": content_b64,
        "sha": sha
    }).encode("utf-8")

    req = urllib.request.Request(url, data=data, method="PUT", headers={
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json"
    })
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read())
        if "content" in result:
            print(f"  ✅ {repo_name} 推送成功")
        else:
            print(f"  ❌ {repo_name} 推送失敗")


def auto_update_web(results):
    """自動更新兩個網頁並推送到 GitHub"""
    import os
    from datetime import datetime
    if not TOKEN:
        print("❌ 請設定環境變數 GITHUB_TOKEN")
        return

    TOKEN    = os.environ.get("GITHUB_TOKEN", "")
    USERNAME = "mapple0107"
    REPOS    = ["fubon-vcct-calculator", "fubon-calculator"]
    DATE_STR = datetime.now().strftime("%Y-%m-%d")
    TMP_HTML = "/tmp/index_updated.html"

    print("\n🌐 開始更新網頁...")

    for repo in REPOS:
        print(f"\n  📄 {repo}")

        # 從 GitHub 下載最新 index.html
        import urllib.request, json, base64
        url = f"https://api.github.com/repos/{USERNAME}/{repo}/contents/index.html"
        req = urllib.request.Request(url, headers={
            "Authorization": f"token {TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        })
        with urllib.request.urlopen(req) as resp:
            r = json.loads(resp.read())
            html_content = base64.b64decode(r["content"]).decode("utf-8")

        with open(TMP_HTML, "w", encoding="utf-8") as f:
            f.write(html_content)

        # 更新淨值
        updated = update_html(results, TMP_HTML)

        if updated:
            push_to_github(repo, TMP_HTML, TOKEN, USERNAME, DATE_STR)
        else:
            print(f"  ℹ️  {repo} 無變動，略過")

    print("\n✅ 網頁更新完成！")

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
            print(f"  [{i}/{len(FUNDS)}] {fund['name']:<8}", end=" ", flush=True)
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
                # 診斷：印出頁面標題
                title = diagnose_url(driver, fund)
                print(f"❌ 代碼可能錯誤 → 頁面標題：{title[:40]}")
                errors.append(fund["name"])

    finally:
        driver.quit()
        print("\n🔒 瀏覽器已關閉")

    if errors:
        print(f"\n⚠️  以下基金需確認代碼：{', '.join(errors)}")

    if not results:
        print("\n❌ 沒有取得任何有效資料。")
        return

    print_results(results)
    auto_update_web(results)


if __name__ == "__main__":
    main()


# ══════════════════════════════════════════════════
# 自動更新網頁並推送到 GitHub
# ══════════════════════════════════════════════════