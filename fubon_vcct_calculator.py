"""
富邦人壽真豐利變額年金保險（VCCT）月配息自動計算器
支援多檔基金同時比較
=====================================================
安裝依賴套件：
    pip3 install requests beautifulsoup4 selenium webdriver-manager

使用方式：
    python3 fubon_vcct_calculator.py
"""

import sys

# ── 使用者設定區 ────────────────────────────────────────────────
PREMIUM       = 1_000_000   # 保費（台幣）
FEE_RATE      = 0.05        # 保費費用率（5% → 0.05）
USD_RATE      = 31.4        # 美金匯率
# ────────────────────────────────────────────────────────────────

def check_dependencies():
    missing = []
    for pkg in ["requests", "bs4", "selenium", "webdriver_manager"]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        print("❌ 缺少套件，請先執行：")
        print(f"   pip3 install {' '.join(missing)}")
        sys.exit(1)


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
        "保費（台幣）":           premium,
        "保費費用":               fee_cost,
        "實際投入保費（台幣）":   effective_premium,
        "換算美金投入":           usd_invested,
        "可購買單位數":           units,
        "每月配息（美金）":       monthly_usd,
        "每月配息（台幣）":       monthly_twd,
        "每年配息（台幣）":       yearly_twd,
        "年化報酬率":             yield_rate,
    }


def print_single(result):
    print(f"\n  {'─'*44}")
    print(f"  📌 {result['基金名稱']}")
    print(f"  {'─'*44}")
    print(f"  {'基金單位淨值（美金）':<20} USD {result['基金單位淨值（美金）']:>10.4f}")
    print(f"  {'每單位分配金額（美金）':<20} USD {result['每單位分配金額（美金）']:>10.4f}")
    print(f"  {'可購買單位數':<20} {result['可購買單位數']:>14.4f} 單位")
    print(f"  {'每月配息（美金）':<20} USD {result['每月配息（美金）']:>10.2f}")
    print(f"  {'每月配息（台幣）':<20} TWD {result['每月配息（台幣）']:>10,.0f}")
    print(f"  {'每年配息（台幣）':<20} TWD {result['每年配息（台幣）']:>10,.0f}")
    print(f"  {'年化報酬率':<20} {result['年化報酬率']:>13.2f}%")


def print_comparison(results):
    print("\n")
    print("═" * 70)
    print("  📊 多檔基金比較排行（依年化報酬率排序）")
    print("═" * 70)

    sorted_results = sorted(results, key=lambda x: x["年化報酬率"], reverse=True)

    # 表頭
    print(f"  {'排名':<4} {'基金名稱':<16} {'淨值':>8} {'分配金額':>8} {'月配息(TWD)':>12} {'年配息(TWD)':>12} {'報酬率':>8}")
    print(f"  {'─'*4} {'─'*16} {'─'*8} {'─'*8} {'─'*12} {'─'*12} {'─'*8}")

    medals = ["🥇", "🥈", "🥉"]
    for i, r in enumerate(sorted_results):
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

    best = sorted_results[0]
    print(f"\n  🏆 最佳選擇：{best['基金名稱']}")
    print(f"     每月可領 TWD {best['每月配息（台幣）']:,.0f}，年化報酬率 {best['年化報酬率']:.2f}%")
    print()


def input_fund(index):
    print(f"\n── 第 {index} 檔基金 ──────────────────────────")
    name = input(f"  基金名稱（可自訂，例如：VCCT-A）：").strip()
    if not name:
        name = f"基金{index}"
    try:
        nav           = float(input(f"  基金單位淨值（美金）："))
        dist_per_unit = float(input(f"  每單位分配金額（美金）："))
    except ValueError:
        print("  ❌ 輸入格式錯誤，請輸入數字。")
        return None
    return calculate(nav, dist_per_unit, fund_name=name)


def main():
    print("═" * 60)
    print("  富邦 VCCT 月配息計算器｜多檔基金比較版")
    print("═" * 60)
    print(f"  保費：TWD {PREMIUM:,.0f}　費用率：{FEE_RATE*100:.1f}%　匯率：{USD_RATE}")
    print("═" * 60)

    check_dependencies()

    results = []
    print("\n📋 請輸入要比較的基金資料")
    print("   （前往富邦網站查詢：https://invest.fubonlife.com.tw）\n")

    while True:
        try:
            count = int(input("請問要比較幾檔基金？（輸入數字，例如：3）："))
            if count < 1:
                print("請輸入至少 1。")
                continue
            break
        except ValueError:
            print("請輸入數字。")

    for i in range(1, count + 1):
        result = input_fund(i)
        if result:
            results.append(result)
            print_single(result)

    if not results:
        print("❌ 沒有有效的基金資料。")
        return

    if len(results) == 1:
        print("\n" + "═" * 50)
        print("  富邦 VCCT 月配息計算結果")
        print("═" * 50)
        print_single(results[0])
        print("═" * 50)
    else:
        print_comparison(results)


if __name__ == "__main__":
    main()
