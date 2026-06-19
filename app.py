import subprocess, sys, os

# Streamlit Cloud でPlaywrightのブラウザを自動インストール
if not os.path.exists(os.path.expanduser("~/.cache/ms-playwright/chromium-1169")):
    subprocess.run(["playwright", "install", "chromium"], check=True)

import streamlit as st
import asyncio
import pandas as pd
import re
import nest_asyncio
from io import BytesIO
from datetime import datetime
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

nest_asyncio.apply()

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

BASE_URL   = "https://www.iryou.teikyouseido.mhlw.go.jp/znk-web/juminkanja/S2300/initialize"
TIMEOUT_MS = 20000

# ============================================================
# スクレイピング処理
# ============================================================
def extract_val(text, pattern):
    m = re.search(pattern, text, re.DOTALL)
    return m.group(1).strip() if m else ""

def extract_pref(address):
    m = re.search(r"(北海道|東京都|大阪府|京都府|[^\s]{2,3}県)", address)
    return m.group(1) if m else ""

async def search_urls(page, keyword):
    await page.goto(BASE_URL, timeout=TIMEOUT_MS * 2)
    await page.wait_for_load_state("networkidle", timeout=TIMEOUT_MS)
    try:
        await page.locator("text=薬局を探す").first.click(timeout=TIMEOUT_MS)
        await page.wait_for_timeout(700)
        links = await page.locator("a:has-text('キーワードで探す')").all()
        await (links[1] if len(links) >= 2 else links[0]).click(timeout=TIMEOUT_MS)
        await page.wait_for_timeout(800)
    except Exception:
        pass
    try:
        for sel in await page.locator("select").all():
            opts = await sel.evaluate("el => Array.from(el.options).map(o => o.text)")
            if "施設名称" in opts:
                await sel.select_option(label="施設名称")
                break
    except Exception:
        pass
    try:
        inputs = await page.locator("input[type='text']").all()
        await inputs[0].fill(keyword)
    except Exception:
        return []
    try:
        await page.locator("button:has-text('検索')").first.click(timeout=TIMEOUT_MS)
    except Exception:
        await page.keyboard.press("Enter")
    await page.wait_for_load_state("networkidle", timeout=TIMEOUT_MS)
    await page.wait_for_timeout(1500)

    all_urls, page_num = [], 1
    while True:
        links = await page.locator(
            "a[href*='S2310'], a[href*='S2400'], a[href*='detail'], table a, .facility-name a"
        ).all()
        page_urls = []
        for link in links:
            try:
                name = re.sub(r"\s+", " ", await link.inner_text()).strip()
                href = await link.get_attribute("href")
                if name and href:
                    if href.startswith("/"):
                        href = "https://www.iryou.teikyouseido.mhlw.go.jp" + href
                    page_urls.append((name, href))
            except Exception:
                continue
        all_urls.extend(page_urls)
        try:
            next_btn = page.locator("a:has-text('次へ'), a.next").first
            if not await next_btn.is_visible() or len(page_urls) == 0:
                break
            await next_btn.click(timeout=TIMEOUT_MS)
            await page.wait_for_load_state("networkidle", timeout=TIMEOUT_MS)
            await page.wait_for_timeout(1500)
            page_num += 1
        except Exception:
            break
    return all_urls

async def fetch_detail(context, name, url):
    store = {"施設名": name, "住所": "", "都道府県": "", "地方": "",
             "薬剤師_常勤": "", "薬剤師_非常勤": "", "総取扱処方箋数": "", "詳細URL": url}
    try:
        p = await context.new_page()
        await p.goto(url, timeout=TIMEOUT_MS * 2)
        await p.wait_for_load_state("networkidle", timeout=TIMEOUT_MS)
        try:
            tab = p.locator("text=実績、結果に係る事項, a:has-text('実績'), button:has-text('実績')").first
            await tab.click(timeout=TIMEOUT_MS)
            await p.wait_for_timeout(1000)
        except Exception:
            pass
        txt = await p.inner_text("body")
        store["薬剤師_常勤"]    = extract_val(txt, r"常勤の人数\s*[：:]\s*([\d,]+)")
        store["薬剤師_非常勤"]  = extract_val(txt, r"非常勤の人数[（(][^）)]*[）)]\s*[：:]\s*([\d,]+)")
        store["総取扱処方箋数"] = extract_val(txt, r"総取[り扱]+処方箋数\s*[：:①②]\s*([\d,]+)")
        store["住所"]           = extract_val(txt, r"所在地\s*[：:]\s*(.+?)[\n\r]")
        pref = extract_pref(store["住所"])
        store["都道府県"] = pref
        store["地方"]     = REGION_MAP.get(pref, "99_不明")
        await p.close()
    except Exception as e:
        store["エラー"] = str(e)
    return store

async def run_scrape(company_name, progress_bar, status_text):
    keyword = COMPANY_MAP.get(company_name, company_name)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        status_text.text("🔍 ナビィで検索中...")
        urls = await search_urls(page, keyword)

        if not urls:
            await browser.close()
            return []

        stores = []
        for i, (name, url) in enumerate(urls):
            status_text.text(f"📋 詳細取得中... {i+1}/{len(urls)}: {name}")
            progress_bar.progress((i + 1) / len(urls))
            store = await fetch_detail(context, name, url)
            stores.append(store)
            await asyncio.sleep(1.2)

        await browser.close()
    return stores

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
            cell.fill = fill
            cell.font = font
            cell.alignment = Alignment(horizontal="center")
        for col in ws.columns:
            w = max((len(str(c.value)) for c in col if c.value), default=10)
            ws.column_dimensions[col[0].column_letter].width = min(w + 2, 60)
    buf.seek(0)
    return buf, df

# ============================================================
# Streamlit UI
# ============================================================
st.set_page_config(page_title="薬局情報収集ツール", page_icon="💊", layout="centered")

st.title("💊 薬局情報収集ツール")
st.caption("医療情報ネット（ナビイ）から薬剤師数・処方箋数を自動収集します")
st.divider()

company = st.text_input(
    "調べたい企業名を入力",
    placeholder="例：クオール　/　日本調剤　/　総合メディカル"
)

known = list(COMPANY_MAP.keys())
st.caption(f"登録済み企業: {' / '.join(known)}")

if st.button("🔍 検索開始", type="primary", disabled=not company):
    progress = st.progress(0)
    status   = st.empty()

    with st.spinner("収集中です。店舗数によって数分かかります..."):
        try:
            stores = asyncio.run(run_scrape(company, progress, status))
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
            type="primary"
        )

        st.subheader("プレビュー（地域別ソート）")
        show_cols = [c for c in ["施設名","都道府県","薬剤師_常勤","薬剤師_非常勤","総取扱処方箋数"] if c in df.columns]
        st.dataframe(df[show_cols], use_container_width=True)
    else:
        st.warning("結果が取得できませんでした。企業名を確認してください。")

st.divider()
st.caption("※ データは医療情報ネット（ナビイ）/ 厚生労働省より取得")
