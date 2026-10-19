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
    {"name": "JFP11"},
    {"name": "ACC3"},
    {"name": "IGB5"},
    {"name": "FRP4"},
    {"name": "DSP5"},
    {"name": "SCP6"},
    {"name": "ESC1"},
    {"name": "MLE24"},
]
# 2026/10 富邦人壽投資型保險網站改版，舊的 /w/wb/wb02.djhtm 等路徑已下架（只會回傳
# 「服務未能正常連線」提示頁）。新站改用 /funds/overview（最新淨值／績效與風險兩個頁籤）
# 與 /funds/dividend（每單位分配金額），且都可以直接用基金代碼（如 JFP11）搜尋，
# 不再需要舊版的 wb/wr 前綴與完整代碼組合。
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


def _dismiss_alert(driver):
    """關掉還留在頁面上的 JS alert（例如某些基金頁面 DataTables 欄位數對不上時
    跳出的「Incorrect column count」警告）。不主動處理的話，這個 alert 會卡住
    瀏覽器，導致下一次 driver.get() 直接丟 UnexpectedAlertPresentException，
    害後面所有基金都跟著抓取失敗。"""
    try:
        driver.switch_to.alert.dismiss()
    except Exception:
        pass


def _safe_get(driver, url):
    """導覽到指定網址；如果上一頁還留著沒關掉的 alert，先關掉再重試一次，
    避免單一基金的頁面問題拖垮後面所有基金的抓取。"""
    from selenium.common.exceptions import UnexpectedAlertPresentException
    for attempt in range(2):
        try:
            driver.get(url)
            return True
        except UnexpectedAlertPresentException:
            _dismiss_alert(driver)
    return False


def _wait_table(driver, timeout=15):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.TAG_NAME, "table")))


def _visible_search_box(driver):
    """新版網站同一頁面上有好幾個 input[type=search]（頁首的、下拉選單篩選用的），
    真正控制表格篩選的那個是畫面上看得到的最後一個，用 is_displayed() 排除藏起來的。"""
    from selenium.webdriver.common.by import By
    boxes = [b for b in driver.find_elements(By.CSS_SELECTOR, 'input[type="search"]') if b.is_displayed()]
    return boxes[-1] if boxes else None


def _set_search(driver, box, code, wait=1.5):
    """新版網站的表格資料在頁面載入時就已經整批帶回來（Nuxt 的 __NUXT_DATA__），
    搜尋框只是純前端用 debounce 篩選，不會另外打 API，所以用原生 setter 寫入搜尋框
    的值、觸發 input 事件，等 debounce 篩選跑完（約 1~1.5 秒）即可，不需要按 Enter。"""
    driver.execute_script(
        """
        const el = arguments[0], value = arguments[1];
        const proto = Object.getPrototypeOf(el);
        const desc = Object.getOwnPropertyDescriptor(proto, 'value');
        desc.set.call(el, value);
        el.dispatchEvent(new Event('input', {bubbles: true}));
        """,
        box, code,
    )
    time.sleep(wait)


def _row_cells_for(driver, code):
    """找出代碼欄位包含 code 的那一列，回傳所有 td 文字；查無資料（「查無資料」）回傳 None。"""
    from selenium.webdriver.common.by import By
    for row in driver.find_elements(By.CSS_SELECTOR, "table tbody tr"):
        tds = row.find_elements(By.TAG_NAME, "td")
        if tds and code in tds[0].text:
            return [td.text.strip() for td in tds]
    return None


def _fmt_pct(v):
    """把原始數字字串轉成帶正負號、百分比符號的顯示格式（N/A 原樣保留）"""
    if v is None or v == "" or v == "N/A":
        return "N/A"
    try:
        f = float(v)
    except ValueError:
        return v
    sign = "+" if f > 0 else ""
    return f"{sign}{f:.2f}%"


def fetch_nav_batch(driver, funds):
    """投資標的總覽／最新淨值頁籤：一次載入頁面，逐檔搜尋取得淨值。
    欄位順序：代碼, 標的名稱, 標的類型, 日期, 淨值, 幣別, 漲跌, 漲跌幅"""
    nav = {}
    if not _safe_get(driver, f"{BASE}/funds/overview"):
        return nav
    try:
        _wait_table(driver)
    except Exception:
        print("  ❌ 投資標的總覽頁面載入逾時")
        return nav
    box = _visible_search_box(driver)
    if box is None:
        print("  ❌ 找不到搜尋框，網站版面可能又變了")
        return nav
    for fund in funds:
        code = fund["name"]
        _set_search(driver, box, code)
        cells = _row_cells_for(driver, code)
        if cells and len(cells) >= 5:
            try:
                nav[code] = float(cells[4])
            except ValueError:
                pass
    return nav


def fetch_perf_batch(driver, funds):
    """投資標的總覽／績效與風險頁籤：切換頁籤後逐檔搜尋取得報酬率。
    欄位順序：代碼, 標的名稱, 今年以來, 一個月, 三個月, 六個月, 一年, 二年, 三年, 五年,
             成立以來, 風險報酬等級, 年化標準差, 夏普值, Beta係數"""
    from selenium.webdriver.common.by import By
    perf = {}
    try:
        tab_btn = next(
            b for b in driver.find_elements(By.TAG_NAME, "button")
            if b.text.strip() == "績效與風險"
        )
        tab_btn.click()
        time.sleep(0.8)
        _wait_table(driver)
    except Exception:
        print("  ❌ 切換到績效與風險頁籤失敗")
        return perf
    box = _visible_search_box(driver)
    if box is None:
        return perf
    labels = ["今年以來", "一個月", "三個月", "六個月", "一年", "二年", "三年", "五年", "成立以來"]
    for fund in funds:
        code = fund["name"]
        _set_search(driver, box, code)
        cells = _row_cells_for(driver, code)
        if cells and len(cells) >= 2 + len(labels):
            values = cells[2:2 + len(labels)]
            perf[code] = {lbl: _fmt_pct(val) for lbl, val in zip(labels, values)}
    return perf


def fetch_dividend_batch(driver, funds):
    """配息/提解資訊頁面：一次載入頁面，逐檔搜尋取得每單位分配金額。
    欄位順序：代碼, 標的名稱, 日期, 淨值, 幣別, 每單位分配金額, 基準日, 除息日"""
    dist = {}
    if not _safe_get(driver, f"{BASE}/funds/dividend"):
        return dist
    try:
        _wait_table(driver)
    except Exception:
        print("  ❌ 配息/提解資訊頁面載入逾時")
        return dist
    box = _visible_search_box(driver)
    if box is None:
        return dist
    for fund in funds:
        code = fund["name"]
        _set_search(driver, box, code)
        cells = _row_cells_for(driver, code)
        if cells and len(cells) >= 6:
            try:
                dist[code] = float(cells[5])
            except ValueError:
                pass
    return dist


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
        pattern = r'(name:"' + re.escape(name) + r'"[^}]*?nav:)([\d.]+)([^}]*?dist:)([\d.]+)'
        if not re.search(pattern, html_content):
            print(f"  ⚠️  {name}：找不到對應欄位，略過")
        else:
            replacement = rf'\g<1>{nav}\g<3>{dist}'
            new_content = re.sub(pattern, replacement, html_content)
            if new_content != html_content:
                html_content = new_content
                updated = True
                print(f"  ✅ {name}：淨值={nav}，分配={dist}")
            else:
                print(f"  ℹ️  {name}：淨值={nav}，分配={dist}（跟目前網頁上的一樣，無需變動）")

        # 比對格式：name:"JFP11" ... perf:{...}（可能是空物件或先前抓過的內容）
        perf_pattern = r'(name:"' + re.escape(name) + r'"[^}]*?perf:)(\{[^}]*\})'
        if not perf:
            print(f"  ⚠️  {name}：本次沒有抓到績效資料，略過")
        elif not re.search(perf_pattern, html_content):
            print(f"  ⚠️  {name}：找不到 perf 欄位，略過")
        else:
            perf_json = json.dumps(perf, ensure_ascii=False, separators=(",", ":"))
            perf_new = re.sub(perf_pattern, lambda m: m.group(1) + perf_json, html_content)
            if perf_new != html_content:
                html_content = perf_new
                updated = True
                print(f"  ✅ {name}：績效已更新（{len(perf)} 筆）")
            else:
                print(f"  ℹ️  {name}：績效資料跟網頁上的一樣，無需變動")
    return html_content, updated


REPO_PATHS = {
    "fubon-vcct-calculator": os.path.expanduser("~/Downloads/fubon-vcct-calculator-main"),
    "fubon-calculator":      os.path.expanduser("~/Downloads/fubon-calculator"),
}


def _run_git(args, cwd):
    import subprocess
    return subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True)


def auto_update_web(results):
    """修改 calculator.html，commit/push 到 GitHub。
    本機執行時：直接在 REPO_PATHS 指到的本機 git 資料夾操作（沿用你手動改過、還沒 commit 的內容）。
    在 Railway 這種雲端容器裡執行時：REPO_PATHS 那些路徑不存在（那是你電腦上的路徑，容器裡看不到），
    所以改成用 GITHUB_TOKEN 直接把兩個倉庫 clone 到一個暫存資料夾，改完再 push 回去，
    這樣排程才會真的更新到網頁，而不是每次都印「找不到本機資料夾，略過」卻什麼都沒發生。"""
    if not GITHUB_TOKEN:
        print("❌ 請設定環境變數 GITHUB_TOKEN")
        return

    import shutil
    import tempfile
    from datetime import datetime
    date_str = datetime.now().strftime("%Y-%m-%d")
    print("\n🌐 開始更新網頁...")

    for repo in REPOS:
        print(f"\n  📄 {repo}")
        local_path = REPO_PATHS.get(repo)
        use_local = bool(local_path and os.path.isdir(local_path))
        tmpdir = None

        if use_local:
            path = local_path
            print(f"  ℹ️  使用本機資料夾：{path}")
            # 先 pull，確保基於最新版本修改（避免蓋掉手動改過的內容）
            pull = _run_git(["pull", "--no-edit"], cwd=path)
            if pull.returncode != 0:
                print(f"  ⚠️  git pull 失敗：{pull.stderr.strip()[:200]}（仍嘗試繼續）")
        else:
            tmpdir = tempfile.mkdtemp(prefix=f"{repo}-")
            clone_url = f"https://mapple0107:{GITHUB_TOKEN}@github.com/{USERNAME}/{repo}.git"
            clone = _run_git(["clone", "--depth", "1", clone_url, tmpdir], cwd=tempfile.gettempdir())
            if clone.returncode != 0:
                print(f"  ❌ 本機找不到資料夾，clone 也失敗，略過：{clone.stderr.strip()[:200]}")
                shutil.rmtree(tmpdir, ignore_errors=True)
                continue
            path = tmpdir
            print(f"  ℹ️  本機找不到資料夾，改用暫存 clone：{path}")

        # 每次都明確設定 commit 身分，避免容器裡沒有全域 git 設定導致 commit 失敗
        _run_git(["config", "user.email", "bot@fubon-calculator.local"], cwd=path)
        _run_git(["config", "user.name", "Fubon Calculator Bot"], cwd=path)

        html_path = os.path.join(path, "calculator.html")
        if not os.path.isfile(html_path):
            print(f"  ❌ 找不到 calculator.html，略過")
            if tmpdir:
                shutil.rmtree(tmpdir, ignore_errors=True)
            continue

        with open(html_path, encoding="utf-8") as f:
            html_content = f.read()

        new_html, updated = update_html(results, html_content)

        if not updated:
            print(f"  ℹ️  無變動，略過")
            if tmpdir:
                shutil.rmtree(tmpdir, ignore_errors=True)
            continue

        with open(html_path, "w", encoding="utf-8") as f:
            f.write(new_html)

        _run_git(["add", "calculator.html"], cwd=path)
        commit = _run_git(["commit", "-m", f"自動更新基金淨值 {date_str}"], cwd=path)
        if commit.returncode != 0 and "nothing to commit" in (commit.stdout + commit.stderr):
            print(f"  ℹ️  git 無變動可提交，略過")
            if tmpdir:
                shutil.rmtree(tmpdir, ignore_errors=True)
            continue

        remote_url = f"https://mapple0107:{GITHUB_TOKEN}@github.com/{USERNAME}/{repo}.git"
        push = _run_git(["push", remote_url, "HEAD:main"], cwd=path)
        if push.returncode == 0:
            print(f"  ✅ {repo} 推送成功")
        else:
            err = (push.stderr or push.stdout).strip()
            print(f"  ❌ {repo} 推送失敗：{err[:300]}")

        if tmpdir:
            shutil.rmtree(tmpdir, ignore_errors=True)

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
        # 新站把資料整批帶回頁面、搜尋框是純前端篩選，所以每個頁面只需要載入一次，
        # 逐檔搜尋就好，不用像舊版那樣每檔基金各自打開好幾個頁面。
        print("\n📈 查詢最新淨值（投資標的總覽）...")
        nav_map = fetch_nav_batch(driver, FUNDS)
        print("📊 查詢績效與風險...")
        perf_map = fetch_perf_batch(driver, FUNDS)
        print("💰 查詢配息資訊（配息/提解資訊）...")
        dist_map = fetch_dividend_batch(driver, FUNDS)

        for i, fund in enumerate(FUNDS, 1):
            name = fund["name"]
            nav = nav_map.get(name)
            dist = dist_map.get(name)
            perf = perf_map.get(name, {})
            print(f"  [{i}/{len(FUNDS)}] {name:<8}", end=" ", flush=True)
            if nav and dist:
                r = calculate(nav, dist, name, perf)
                results.append(r)
                perf_note = f"  績效={len(perf)}筆" if perf else "  ⚠️績效未取得"
                print(f"✅ 淨值={nav:.4f}  分配={dist:.4f}  月配息 TWD {r['月配息(TWD)']:,.0f}  報酬率 {r['年化報酬率']:.2f}%{perf_note}")
            else:
                print(f"❌ 無法取得資料（淨值={nav}, 分配={dist}），請確認代碼 {name} 在新版網站上是否仍叫這個名字")
                errors.append(name)
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
