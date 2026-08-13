import re, requests, base64, os
from datetime import datetime

TOKEN    = os.environ.get("GITHUB_TOKEN", "")
USERNAME = "mapple0107"
REPOS    = ["fubon-vcct-calculator", "fubon-calculator"]

def get_fund_results():
    """從 fubon_vcct_calculator.py 執行爬蟲取得結果"""
    import subprocess, json, sys
    # 執行爬蟲並截取結果
    result = subprocess.run(
        [sys.executable, "fubon_vcct_calculator.py"],
        capture_output=True, text=True, cwd="."
    )
    return result.stdout

def update_and_push(results_text):
    headers = {"Authorization": f"token {TOKEN}", "Accept": "application/vnd.github.v3+json"}
    date_str = datetime.now().strftime("%Y-%m-%d")

    # 解析爬蟲結果
    funds = {}
    for line in results_text.splitlines():
        m = re.search(r'\[(\d+)/\d+\]\s+(\w+)\s+✅\s+淨值=([\d.]+)\s+分配=([\d.]+)', line)
        if m:
            name = m.group(2)
            nav  = m.group(3)
            dist = m.group(4)
            funds[name] = (nav, dist)
            print(f"  解析到：{name} nav={nav} dist={dist}")

    if not funds:
        print("❌ 沒有解析到任何基金資料")
        return

    for repo in REPOS:
        print(f"\n📄 更新 {repo}...")
        url = f"https://api.github.com/repos/{USERNAME}/{repo}/contents/index.html"
        r   = requests.get(url, headers=headers, verify=False)
        sha = r.json()["sha"]
        html = base64.b64decode(r.json()["content"]).decode("utf-8")

        updated = False
        for name, (nav, dist) in funds.items():
            key = f'name:"{name}"'
            if key not in html:
                print(f"  ⚠️  {name}：不在此 repo")
                continue

            def make_replacer(n, d):
                def replacer(m):
                    block = m.group(0)
                    block = re.sub(r"nav:[\d.]+", "nav:" + n, block)
                    block = re.sub(r"dist:[\d.]+", "dist:" + d, block)
                    return block
                return replacer

            pattern  = r"[{][^{}]*?" + re.escape(key) + r"[^{}]*?[}]"
            new_html = re.sub(pattern, make_replacer(nav, dist), html, flags=re.DOTALL)
            if new_html != html:
                html = new_html
                updated = True
                print(f"  ✅ {name}：淨值={nav}，分配={dist}")

        if updated:
            r2 = requests.put(url, headers=headers, verify=False, json={
                "message": f"自動更新基金淨值 {date_str}",
                "content": base64.b64encode(html.encode("utf-8")).decode("utf-8"),
                "sha": sha
            })
            if "content" in r2.json():
                print(f"  ✅ {repo} 推送成功")
            else:
                print(f"  ❌ {repo} 推送失敗：{r2.json().get('message','')}")
        else:
            print(f"  ℹ️  {repo} 無變動")

if __name__ == "__main__":
    import subprocess, sys
    print("🌐 執行爬蟲...")
    result = subprocess.run(
        [sys.executable, "fubon_vcct_calculator.py"],
        capture_output=True, text=True
    )
    print(result.stdout[-2000:])
    update_and_push(result.stdout)
    print("\n✅ 完成！")
