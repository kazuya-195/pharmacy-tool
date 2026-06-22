import streamlit as st
import requests
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
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ============================================================
# 設定
# ============================================================
SEARCH_API = "https://www.iryou.teikyouseido.mhlw.go.jp/znk-web/juminkanja/S2300/yakkyokuSearch"
RESULTS_BASE = "https://www.iryou.teikyouseido.mhlw.go.jp/znk-web/juminkanja/S2400/initialize?id="

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
PAGE_DELAY = 2.5
DETAIL_DELAY = 1.5

# ============================================================
# Step1: Seleniumのセッションを使ってAPIで検索IDを取得
# ============================================================
def get_session_id_with_driver(driver, keyword: str, debug: bool) -> str | None:
    """
    ① Seleniumでナビィのトップページを開く（セッション確立）
    ② そのクッキーをrequestsに渡してAPIを叩く
    ③ セッションIDを返す
    """
    base = "https://www.iryou.teikyouseido.mhlw.go.jp"

    # ナビィのトップを開いてセッションを確立
    driver.get(f"{base}/znk-web/juminkanja/S2300/initialize")
    time.sleep(4)

    if debug:
        st.image(driver.get_screenshot_as_png(), caption="① トップページ（セッション確立）")

    # Seleniumのクッキーをrequestsセッションに移植
    session = requests.Session()
    session.headers.update({
        "User-Agent": driver.execute_script("return navigator.userAgent;"),
        "Referer": f"{base}/znk-web/juminkanja/S2300/initialize",
    })
    for cookie in driver.get_cookies():
        session.cookies.set(cookie["name"], cookie["value"],
                            domain=cookie.get("domain",""))

    # 同じセッションでAPIを叩く
    params = {
        "XCHARSET": "utf-8",
        "XPARAM": "keyword",
        "iyakuKbn": "2",
        "lang": "ja",
        "keywordType": "2",
        "keyword": keyword,
    }
    try:
        r = session.get(SEARCH_API, params=params, timeout=15)
        data = r.json()
        session_id = data.get("result", {}).get("id")
        if debug:
            st.info(f"APIレスポンス: {data}")
        return session_id
    except Exception as e:
        st.error(f"API呼び出し失敗: {e}")
        return None

# ============================================================
# Selenium ドライバー
# ============================================================
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
    options.add_argument("--window-size=1280,800")
    chromium = _find_bin(["chromium", "chromium-browser", "google-chrome-stable"])
    if chromium:
        options.binary_location = chromium
    chromedriver = _find_bin(["chromedriver", "chromium-chromedriver"])
    service = Service(chromedriver) if chromedriver else Service()
    return webdriver.Chrome(service=service, options=options)

# ============================================================
# Step2: 結果ページから店舗リンクを収集
# ============================================================
def collect_detail_urls(driver, session_id: str, status_text, debug: bool) -> list:
    results_url = RESULTS_BASE + session_id
    driver.get(results_url)
    time.sleep(PAGE_DELAY)

    if debug:
        st.image(driver.get_screenshot_as_png(), caption="① 結果ページ（直接アクセス）")

    # モーダルを閉じる
    for sel in ["button.modalClose", "[class*='modal'] button", "button"]:
        try:
            btns = driver.find_elements(By.CSS_SELECTOR, sel)
            for b in btns:
                if b.is_displayed() and b.text.strip() in ("閉じる", "OK", "×"):
                    driver.execute_script("arguments[0].click();", b)
                    time.sleep(1)
                    break
        except Exception:
            pass

    time.sleep(1)

    if debug:
        st.image(driver.get_screenshot_as_png(), caption="② モーダル処理後")

    # 全ページを巡回してリンク収集（最大20ページ）
    all_urls = []
    seen = set()  # ← ループ外に置くことで全ページ通じて重複除外
    page_num = 1
    MAX_PAGES = 20
    consecutive_empty = 0

    while page_num <= MAX_PAGES:
        # JavaScript で全リンクを取得
        js_links = driver.execute_script("""
            return Array.from(document.querySelectorAll('a')).map(l => ({
                text: (l.innerText || l.textContent || '').trim(),
                href: l.href || ''
            }));
        """)

        # 結果アイテムの要素も確認（liやtr）
        result_els = driver.execute_script("""
            var items = document.querySelectorAll(
                'ul li a, .searchResult a, .resultList a, table tbody tr td a, .list-item a'
            );
            return Array.from(items).map(a => ({
                text: (a.innerText || '').trim(),
                href: a.href || ''
            }));
        """)

        if debug:
            st.write(f"ページ{page_num}: 全リンク={len(js_links)}件, result要素={len(result_els)}件")
            # result要素の最初の10件を表示（URLパターン確認用）
            if result_els:
                st.write("result要素（先頭10件）:")
                st.dataframe({"テキスト": [r.get('text','')[:30] for r in result_els[:10]],
                              "URL": [r.get('href','')[:80] for r in result_els[:10]]})
            # 全リンクの中でiryou.teikyouseidoを含むものを表示
            iryou_links = [l for l in js_links
                          if "iryou.teikyouseido" in l.get('href','')
                          and len(l.get('text','')) > 3
                          and 'S23' not in l.get('href','')
                          and 'S29' not in l.get('href','')]
            st.write(f"iryou系リンク（S23/S29除く）: {len(iryou_links)}件")
            st.dataframe({"テキスト": [l['text'][:40] for l in iryou_links[:20]],
                          "URL": [l['href'][:80] for l in iryou_links[:20]]})

        # 薬局詳細ページのリンクを抽出
        page_urls = []
        SKIP = {"ホーム","トップ","次へ","前へ","閉じる","戻る","条件を絞り込む",
                "全国の薬局","検索条件","お気に入り","ログイン","利用規約","関係者",
                "医療機関を探す","薬局を探す","キーワードで探す"}
        SKIP_PATTERNS = ["window", "オブジェクト", "//", "function", "undefined",
                         "null", "Copyright", "javascript", "Script"]

        for link_list in [result_els, js_links]:
            for item in link_list:
                name = re.sub(r"\s+", " ", item.get("text","")).strip()
                href = item.get("href","")
                # 不正なエントリを除外
                if any(p in name for p in SKIP_PATTERNS):
                    continue
                if (name and href and len(name) >= 3
                        and "javascript" not in href
                        and href not in seen
                        and name not in SKIP
                        and any(p in name for p in SKIP_PATTERNS) is False
                        and "iryou.teikyouseido" in href
                        and not any(skip in href for skip in
                                    ["S2300","S2310","S2320","S2400","S2410",
                                     "S2800","S2900","S3000","S3100","S3400",
                                     "S3870","S3880","initialize?fo"])):
                    page_urls.append((name, href))
                    seen.add(href)

        all_urls.extend(page_urls)
        status_text.text(f"結果収集中... ページ{page_num}: {len(page_urls)}件 / 累計{len(all_urls)}件")

        # 0件が3回続いたら終了（最終ページ後の空ページ対策）
        if len(page_urls) == 0:
            consecutive_empty += 1
            if consecutive_empty >= 3:
                break
        else:
            consecutive_empty = 0

        # 次のページへ（ページ下部のボタンを使う＝最後の>>）
        try:
            clicked_next = False
            for sel_xpath in [
                "//*[normalize-space(text())='>>' and not(@disabled)]",
                "//*[normalize-space(text())='次へ' and not(@disabled)]",
                "//*[contains(@class,'next') and not(@disabled)]",
            ]:
                btns = [b for b in driver.find_elements(By.XPATH, sel_xpath)
                        if b.is_displayed() and b.is_enabled()]
                if btns:
                    # 最後の>>（ページ下部のページネーション）をクリック
                    driver.execute_script("arguments[0].click();", btns[-1])
                    time.sleep(PAGE_DELAY + 1)
                    clicked_next = True
                    page_num += 1
                    break

            if not clicked_next:
                break

        except Exception:
            break

    return all_urls

# ============================================================
# Step3: 各店舗の詳細ページからデータ取得
# ============================================================
def extract_val(text, pattern):
    m = re.search(pattern, text, re.DOTALL)
    return m.group(1).strip() if m else ""

def extract_pref(address):
    m = re.search(r"(北海道|東京都|大阪府|京都府|[^\s]{2,3}県)", address)
    return m.group(1) if m else ""

def fetch_detail(driver, name, url):
    store = {"施設名": name, "住所": "", "都道府県": "", "地方": "",
             "薬剤師_常勤": "", "薬剤師_非常勤": "", "総取扱処方箋数": "",
             "詳細URL": url}
    try:
        driver.get(url)
        time.sleep(5)  # ページ描画を待つ

        # ── 基本情報タブで住所を取得 ──────────────────────────────
        txt_basic = driver.find_element(By.TAG_NAME, "body").text

        # 住所のパターンを複数試みる
        addr = ""
        for pattern in [
            r"所在地\s*[：:]\s*(.+?)[\n\r]",           # 所在地：〇〇
            r"所在地\s*\n(.+?)[\n\r]",                  # 所在地\n〇〇
            r"〒\d{3}[-－]\d{4}\s*(.+?)[\n\r]",        # 〒xxx-xxxx 住所
            r"((?:北海道|東京都|大阪府|京都府|.{2,3}県).{5,50})[\n\r]",  # 都道府県から始まる行
        ]:
            addr = extract_val(txt_basic, pattern)
            if addr and len(addr) > 5:
                break
        store["住所"] = addr.replace("Googleマップで見る", "").replace("Google マップで見る", "").strip()

        # ── 実績タブをクリック ──────────────────────────────────────
        try:
            all_tabs = driver.find_elements(By.XPATH, "//*[contains(text(),'実績')]")
            for tab in all_tabs:
                try:
                    if tab.is_displayed():
                        driver.execute_script(
                            "arguments[0].scrollIntoView(true); arguments[0].click();", tab)
                        time.sleep(3)
                        break
                except Exception:
                    continue
        except Exception:
            pass

        # ── 実績タブの本文から数値を取得 ───────────────────────────
        txt = driver.find_element(By.TAG_NAME, "body").text

        store["薬剤師_常勤"]    = extract_val(txt, r"常勤の人数[^\d]*([\d,]+)")
        store["薬剤師_非常勤"]  = extract_val(txt, r"非常勤の人数[^）]*[）)][^\d]*([\d,]+)")
        store["総取扱処方箋数"] = extract_val(txt, r"総取扱処方箋数[^\d]*([\d,]+)")

        pref = extract_pref(store["住所"])
        store["都道府県"] = pref
        store["地方"]     = REGION_MAP.get(pref, "99_不明")

    except Exception as e:
        store["エラー"] = str(e)
    return store

# ============================================================
# メイン処理
# ============================================================
def run(company, keyword, progress_bar, status_text, debug):
    # Step1: Seleniumでセッション確立 → APIで検索ID取得
    status_text.text("🔍 ナビィに接続してセッションを確立中...")
    driver = get_driver()
    all_stores = []
    try:
        session_id = get_session_id_with_driver(driver, keyword, debug)
        if not session_id:
            return []

        if debug:
            st.info(f"セッションID取得: {session_id}")

        # Step2: 結果ページを開いてリンク収集
        status_text.text("📋 検索結果を取得中...")
        urls = collect_detail_urls(driver, session_id, status_text, debug)

        if not urls:
            st.warning("詳細ページのリンクが見つかりませんでした。デバッグモードで確認してください。")
            return []

        # Step3: 各詳細ページからデータ取得
        for i, (name, url) in enumerate(urls):
            status_text.text(f"📊 詳細取得中 {i+1}/{len(urls)}: {name}")
            progress_bar.progress((i+1)/len(urls))
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
            ws.column_dimensions[col[0].column_letter].width = min(w+2, 60)
    buf.seek(0)
    return buf, df

# ============================================================
# ============================================================
# Streamlit UI（最終版）
# ============================================================
st.set_page_config(page_title="薬局情報収集ツール", page_icon="💊", layout="centered")

st.title("💊 薬局情報収集ツール")
st.caption("医療情報ネット（ナビイ）から薬局の薬剤師数・処方箋数を自動収集してExcelに出力します")
st.divider()

col1, col2 = st.columns(2)
with col1:
    company = st.text_input("① 企業名",
        placeholder="例：株式会社裕生堂")
with col2:
    keyword = st.text_input("② ナビィ検索ワード",
        placeholder="例：裕生堂薬局")

st.caption("💡 ②はナビィで薬局名として表示されているブランド名を入力してください。①と同じでOKな場合も多いです。")

with st.expander("🔧 開発者向けオプション"):
    debug_mode = st.checkbox("デバッグモード（ブラウザの動作を画像で確認）", value=False)

st.divider()

ready = bool(company and keyword)
if st.button("🔍 収集開始", type="primary", disabled=not ready, use_container_width=True):
    progress = st.progress(0)
    status   = st.empty()

    with st.spinner(f"「{keyword}」を収集中です。店舗数によって数分かかります..."):
        try:
            stores = run(company, keyword, progress, status, debug_mode)
        except Exception as e:
            st.error(f"エラーが発生しました: {e}")
            stores = []

    if stores:
        progress.progress(1.0)
        status.empty()

        buf, df = to_excel(stores)
        fname = f"{company}_薬局一覧_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"

        st.success(f"✅  {len(stores)} 件を取得しました")

        st.download_button(
            label="📥 Excelをダウンロード",
            data=buf,
            file_name=fname,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            use_container_width=True,
        )

        st.subheader("プレビュー（地域別ソート）")
        show_cols = [c for c in
            ["施設名","都道府県","住所","薬剤師_常勤","薬剤師_非常勤","総取扱処方箋数"]
            if c in df.columns]
        st.dataframe(df[show_cols], use_container_width=True, hide_index=True)

    else:
        st.warning(
            "結果が取得できませんでした。\n\n"
            "② のナビィ検索ワードを確認してください。"
            "ナビィ（https://www.iryou.teikyouseido.mhlw.go.jp）で実際に検索して、"
            "出てくる薬局名のブランド名を入力してください。"
        )

st.divider()
st.caption("データ出典：医療情報ネット（ナビイ）/ 厚生労働省・都道府県")
