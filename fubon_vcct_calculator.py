"""
富邦 VCCT 月配息計算器 - 完整版
自動爬取基金淨值並更新網頁
"""
import sys, re, time, os, ssl, base64, json
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ── 設定 ────────────────────────────────────────
PREMIUM  = 1_000_000
FEE_RATE = 0.05
USD_RATE = 31.4
PRODUCT  = "VCCT"
FUNDS = [
    {"name": "JFP11", "code": "JFZN3-JFP11",  "prefix": "wb"},
    {"name": "ACC3",  "code": "ACTI71-ACC3",   "prefix": "wr"},
    {"name": "IGB5",  "code": "CTZP0-IGB5",    "prefix": "wb"},
    {"name": "FRP4",  "code": "FLZ92-FRP4",    "prefix": "wb"},
    {"name": "DSP5",  "code": "TLZ64-DSP5",    "prefix": "wb"},
    {"name": "SCP6",  "code": "PYZW3-SCP6",    "prefix": "wb"},
    {"name": "ESC1",  "code": "ACCP138-ESC1",  "prefix": "wr"},
    {"name": "MLE24", "code": "SHZV9-MLE24",   "prefix": "wb"},
]
BASE = "https://invest.fubonlife.com.tw"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
USERNAME = "mapple0107"
REPOS = ["fubon-vcct-calculator", "fubon-calculator"]
# ────────────────────────────────────────────────


def check_dependencies():
    missing = []
    for pkg in ["selenium", "webdriver_manager"]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        print("❌ 缺少套件：pip3 install", " ".join(missing))
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
    opts.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36")
    svc = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=svc, options=opts)


def fetch_fund_data(driver, fund):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    p = fund["prefix"]
    nav, dist = None, None

    # 抓淨值
    driver.get(f"{BASE}/w/{p}/{p}02.djhtm?a={fund['code']}&product={PRODUCT}")
    try:
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "table")))
        time.sleep(1.5)
        for row in driver.find_elements(By.CSS_SELECTOR, "table tr"):
            cells = [td.text.strip() for td in row.find_elements(By.TAG_NAME, "td")]
            if len(cells) >= 2 and re.match(r"\d{2}/\d{2}|\d{4}/\d{2}/\d{2}", cells[0]):
                try:
                    nav = float(cells[1])
                    break
                except ValueError:
                    continue
    except Exception:
        pass

    # 抓配息
    page = "wr10" if p == "wr" else "wb05"
    driver.get(f"{BASE}/w/{p}/{page}.djhtm?a={fund['code']}&product={PRODUCT}")
    try:
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "table")))
        time.sleep(2)
        for row in driver.find_elements(By.CSS_SELECTOR, "table tr"):
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

    return nav, dist


def calculate(nav, dist, name):
    fee = PREMIUM * FEE_RATE
    eff = PREMIUM - fee
    units = (eff / USD_RATE) / nav
    m_twd = units * dist * USD_RATE
    y_twd = m_twd * 12
    return {
        "基金名稱": name, "淨值": nav, "每單位分配": dist,
        "月配息(TWD)": m_twd, "年配息(TWD)": y_twd,
        "年化報酬率": (y_twd / (PREMIUM - PREMIUM*FEE_RATE)) * 100
    }


def print_results(results):
    ranked = sorted(results, key=lambda x: x["年化報酬率"], reverse=True)
    medals = ["🥇","🥈","🥉"]
    print("\n" + "═"*76)
    print("  📊 基金比較排行（依年化報酬率排序）")
    print("═"*76)
    print(f"  {'排名':<4} {'基金名稱':<10} {'淨值':>10} {'分配金額':>9} {'月配息(TWD)':>12} {'年配息(TWD)':>12} {'報酬率':>8}")
    print(f"  {'─'*4} {'─'*10} {'─'*10} {'─'*9} {'─'*12} {'─'*12} {'─'*8}")
    for i, r in enumerate(ranked):
        medal = medals[i] if i < 3 else f" {i+1:>2}."
        print(f"  {medal:<4} {r['基金名稱']:<10} {r['淨值']:>10.4f} {r['每單位分配']:>9.4f} {r['月配息(TWD)']:>12,.0f} {r['年配息(TWD)']:>12,.0f} {r['年化報酬率']:>7.2f}%")
    print("═"*76)
    best = ranked[0]
    print(f"\n  🏆 最佳選擇：{best['基金名稱']}")
    print(f"     每月可領 TWD {best['月配息(TWD)']:,.0f}　年化報酬率 {best['年化報酬率']:.2f}%")
    if len(ranked) > 1:
        print(f"     vs 最低 {ranked[-1]['基金名稱']}：每月多 TWD {best['月配息(TWD)']-ranked[-1]['月配息(TWD)']:,.0f}")
    print()


def update_html(results, html_content):
    """把最新淨值寫入 HTML 內容並回傳"""
    updated = False
    for r in results:
        name = r["基金名稱"]
        nav  = r["淨值"]
        dist = r["每單位分配"]
        # 比對格式：name:"JFP11", label:"...", nav:數字, dist:數字
        pattern     = r'(name:"' + re.escape(name) + r'"[^}]*?nav:)([\d.]+)([^}]*?dist:)([\d.]+)'
        replacement = rf'\g<1>{nav}\g<3>{dist}'
        new_content = re.sub(pattern, replacement, html_content)
        if new_content != html_content:
            html_content = new_content
            updated = True
            print(f"  ✅ {name}：淨值={nav}，分配={dist}")
        else:
            print(f"  ⚠️  {name}：找不到對應欄位，略過")
    return html_content, updated


def github_get(url):
    ssl._create_default_https_context = ssl._create_unverified_context
    import requests
    return requests.get(url, headers={
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }, verify=False).json()


def github_put(url, data):
    ssl._create_default_https_context = ssl._create_unverified_context
    import requests
    return requests.put(url, headers={
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }, json=data, verify=False).json()


def auto_update_web(results):
    """自動更新兩個網頁並推送到 GitHub"""
    if not GITHUB_TOKEN:
        print("❌ 請設定環境變數 GITHUB_TOKEN")
        return

    from datetime import datetime
    date_str = datetime.now().strftime("%Y-%m-%d")
    print("\n🌐 開始更新網頁...")

    for repo in REPOS:
        print(f"\n  📄 {repo}")
        url = f"https://api.github.com/repos/{USERNAME}/{repo}/contents/index.html"
        r   = github_get(url)
        sha = r["sha"]
        html_content = base64.b64decode(r["content"]).decode("utf-8")

        new_html, updated = update_html(results, html_content)

        if updated:
            result = github_put(url, {
                "message": f"自動更新基金淨值 {date_str}",
                "content": base64.b64encode(new_html.encode("utf-8")).decode("utf-8"),
                "sha": sha
            })
            if "content" in result:
                print(f"  ✅ {repo} 推送成功")
            else:
                print(f"  ❌ {repo} 推送失敗：{result.get('message','')}")
        else:
            print(f"  ℹ️  {repo} 無變動，略過")

    print("\n✅ 網頁更新完成！")


def main():
    print("═"*60)
    print("  富邦 VCCT 月配息計算器")
    print("═"*60)
    print(f"  共 {len(FUNDS)} 檔基金待查詢")
    print("═"*60)
    check_dependencies()

    print("\n🌐 啟動瀏覽器...")
    driver = make_driver()
    results, errors = [], []

    try:
        for i, fund in enumerate(FUNDS, 1):
            print(f"  [{i}/{len(FUNDS)}] {fund['name']:<8}", end=" ", flush=True)
            nav, dist = fetch_fund_data(driver, fund)
            if nav and dist:
                r = calculate(nav, dist, fund["name"])
                results.append(r)
                print(f"✅ 淨值={nav:.4f}  分配={dist:.4f}  月配息 TWD {r['月配息(TWD)']:,.0f}  報酬率 {r['年化報酬率']:.2f}%")
            else:
                print(f"❌ 無法取得資料（淨值={nav}, 分配={dist}）")
                errors.append(fund["name"])
    finally:
        driver.quit()
        print("🔒 瀏覽器已關閉")

    if errors:
        print(f"\n⚠️  以下基金需確認代碼：{', '.join(errors)}")

    if results:
        print_results(results)
        auto_update_web(results)


if __name__ == "__main__":
    main()
