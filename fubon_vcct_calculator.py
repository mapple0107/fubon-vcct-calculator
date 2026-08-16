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


def _parse_date_key(date_str):
    """把 MM/DD 或 YYYY/MM/DD 轉成可比較的日期物件，抓不到年份時用今年，
    若因跨年造成日期看起來在未來，往前推一年。"""
    from datetime import datetime, timedelta
    now = datetime.now()
    try:
        if len(date_str) == 5:  # MM/DD
            d = datetime.strptime(f"{now.year}/{date_str}", "%Y/%m/%d")
            if d > now + timedelta(days=2):
                d = d.replace(year=now.year - 1)
            return d
        return datetime.strptime(date_str, "%Y/%m/%d")
    except Exception:
        return datetime.min


def fetch_fund_data(driver, fund):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    p = fund["prefix"]
    nav, dist = None, None

    # 抓淨值：收集頁面上所有「日期＋淨值」配對，取日期最新的那一筆
    # （避免頁面上有多個表格/區塊時，誤抓到非最新一列的舊資料）
    driver.get(f"{BASE}/w/{p}/{p}02.djhtm?a={fund['code']}&product={PRODUCT}")
    try:
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "table")))
        candidates = []
        for attempt in range(3):
            time.sleep(2.5 if attempt == 0 else 2)
            candidates = []
            for row in driver.find_elements(By.CSS_SELECTOR, "table tr"):
                cells = [td.text.strip() for td in row.find_elements(By.TAG_NAME, "td")]
                for idx, cell in enumerate(cells):
                    if re.match(r"^\d{2}/\d{2}$|^\d{4}/\d{2}/\d{2}$", cell) and idx + 1 < len(cells):
                        try:
                            val = float(cells[idx + 1])
                            candidates.append((cell, val))
                        except ValueError:
                            continue
            if candidates:
                break
        if candidates:
            candidates.sort(key=lambda item: _parse_date_key(item[0]), reverse=True)
            nav = candidates[0][1]
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


PERF_LABELS = ["一週", "一個月", "本月", "本季", "三個月", "六個月", "九個月", "一年", "二年", "三年", "五年"]


def fetch_perf_data(driver, fund):
    """抓取「累積報酬率」頁面（{p}03.djhtm），回傳 {期間: 數值字串} 的 dict。
    對應網址規律：wb01/wr01 淨值頁 → {p}02 淨值明細、{p}03 累積報酬率（wb/wr 皆同）。"""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    p = fund["prefix"]
    perf = {}
    driver.get(f"{BASE}/w/{p}/{p}03.djhtm?a={fund['code']}&product={PRODUCT}")
    try:
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "table")))
        time.sleep(2.5)
        for table in driver.find_elements(By.TAG_NAME, "table"):
            rows = table.find_elements(By.TAG_NAME, "tr")
            if len(rows) != 3:
                continue
            labels = [td.text.strip() for td in rows[1].find_elements(By.TAG_NAME, "td")]
            values = [td.text.strip() for td in rows[2].find_elements(By.TAG_NAME, "td")]
            if not labels or not any(lbl in PERF_LABELS for lbl in labels):
                continue
            for lbl, val in zip(labels, values):
                if lbl in PERF_LABELS and val:
                    perf[lbl] = val
            if perf:
                break
    except Exception:
        pass
    return perf


def calculate(nav, dist, name, perf=None):
    fee = PREMIUM * FEE_RATE
    eff = PREMIUM - fee
    units = (eff / USD_RATE) / nav
    m_twd = units * dist * USD_RATE
    y_twd = m_twd * 12
    return {
        "基金名稱": name, "淨值": nav, "每單位分配": dist,
        "月配息(TWD)": m_twd, "年配息(TWD)": y_twd,
        "年化報酬率": (y_twd / (PREMIUM - PREMIUM*FEE_RATE)) * 100,
        "績效": perf or {}
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
    """把最新淨值與績效寫入 HTML 內容並回傳"""
    updated = False
    for r in results:
        name = r["基金名稱"]
        nav  = r["淨值"]
        dist = r["每單位分配"]
        perf = r.get("績效") or {}

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

        # 比對格式：name:"JFP11" ... perf:{...}（可能是空物件或先前抓過的內容）
        if perf:
            perf_json = json.dumps(perf, ensure_ascii=False, separators=(",", ":"))
            perf_pattern = r'(name:"' + re.escape(name) + r'"[^}]*?perf:)(\{[^}]*\})'
            perf_new = re.sub(perf_pattern, lambda m: m.group(1) + perf_json, html_content)
            if perf_new != html_content:
                html_content = perf_new
                updated = True
                print(f"  ✅ {name}：績效已更新（{len(perf)} 筆）")
            else:
                print(f"  ⚠️  {name}：找不到 perf 欄位，略過")
    return html_content, updated


REPO_PATHS = {
    "fubon-vcct-calculator": os.path.expanduser("~/Downloads/fubon-vcct-calculator-main"),
    "fubon-calculator":      os.path.expanduser("~/Downloads/fubon-calculator"),
}


def _run_git(args, cwd):
    import subprocess
    return subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True)


def auto_update_web(results):
    """直接在本機 git 資料夾修改 calculator.html，git pull/commit/push 到 GitHub
    （改用本機 git 而不是 GitHub API，因為 API 版本一直沒有真的成功寫入，難以除錯）"""
    if not GITHUB_TOKEN:
        print("❌ 請設定環境變數 GITHUB_TOKEN")
        return

    from datetime import datetime
    date_str = datetime.now().strftime("%Y-%m-%d")
    print("\n🌐 開始更新網頁...")

    for repo in REPOS:
        path = REPO_PATHS.get(repo)
        print(f"\n  📄 {repo} ({path})")
        if not path or not os.path.isdir(path):
            print(f"  ❌ 找不到本機資料夾，略過")
            continue

        html_path = os.path.join(path, "calculator.html")

        # 先 pull，確保基於最新版本修改（避免蓋掉手動改過的內容）
        pull = _run_git(["pull", "--no-edit"], cwd=path)
        if pull.returncode != 0:
            print(f"  ⚠️  git pull 失敗：{pull.stderr.strip()[:200]}（仍嘗試繼續）")

        if not os.path.isfile(html_path):
            print(f"  ❌ 找不到 calculator.html，略過")
            continue

        with open(html_path, encoding="utf-8") as f:
            html_content = f.read()

        new_html, updated = update_html(results, html_content)

        if not updated:
            print(f"  ℹ️  無變動，略過")
            continue

        with open(html_path, "w", encoding="utf-8") as f:
            f.write(new_html)

        _run_git(["add", "calculator.html"], cwd=path)
        commit = _run_git(["commit", "-m", f"自動更新基金淨值 {date_str}"], cwd=path)
        if commit.returncode != 0 and "nothing to commit" in (commit.stdout + commit.stderr):
            print(f"  ℹ️  git 無變動可提交，略過")
            continue

        remote_url = f"https://mapple0107:{GITHUB_TOKEN}@github.com/{USERNAME}/{repo}.git"
        push = _run_git(["push", remote_url, "HEAD:main"], cwd=path)
        if push.returncode == 0:
            print(f"  ✅ {repo} 推送成功")
        else:
            err = (push.stderr or push.stdout).strip()
            print(f"  ❌ {repo} 推送失敗：{err[:300]}")

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
                perf = fetch_perf_data(driver, fund)
                r = calculate(nav, dist, fund["name"], perf)
                results.append(r)
                perf_note = f"  績效={len(perf)}筆" if perf else "  ⚠️績效未取得"
                print(f"✅ 淨值={nav:.4f}  分配={dist:.4f}  月配息 TWD {r['月配息(TWD)']:,.0f}  報酬率 {r['年化報酬率']:.2f}%{perf_note}")
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
