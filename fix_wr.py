import shutil

path = "fubon_vcct_calculator.py"
backup = path + ".bak"
shutil.copy(path, backup)
print(f"已備份至 {backup}")

with open(path, "r", encoding="utf-8") as f:
    content = f.read()

old_code = '''    driver.get(f"{BASE}/w/{p}/{p}02.djhtm?a={fund['code']}&product={PRODUCT}")
    try:
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "table")))
        time.sleep(1.5)
        for row in driver.find_elements(By.CSS_SELECTOR, "table tr"):
            cells = [td.text.strip() for td in row.find_elements(By.TAG_NAME, "td")]
            if len(cells) >= 2 and re.match(r"\\d{2}/\\d{2}|\\d{4}/\\d{2}/\\d{2}", cells[0]):
                try:
                    nav = float(cells[1])
                    break
                except ValueError:
                    continue
    except Exception:
        pass'''

new_code = '''    driver.get(f"{BASE}/w/{p}/{p}02.djhtm?a={fund['code']}&product={PRODUCT}")
    try:
        if p == "wr":
            WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, "a.navbar-brand")))
            time.sleep(1.5)
            el = driver.find_element(By.CSS_SELECTOR, "a.navbar-brand")
            m = re.search(r"\\d+\\.\\d+", el.text.strip())
            if m:
                nav = float(m.group())
        else:
            WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "table")))
            time.sleep(1.5)
            for row in driver.find_elements(By.CSS_SELECTOR, "table tr"):
                cells = [td.text.strip() for td in row.find_elements(By.TAG_NAME, "td")]
                if len(cells) >= 2 and re.match(r"\\d{2}/\\d{2}|\\d{4}/\\d{2}/\\d{2}", cells[0]):
                    try:
                        nav = float(cells[1])
                        break
                    except ValueError:
                        continue
    except Exception:
        pass'''

if old_code not in content:
    print("❌ 找不到符合的舊程式碼，可能格式跟預期不同，請手動修改。")
else:
    content = content.replace(old_code, new_code)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("✅ 已成功修改 fubon_vcct_calculator.py")
