import streamlit as st
import pandas as pd
import re
import time
import subprocess
from io import BytesIO
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys


REGION_MAP = {
    "北海道":"01_北海道",
    "青森県":"02_東北","岩手県":"02_東北","宮城県":"02_東北",
    "秋田県":"02_東北","山形県":"02_東北","福島県":"02_東北",
    "茨城県":"03_関東","栃木県":"03_関東","群馬県":"03_関東",
    "埼玉県":"03_関東","千葉県":"03_関東","東京都":"03_関東","神奈川県":"03_関東",
    "新潟県":"04_中部","富山県":"04_中部","石川県":"04_中部",
    "福井県":"04_中部","山梨県":"04_中部","長野県":"04_中部",
    "岐阜県":"04_中部","静岡県":"04_中部","愛知県":"04_中部",
    "三重県":"05_近畿","滋賀県":"05_近畿","京都府":"05_近畿",
    "大阪府":"05_近畿","兵庫県":"05_近畿","奈良県":"05_近畿","和歌山県":"05_近畿",
    "鳥取県":"06_中国四国","島根県":"06_中国四国","岡山県":"06_中国四国",
    "広島県":"06_中国四国","山口県":"06_中国四国",
    "徳島県":"06_中国四国","香川県":"06_中国四国","愛媛県":"06_中国四国","高知県":"06_中国四国",
    "福岡県":"07_九州沖縄","佐賀県":"07_九州沖縄","長崎県":"07_九州沖縄",
    "熊本県":"07_九州沖縄","大分県":"07_九州沖縄","宮崎県":"07_九州沖縄",
    "鹿児島県":"07_九州沖縄","沖縄県":"07_九州沖縄",
}

BASE_URL = "https://www.iryou.teikyouseido.mhlw.go.jp/znk-web/juminkanja/S2300/initialize"
PAGE_DELAY = 2
DETAIL_DELAY = 1.5


def _find_bin(candidates):
    for name in candidates:
        try:
            path = subprocess.check_output(["which", name], text=True).strip()
            if path:
                return path
        except Exception:
            pass
    return None


def get_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1365,900")
    options.add_argument("--lang=ja-JP")

    chromium = _find_bin(["chromium", "chromium-browser", "google-chrome-stable"])
    if chromium:
        options.binary_location = chromium

    chromedriver = _find_bin(["chromedriver", "chromium-chromedriver"])
    service = Service(chromedriver) if chromedriver else Service()

    return webdriver.Chrome(service=service, options=options)


def is_visible(el):
    try:
        return el.is_displayed() and el.size["width"] > 0 and el.size["height"] > 0
    except Exception:
        return False


def debug_screenshot(driver, caption):
    st.image(driver.get_screenshot_as_png(), caption=caption)


def click_first_visible_by_text(driver, text_candidates):
    for text in text_candidates:
        xpath = (
            f"//*[self::a or self::button or self::span or self::div or self::li]"
            f"[contains(normalize-space(), '{text}')]"
        )
        elems = driver.find_elements(By.XPATH, xpath)
        for el in elems:
            if is_visible(el):
                try:
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                    time.sleep(0.2)
                    driver.execute_script("arguments[0].click();", el)
                    return True, text
                except Exception:
                    continue
    return False, ""


def collect_form_debug(driver):
    return driver.execute_script("""
        return Array.from(document.querySelectorAll('input, select, textarea, button')).map((el, idx) => {
            let opts = [];
            if (el.tagName === 'SELECT') {
                opts = Array.from(el.options).map(o => `${o.text}:${o.value}`);
            }

            return {
                idx: idx,
                tag: el.tagName,
                type: el.type || '',
                name: el.name || '',
                id: el.id || '',
                placeholder: el.placeholder || '',
                value: el.value || '',
                text: (el.innerText || el.textContent || '').trim().substring(0, 80),
                displayed: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
                options: opts.join(' | ')
            };
        });
    """)


def collect_button_debug(driver):
    return driver.execute_script("""
        return Array.from(
            document.querySelectorAll('button, input[type=button], input[type=submit], a')
        ).map((b, idx) => ({
            idx: idx,
            tag: b.tagName,
            type: b.type || '',
            text: (b.innerText || b.value || b.textContent || '').trim().substring(0, 80),
            name: b.name || '',
            id: b.id || '',
            className: b.className || '',
            href: b.href || '',
            onclick: b.getAttribute('onclick') || '',
            disabled: b.disabled || false,
            displayed: !!(b.offsetWidth || b.offsetHeight || b.getClientRects().length),
            value: b.value || ''
        }));
    """)


def select_facility_name_if_exists(driver, debug=False):
    selects = driver.find_elements(By.TAG_NAME, "select")
    debug_rows = []

    for sel in selects:
        if not is_visible(sel):
            continue

        name = sel.get_attribute("name") or ""
        sel_id = sel.get_attribute("id") or ""
        before_value = sel.get_attribute("value") or ""

        try:
            options = [
                {
                    "text": o.text.strip(),
                    "value": o.get_attribute("value")
                }
                for o in sel.find_elements(By.TAG_NAME, "option")
            ]

            if name == "keywordType":
                driver.execute_script("""
                    arguments[0].value = '2';
                    arguments[0].dispatchEvent(new Event('input', { bubbles:true }));
                    arguments[0].dispatchEvent(new Event('change', { bubbles:true }));
                    arguments[0].dispatchEvent(new Event('blur', { bubbles:true }));
                """, sel)

                time.sleep(1)

                after_value = sel.get_attribute("value") or ""

                debug_rows.append({
                    "name": name,
                    "id": sel_id,
                    "before": before_value,
                    "after": after_value,
                    "options": " | ".join([f"{o['text']}:{o['value']}" for o in options])
                })

                return after_value == "2", debug_rows

            debug_rows.append({
                "name": name,
                "id": sel_id,
                "before": before_value,
                "after": sel.get_attribute("value") or "",
                "options": " | ".join([f"{o['text']}:{o['value']}" for o in options])
            })

        except Exception as e:
            debug_rows.append({
                "name": name,
                "id": sel_id,
                "before": before_value,
                "after": "",
                "options": f"ERROR: {e}"
            })

    return False, debug_rows


def fill_visible_keyword_input(driver, keyword):
    selectors = [
        "input#keyword1",
        "input[name='keyword']",
        "input[type='text']",
        "input[type='search']",
        "input:not([type])",
        "input:not([type='hidden']):not([type='submit']):not([type='button']):not([type='checkbox']):not([type='radio'])",
    ]

    tried = []
    used_keys = set()

    for selector in selectors:
        inputs = driver.find_elements(By.CSS_SELECTOR, selector)
        visible_inputs = [i for i in inputs if is_visible(i)]

        for el in visible_inputs:
            key = (
                el.get_attribute("name"),
                el.get_attribute("id"),
                el.get_attribute("placeholder"),
            )
            if key in used_keys:
                continue
            used_keys.add(key)

            info = {
                "type": el.get_attribute("type"),
                "name": el.get_attribute("name"),
                "id": el.get_attribute("id"),
                "placeholder": el.get_attribute("placeholder"),
            }
            tried.append(info)

            try:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                time.sleep(0.2)
                el.clear()
                el.send_keys(keyword)

                driver.execute_script("""
                    arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
                    arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
                    arguments[0].dispatchEvent(new Event('blur', { bubbles: true }));
                """, el)

                val = el.get_attribute("value") or ""
                if keyword in val:
                    return True, el, tried
            except Exception:
                continue

    return False, None, tried


def click_search_button(driver, target_input=None):
    # 画面上の「検索」ボタン候補を下方向から探す
    button_xpaths = [
        "//button[contains(normalize-space(), '検索')]",
        "//input[@type='submit' and contains(@value, '検索')]",
        "//input[@type='button' and contains(@value, '検索')]",
        "//*[self::a or self::button or self::span or self::div][contains(normalize-space(), '検索')]",
    ]

    candidates = []

    for xp in button_xpaths:
        buttons = driver.find_elements(By.XPATH, xp)
        for b in buttons:
            if is_visible(b):
                try:
                    loc = b.location
                    candidates.append((loc.get("y", 0), b))
                except Exception:
                    candidates.append((0, b))

    # 下にある検索ボタンを優先
    candidates = sorted(candidates, key=lambda x: x[0], reverse=True)

    for _, b in candidates:
        try:
            if b.get_attribute("disabled"):
                continue
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", b)
            time.sleep(0.3)
            driver.execute_script("arguments[0].click();", b)
            return True
        except Exception:
            continue

    if target_input:
        try:
            target_input.send_keys(Keys.ENTER)
            return True
        except Exception:
            pass

    return False


def extract_result_links(driver):
    js_links = driver.execute_script("""
        return Array.from(document.querySelectorAll('a')).map(l => ({
            text: (l.innerText || l.textContent || '').trim(),
            href: l.href || '',
            onclick: l.getAttribute('onclick') || ''
        }));
    """)

    skip_texts = {
        "ホーム","トップ","検索","次へ","前へ","閉じる","戻る",
        "医療機関","薬局を探す","キーワード","急いで探す","じっくり探す",
        "お気に入り","都道府県","ご意見","マニュアル","リンク集","ログイン",
        "このページの先頭へ","English","日本語","簡体中文","繁體中文","한국어"
    }

    results = []
    seen = set()

    for item in js_links:
        name = re.sub(r"\s+", " ", item.get("text", "")).strip()
        href = item.get("href", "")
        onclick = item.get("onclick", "")

        if not name or len(name) < 3:
            continue
        if name in skip_texts:
            continue

        key = href or onclick or name
        if key in seen:
            continue

        if href and any(x in href for x in ["S2310", "S2400", "S2500", "detail"]):
            results.append((name, href))
            seen.add(key)
            continue

        if onclick and any(x in onclick for x in ["S2310", "S2400", "S2500", "detail", "select", "shosai"]):
            results.append((name, href if href else driver.current_url))
            seen.add(key)

    return results


def search_and_collect(driver, keyword, status_text, debug=False):
    driver.get(BASE_URL)
    time.sleep(6)

    if debug:
        debug_screenshot(driver, "① トップページ読み込み後")
        st.code(f"URL: {driver.current_url}")

    clicked_pharmacy, txt = click_first_visible_by_text(driver, ["薬局を探す", "薬局"])
    time.sleep(2)

    if debug:
        st.write(f"薬局タブクリック: {clicked_pharmacy} / {txt}")
        debug_screenshot(driver, "② 薬局を探すクリック後")

    clicked_keyword, txt = click_first_visible_by_text(driver, ["キーワードで探す", "キーワード検索"])
    time.sleep(2)

    if debug:
        st.write(f"キーワード検索クリック: {clicked_keyword} / {txt}")
        debug_screenshot(driver, "③ 入力フォーム確認")
        st.code(f"URL: {driver.current_url}")
        forms = collect_form_debug(driver)
        st.write(f"フォーム要素数: {len(forms)}")
        st.dataframe(forms, use_container_width=True)

    selected, select_debug = select_facility_name_if_exists(driver, debug=debug)

    if debug:
        st.write(f"施設名称選択結果: {selected}")
        st.write("SELECT一覧")
        st.dataframe(select_debug, use_container_width=True)
        st.write(select_debug)
        debug_screenshot(driver, "③-1 施設名称選択後")

    input_filled, target, tried = fill_visible_keyword_input(driver, keyword)

    if debug:
        st.write(f"キーワード入力成功: {input_filled}")
        st.write("入力候補")
        st.dataframe(tried, use_container_width=True)
        debug_screenshot(driver, f"③-2 キーワード入力後：{keyword}")

    if not input_filled:
        if debug:
            st.error("表示中のキーワード入力欄が見つからない、または入力値が反映されませんでした。")
        return []

    if debug:
        before_buttons = collect_button_debug(driver)
        st.write("検索前 BUTTON一覧")
        st.dataframe(before_buttons, use_container_width=True)

    clicked_search = click_search_button(driver, target)
    time.sleep(6)

    if debug:
        st.write(f"検索ボタンクリック: {clicked_search}")
        debug_screenshot(driver, "④ 検索結果ページ")

        after_buttons = collect_button_debug(driver)
        st.write("検索後 BUTTON一覧")
        st.dataframe(after_buttons, use_container_width=True)

        js_links = driver.execute_script("""
            return Array.from(document.querySelectorAll('a')).map((l, idx) => ({
                idx: idx,
                text: (l.innerText || l.textContent || '').trim().substring(0, 80),
                href: l.href || '',
                onclick: l.getAttribute('onclick') || ''
            })).filter(l => l.text.length > 0 || l.href.length > 0 || l.onclick.length > 0);
        """)
        st.write(f"ページ内リンク数: {len(js_links)}")
        st.dataframe(js_links[:100], use_container_width=True)

        try:
            body_text = driver.find_element(By.TAG_NAME, "body").text
            st.write("ページ本文 先頭1000文字")
            st.text(body_text[:1000])
        except Exception as e:
            st.warning(f"本文取得失敗: {e}")

    all_urls = []
    seen_urls = set()
    page_num = 1

    while True:
        page_urls = extract_result_links(driver)

        new_items = []
        for name, url in page_urls:
            key = f"{name}__{url}"
            if key not in seen_urls:
                new_items.append((name, url))
                seen_urls.add(key)

        all_urls.extend(new_items)
        status_text.text(f"検索中... ページ {page_num}: {len(new_items)} 件 / 累計 {len(all_urls)} 件")

        clicked_next = False
        next_candidates = driver.find_elements(By.XPATH, "//*[self::a or self::button][contains(normalize-space(), '次へ')]")
        for n in next_candidates:
            if is_visible(n):
                try:
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", n)
                    time.sleep(0.2)
                    driver.execute_script("arguments[0].click();", n)
                    clicked_next = True
                    break
                except Exception:
                    continue

        if clicked_next:
            time.sleep(PAGE_DELAY)
            page_num += 1
            if page_num > 30:
                break
        else:
            break

    return all_urls


def extract_val(text, pattern):
    m = re.search(pattern, text, re.DOTALL)
    return m.group(1).strip() if m else ""


def extract_pref(address):
    m = re.search(r"(北海道|東京都|大阪府|京都府|[^\s]{2,3}県)", address)
    return m.group(1) if m else ""


def fetch_detail(driver, name, url):
    store = {
        "施設名": name,
        "住所": "",
        "都道府県": "",
        "地方": "",
        "薬剤師_常勤": "",
        "薬剤師_非常勤": "",
        "総取扱処方箋数": "",
        "詳細URL": url,
    }

    try:
        driver.get(url)
        time.sleep(3)

        tab_candidates = driver.find_elements(
            By.XPATH,
            "//*[self::a or self::button or self::span or self::li or self::div]"
            "[contains(normalize-space(), '実績') or contains(normalize-space(), '結果に係る事項')]"
        )
        for tab in tab_candidates:
            if is_visible(tab):
                try:
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", tab)
                    time.sleep(0.2)
                    driver.execute_script("arguments[0].click();", tab)
                    time.sleep(1.5)
                    break
                except Exception:
                    continue

        txt = driver.find_element(By.TAG_NAME, "body").text

        store["住所"] = (
            extract_val(txt, r"所在地\s*[：:]\s*(.+?)(?:\n|\r)")
            or extract_val(txt, r"住所\s*[：:]\s*(.+?)(?:\n|\r)")
        )

        store["薬剤師_常勤"] = (
            extract_val(txt, r"常勤の人数\s*[：:]\s*([\d,]+)")
            or extract_val(txt, r"薬剤師.*?常勤.*?([\d,]+)")
        )

        store["薬剤師_非常勤"] = (
            extract_val(txt, r"非常勤の人数[（(][^）)]*[）)]\s*[：:]\s*([\d,]+)")
            or extract_val(txt, r"非常勤の人数\s*[：:]\s*([\d,]+)")
            or extract_val(txt, r"薬剤師.*?非常勤.*?([\d,]+)")
        )

        store["総取扱処方箋数"] = (
            extract_val(txt, r"総取[り扱]*処方箋数\s*[：:①②]?\s*([\d,]+)")
            or extract_val(txt, r"処方箋数\s*[：:]\s*([\d,]+)")
        )

        pref = extract_pref(store["住所"])
        store["都道府県"] = pref
        store["地方"] = REGION_MAP.get(pref, "99_不明")

    except Exception as e:
        store["エラー"] = str(e)

    return store


def run_scrape_with_keyword(company_name, keyword, progress_bar, status_text, debug=False):
    driver = get_driver()
    all_stores = []

    try:
        urls = search_and_collect(driver, keyword, status_text, debug=debug)

        if not urls:
            return []

        for i, (name, url) in enumerate(urls):
            status_text.text(f"📋 詳細取得中 {i + 1}/{len(urls)}: {name}")
            progress_bar.progress((i + 1) / len(urls))

            store = fetch_detail(driver, name, url)
            all_stores.append(store)
            time.sleep(DETAIL_DELAY)

    finally:
        driver.quit()

    return all_stores


def to_excel(stores):
    df = pd.DataFrame(stores)

    sort_cols = [c for c in ["地方", "都道府県", "施設名"] if c in df.columns]
    if sort_cols:
        df = df.sort_values(sort_cols).reset_index(drop=True)

    col_order = [
        "施設名",
        "都道府県",
        "地方",
        "住所",
        "薬剤師_常勤",
        "薬剤師_非常勤",
        "総取扱処方箋数",
        "詳細URL",
    ]

    cols = [c for c in col_order if c in df.columns]
    df = df[cols]

    buf = BytesIO()

    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="店舗一覧")
        ws = writer.sheets["店舗一覧"]

        from openpyxl.styles import PatternFill, Font, Alignment

        fill = PatternFill(fill_type="solid", fgColor="1F4E79")
        font = Font(color="FFFFFF", bold=True)

        for cell in ws[1]:
            cell.fill = fill
            cell.font = font
            cell.alignment = Alignment(horizontal="center")

        for col in ws.columns:
            w = max((len(str(c.value)) for c in col if c.value), default=10)
            ws.column_dimensions[col[0].column_letter].width = min(w + 2, 60)

    buf.seek(0)
    return buf, df


st.set_page_config(page_title="薬局情報収集ツール", page_icon="💊", layout="centered")

st.title("💊 薬局情報収集ツール")
st.caption("医療情報ネット（ナビイ）から薬剤師数・処方箋数を自動収集します")
st.divider()

company = st.text_input(
    "① 企業名（ファイル名などに使われます）",
    placeholder="例：総合メディカル、クオール、日本調剤",
)

keyword = st.text_input(
    "② ナビイでの検索ワード（店舗名に使われているブランド名）",
    placeholder="例：そうごう薬局、クオール薬局、日本調剤",
)

st.caption("💡 ①と②が同じ場合はどちらも同じ名前でOKです。")

debug_mode = st.checkbox("🔧 デバッグモード（ブラウザの動作を画像で確認）", value=False)

st.divider()

can_search = bool(company and keyword)

if st.button("🔍 検索開始", type="primary", disabled=not can_search):
    progress = st.progress(0)
    status = st.empty()

    with st.spinner(f"「{keyword}」で検索中です..."):
        try:
            stores = run_scrape_with_keyword(company, keyword, progress, status, debug=debug_mode)
        except Exception as e:
            st.error(f"エラーが発生しました: {e}")
            stores = []

    if stores:
        progress.progress(1.0)
        status.text("✅ 完了！")

        buf, df = to_excel(stores)
        fname = f"{company}_薬局一覧_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"

        st.success(f"**{len(stores)} 件** を取得しました")

        st.download_button(
            label="📥 Excelをダウンロード",
            data=buf,
            file_name=fname,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
        )

        show_cols = [
            c for c in [
                "施設名",
                "都道府県",
                "薬剤師_常勤",
                "薬剤師_非常勤",
                "総取扱処方箋数",
            ]
            if c in df.columns
        ]

        st.subheader("プレビュー（地域別ソート）")
        st.dataframe(df[show_cols], use_container_width=True)

    else:
        st.warning(
            f"「{keyword}」で検索しましたが結果が取得できませんでした。\n"
            "デバッグモードONで③④の画面とフォーム要素一覧を確認してください。"
        )

st.divider()
st.caption("※ データは医療情報ネット（ナビイ）/ 厚生労働省より取得")
