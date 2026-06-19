import streamlit as st
import pandas as pd
import re
import time
import os
import subprocess
from io import BytesIO
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# ============================================================
# 設定
# ============================================================
COMPANY_MAP = {
    "クオール":                "クオール",
    "日本調剤":                "日本調剤",
    "総合メディカル":          "そうごう薬局",
    "アインホールディングス":  "アイン",
    "スギ薬局":                "スギ薬局",
    "ウエルシア":              "ウエルシア薬局",
    "マツモトキヨシ":          "マツモトキヨシ",
    "ツルハ":                  "ツルハ",
    "たんぽぽ薬局":            "たんぽぽ",
    "チューリップ調剤":        "チューリップ",
    "メディカルシステムネットワーク": "なの花薬局",
}

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

# ============================================================
# Selenium ドライバー
# ============================================================
def _find_bin(candidates):
    """システムにインストールされているバイナリのパスを返す"""
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
    options.add_argument("--window-size=1280,800")

    # Chromium本体を自動検出
    chromium = _find_bin(["chromium", "chromium-browser", "google-chrome-stable", "google-chrome"])
    if chromium:
        options.binary_location = chromium

    # ChromeDriverを自動検出
    chromedriver = _find_bin(["chromedriver", "chromium-chromedriver", "chromium.chromedriver"])
    service = Service(chromedriver) if chromedriver else Service()

    return webdriver.Chrome(service=service, options=options)

def wait_for(driver, by, selector, timeout=15):
    return WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((by, selector))
    )

# ============================================================
# スクレイピング処理
# ============================================================
def extract_val(text, pattern):
    m = re.search(pattern, text, re.DOTALL)
    return m.group(1).strip() if m else ""

def extract_pref(address):
    m = re.search(r"(北海道|東京都|大阪府|京都府|[^\s]{2,3}県)", address)
    return m.group(1) if m else ""

def search_and_collect(driver, keyword, status_text, debug=False):
    driver.get(BASE_URL)
    time.sleep(4)

    if debug:
        st.image(driver.get_screenshot_as_png(), caption="① トップページ読み込み後")

    # 薬局タブ → キーワード検索
    try:
        links = driver.find_elements(By.PARTIAL_LINK_TEXT, "キーワードで探す")
        if len(links) >= 2:
            links[1].click()
        elif links:
            links[0].click()
        time.sleep(1.5)
    except Exception:
        pass

    if debug:
        st.image(driver.get_screenshot_as_png(), caption="② キーワードで探すクリック後")
        st.code(f"URL: {driver.current_url}")

    # 施設名称を選択
    try:
        selects = driver.find_elements(By.TAG_NAME, "select")
        for sel in selects:
            opts = [o.text for o in sel.find_elements(By.TAG_NAME, "option")]
            if "施設名称" in opts:
                Select(sel).select_by_visible_text("施設名称")
                break
    except Exception:
        pass

    # キーワード入力
    try:
        inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='text']")
        if inputs:
            inputs[0].clear()
            inputs[0].send_keys(keyword)
    except Exception as e:
        return []

    if debug:
        st.image(driver.get_screenshot_as_png(), caption="③ キーワード入力後")

    # 検索ボタン
    try:
        btns = driver.find_elements(By.XPATH, "//button[contains(text(),'検索')]")
        if btns:
            btns[0].click()
        else:
            inputs[0].submit()
    except Exception:
        pass

    time.sleep(PAGE_DELAY + 1)

    if debug:
        st.image(driver.get_screenshot_as_png(), caption="④ 検索結果ページ")
        all_links = driver.find_elements(By.TAG_NAME, "a")
        link_data = [(l.text.strip()[:40], (l.get_attribute("href") or "")[:80]) for l in all_links if l.text.strip()]
        st.write(f"ページ内リンク数: {len(link_data)}")
        st.dataframe({"テキスト": [t for t,_ in link_data[:30]], "URL": [u for _,u in link_data[:30]]})

    # 全ページのURLを収集
    all_urls = []
    page_num = 1
    while True:
        links = driver.find_elements(By.CSS_SELECTOR,
            "a[href*='S2310'], a[href*='S2400'], a[href*='detail'], "
            "a[href*='juminkanja'], table a, .result-list a, .facility-name a"
        )
        page_urls = []
        for link in links:
            try:
                name = re.sub(r"\s+", " ", link.text).strip()
                href = link.get_attribute("href") or ""
                if name and href and "javascript" not in href and len(name) > 2:
                    page_urls.append((name, href))
            except Exception:
                continue
        all_urls.extend(page_urls)
        status_text.text(f"検索中... ページ {page_num}: {len(page_urls)} 件")

        try:
            next_links = driver.find_elements(By.PARTIAL_LINK_TEXT, "次へ")
            if next_links and next_links[0].is_displayed():
                next_links[0].click()
                time.sleep(PAGE_DELAY)
                page_num += 1
            else:
                break
        except Exception:
            break

    return all_urls

def fetch_detail(driver, name, url):
    store = {
        "施設名": name, "住所": "", "都道府県": "", "地方": "",
        "薬剤師_常勤": "", "薬剤師_非常勤": "", "総取扱処方箋数": "",
        "詳細URL": url
    }
    try:
        driver.get(url)
        time.sleep(2)

        # 「実績、結果に係る事項」タブをクリック
        try:
            tabs = driver.find_elements(By.XPATH,
                "//*[contains(text(),'実績') and (self::a or self::button or self::span or self::li)]")
            if tabs:
                tabs[0].click()
                time.sleep(1)
        except Exception:
            pass

        txt = driver.find_element(By.TAG_NAME, "body").text

        store["薬剤師_常勤"]    = extract_val(txt, r"常勤の人数\s*[：:]\s*([\d,]+)")
        store["薬剤師_非常勤"]  = extract_val(txt, r"非常勤の人数[（(][^）)]*[）)]\s*[：:]\s*([\d,]+)")
        store["総取扱処方箋数"] = extract_val(txt, r"総取[り扱]+処方箋数\s*[：:①②]\s*([\d,]+)")
        store["住所"]           = extract_val(txt, r"所在地\s*[：:]\s*(.+?)[\n\r]")

        pref = extract_pref(store["住所"])
        store["都道府県"] = pref
        store["地方"]     = REGION_MAP.get(pref, "99_不明")

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
            status_text.text(f"📋 詳細取得中 {i+1}/{len(urls)}: {name}")
            progress_bar.progress((i + 1) / len(urls))
            store = fetch_detail(driver, name, url)
            all_stores.append(store)
            time.sleep(DETAIL_DELAY)
    finally:
        driver.quit()
    return all_stores

    keyword = COMPANY_MAP.get(company_name, company_name)
    driver = get_driver()
    all_stores = []
    try:
        urls = search_and_collect(driver, keyword, status_text)
        if not urls:
            return []

        for i, (name, url) in enumerate(urls):
            status_text.text(f"📋 詳細取得中 {i+1}/{len(urls)}: {name}")
            progress_bar.progress((i + 1) / len(urls))
            store = fetch_detail(driver, name, url)
            all_stores.append(store)
            time.sleep(DETAIL_DELAY)
    finally:
        driver.quit()
    return all_stores

def to_excel(stores):
    df = pd.DataFrame(stores)
    sort_cols = [c for c in ["地方","都道府県","施設名"] if c in df.columns]
    df = df.sort_values(sort_cols).reset_index(drop=True)
    col_order = ["施設名","都道府県","地方","住所","薬剤師_常勤","薬剤師_非常勤","総取扱処方箋数","詳細URL"]
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
            cell.fill = fill; cell.font = font
            cell.alignment = Alignment(horizontal="center")
        for col in ws.columns:
            w = max((len(str(c.value)) for c in col if c.value), default=10)
            ws.column_dimensions[col[0].column_letter].width = min(w + 2, 60)
    buf.seek(0)
    return buf, df

# ============================================================
# ============================================================
# Streamlit UI
# ============================================================
st.set_page_config(page_title="薬局情報収集ツール", page_icon="💊", layout="centered")
st.title("💊 薬局情報収集ツール")
st.caption("医療情報ネット（ナビイ）から薬剤師数・処方箋数を自動収集します")
st.divider()

company = st.text_input(
    "① 企業名（ファイル名などに使われます）",
    placeholder="例：総合メディカル、クオール、日本調剤"
)

keyword = st.text_input(
    "② ナビィでの検索ワード（店舗名に使われているブランド名）",
    placeholder="例：そうごう薬局、クオール薬局、日本調剤"
)
st.caption("💡 ①と②が同じ場合はどちらも同じ名前でOKです。ナビイで薬局名を検索して確認できます。")

debug_mode = st.checkbox("🔧 デバッグモード（ブラウザの動作を画像で確認）", value=False)

st.divider()

can_search = bool(company and keyword)
if st.button("🔍 検索開始", type="primary", disabled=not can_search):
    progress = st.progress(0)
    status   = st.empty()
    with st.spinner(f"「{keyword}」で検索中です。店舗数によって数分かかります..."):
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
            data=buf, file_name=fname,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary"
        )
        show_cols = [c for c in ["施設名","都道府県","薬剤師_常勤","薬剤師_非常勤","総取扱処方箋数"] if c in df.columns]
        st.subheader("プレビュー（地域別ソート）")
        st.dataframe(df[show_cols], use_container_width=True)
    else:
        st.warning(f"「{keyword}」で検索しましたが結果が取得できませんでした。\n\n検索ワードを変えて再試行してください。")

st.divider()
st.caption("※ データは医療情報ネット（ナビイ）/ 厚生労働省より取得")

st.divider()
st.caption("※ データは医療情報ネット（ナビイ）/ 厚生労働省より取得")
