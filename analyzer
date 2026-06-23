import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from io import BytesIO

st.set_page_config(page_title="薬局 生産性分析ツール", page_icon="📊", layout="wide")

st.title("📊 薬局 生産性分析ツール")
st.caption("薬局情報収集ツールで出力したExcelをアップロードして、処方箋枚数・人時生産性を算出・可視化します")
st.divider()

# ============================================================
# ① ファイルアップロード
# ============================================================
uploaded = st.file_uploader("① 収集ツールのExcelをアップロード", type=["xlsx"])

if not uploaded:
    st.info("💡 薬局情報収集ツールでダウンロードしたExcelファイルをアップロードしてください。")
    st.stop()

try:
    df_raw = pd.read_excel(uploaded)
except Exception as e:
    st.error(f"Excelの読み込みに失敗しました: {e}")
    st.stop()

required = ["施設名", "総取扱処方箋数", "薬剤師_常勤"]
missing = [c for c in required if c not in df_raw.columns]
if missing:
    st.error(f"必要な列が見つかりません: {missing}")
    st.stop()

st.success(f"✅ {len(df_raw)} 件読み込みました")
st.divider()

# ============================================================
# ② 営業条件の入力
# ============================================================
st.subheader("② 営業条件を入力（全店舗共通）")
col1, col2 = st.columns(2)
with col1:
    work_days = st.number_input("月間営業日数（日）", min_value=1, max_value=31, value=25, step=1)
with col2:
    work_hours = st.number_input("1日の営業時間（時間）", min_value=0.5, max_value=24.0, value=8.0, step=0.5)

st.divider()

# ============================================================
# ③ 計算
# ============================================================
def to_num(series):
    return pd.to_numeric(
        series.astype(str).str.replace(",", "", regex=False).str.strip(),
        errors="coerce"
    )

df = df_raw.copy()
df["総取扱処方箋数_num"] = to_num(df["総取扱処方箋数"])
df["薬剤師_常勤_num"]   = to_num(df["薬剤師_常勤"])
df["月間処方箋枚数"]           = (df["総取扱処方箋数_num"] / 12).round(1)
df["1日処方箋枚数"]            = (df["月間処方箋枚数"] / work_days).round(1)
df["1時間あたり処方箋枚数"]    = (df["1日処方箋枚数"] / work_hours).round(1)
df["人時生産性"]               = (df["1時間あたり処方箋枚数"] / df["薬剤師_常勤_num"]).round(2)

# ============================================================
# ④ 分析結果テーブル
# ============================================================
st.subheader("③ 分析結果")

no_rx = df["総取扱処方箋数_num"].isna().sum()
no_ph = df["薬剤師_常勤_num"].isna().sum()
if no_rx > 0:
    st.warning(f"⚠️ 総取扱処方箋数が取得できていない店舗が {no_rx} 件あります")
if no_ph > 0:
    st.warning(f"⚠️ 常勤薬剤師数が取得できていない店舗が {no_ph} 件あります（人時生産性が空欄）")

display_cols = [c for c in ["施設名","都道府県","地方"] if c in df.columns] + [
    "総取扱処方箋数_num","月間処方箋枚数","1日処方箋枚数","1時間あたり処方箋枚数",
    "薬剤師_常勤_num","人時生産性"
]
df_view = df[display_cols].rename(columns={
    "総取扱処方箋数_num":"年間処方箋数","薬剤師_常勤_num":"常勤薬剤師数",
    "人時生産性":"人時生産性（枚/人/時間）"
})
st.dataframe(df_view, use_container_width=True, hide_index=True)

# サマリー
valid    = df.dropna(subset=["1日処方箋枚数"])
valid_ph = df.dropna(subset=["人時生産性"])
c1, c2, c3, c4 = st.columns(4)
c1.metric("月間処方箋（平均）", f"{valid['月間処方箋枚数'].mean():.0f} 枚")
c2.metric("1日処方箋（平均）",  f"{valid['1日処方箋枚数'].mean():.1f} 枚")
c3.metric("1時間あたり（平均）",f"{valid['1時間あたり処方箋枚数'].mean():.1f} 枚")
v = valid_ph["人時生産性"].mean()
c4.metric("人時生産性（平均）", f"{v:.2f} 枚/人時" if not pd.isna(v) else "—")

st.divider()

# ============================================================
# ⑤ 散布図
# ============================================================
st.subheader("④ 散布図：1日処方箋枚数 × 人時生産性")

df_plot = df.dropna(subset=["1日処方箋枚数","人時生産性"]).copy()

if df_plot.empty:
    st.warning("散布図を描画するのに必要なデータがありません。")
    st.stop()

# --- エリア選択 ---
area_options = ["全店舗"]
for col in ["地方", "都道府県"]:
    if col in df_plot.columns:
        vals = sorted(df_plot[col].dropna().unique().tolist())
        area_options += [f"【{col}】{v}" for v in vals]

left, right = st.columns([2, 1])
with left:
    area_sel = st.selectbox("エリアで絞り込む", area_options)

if area_sel == "全店舗":
    df_chart = df_plot.copy()
else:
    # 「【地方】07_九州沖縄」→ col=地方, val=07_九州沖縄
    col_name = area_sel.split("】")[0].replace("【","")
    val_name = area_sel.split("】")[1]
    df_chart = df_plot[df_plot[col_name] == val_name].copy()

if df_chart.empty:
    st.warning("選択したエリアにデータがありません。")
    st.stop()

# --- ゾーンしきい値 ---
with right:
    x_max = float(df_chart["1日処方箋枚数"].max())
    y_max = float(df_chart["人時生産性"].max())
    x_thresh = st.slider(
        "X軸しきい値（1日処方箋枚数）",
        min_value=0.0, max_value=max(x_max, 10.0),
        value=round(df_chart["1日処方箋枚数"].median(), 1),
        step=1.0
    )
    y_thresh = st.slider(
        "Y軸しきい値（人時生産性）",
        min_value=0.0, max_value=max(y_max, 1.0),
        value=round(df_chart["人時生産性"].median(), 2),
        step=0.1
    )

# --- 各店舗のゾーン判定 ---
def zone_label(row):
    hi_x = row["1日処方箋枚数"] >= x_thresh
    hi_y = row["人時生産性"]    >= y_thresh
    if hi_x and hi_y:   return "高負荷・ターゲット候補"
    if hi_x and not hi_y: return "リソース余力ポテンシャル"
    if not hi_x and hi_y: return "低負荷・高生産性"
    return "低負荷・低生産性"

df_chart["ゾーン"] = df_chart.apply(zone_label, axis=1)

ZONE_COLOR = {
    "高負荷・ターゲット候補":     "#C8860A",
    "リソース余力ポテンシャル":    "#1a7a6e",
    "低負荷・高生産性":            "#1F4E79",
    "低負荷・低生産性":            "#999999",
}

# --- Plotly図 ---
fig = go.Figure()

# ゾーン背景
x_plot_max = max(df_chart["1日処方箋枚数"].max() * 1.2, x_thresh * 1.5, 10)
y_plot_max = max(df_chart["人時生産性"].max()    * 1.2, y_thresh * 1.5, 1)

fig.add_shape(type="rect", x0=x_thresh, x1=x_plot_max, y0=y_thresh, y1=y_plot_max,
              fillcolor="#C8860A", opacity=0.08, line_width=0, layer="below")
fig.add_shape(type="rect", x0=x_thresh, x1=x_plot_max, y0=0, y1=y_thresh,
              fillcolor="#1a7a6e", opacity=0.08, line_width=0, layer="below")

# ゾーンラベル
fig.add_annotation(x=(x_thresh + x_plot_max)/2, y=y_plot_max * 0.93,
                   text="<b>高負荷・ターゲット候補</b>",
                   font=dict(size=13, color="#C8860A"), showarrow=False)
fig.add_annotation(x=(x_thresh + x_plot_max)/2, y=y_thresh * 0.15,
                   text="<b>リソース余力ポテンシャル店舗</b>",
                   font=dict(size=13, color="#1a7a6e"), showarrow=False)

# しきい値の縦横線
fig.add_shape(type="line", x0=x_thresh, x1=x_thresh, y0=0, y1=y_plot_max,
              line=dict(color="#aaa", width=1, dash="dash"))
fig.add_shape(type="line", x0=0, x1=x_plot_max, y0=y_thresh, y1=y_thresh,
              line=dict(color="#aaa", width=1, dash="dash"))

# 店舗ごとに散布
hover_cols = ["施設名","都道府県","地方"] if "地方" in df_chart.columns else ["施設名","都道府県"]
for zone, group in df_chart.groupby("ゾーン"):
    color = ZONE_COLOR.get(zone, "#999")
    customdata = group[hover_cols].values
    extra_lines = "<br>".join(
        [f"{c}: %{{customdata[{i}]}}" for i, c in enumerate(hover_cols)]
    )
    hover_tmpl = (
        f"{extra_lines}"
        "<br>1日処方箋: %{x:.1f} 枚"
        "<br>人時生産性: %{y:.2f} 枚/人時"
        "<extra></extra>"
    )
    fig.add_trace(go.Scatter(
        x=group["1日処方箋枚数"],
        y=group["人時生産性"],
        mode="markers+text",
        name=zone,
        marker=dict(size=11, color=color, line=dict(width=1, color="white")),
        text=group["施設名"].str.replace(r"薬局.*", "…", regex=True),
        textposition="top center",
        textfont=dict(size=10, color=color),
        customdata=customdata,
        hovertemplate=hover_tmpl,
    ))

fig.update_layout(
    xaxis=dict(title="1日あたり処方箋枚数（枚）", range=[0, x_plot_max], gridcolor="#eee"),
    yaxis=dict(title="人時生産性（枚/人/時間）",  range=[0, y_plot_max], gridcolor="#eee"),
    plot_bgcolor="white",
    paper_bgcolor="white",
    legend=dict(orientation="h", yanchor="bottom", y=-0.25, xanchor="center", x=0.5),
    margin=dict(l=60, r=30, t=30, b=80),
    height=560,
    font=dict(family="Noto Sans JP, sans-serif"),
)

st.plotly_chart(fig, use_container_width=True,
                config={"toImageButtonOptions": {"format": "png", "filename": "pharmacy_scatter",
                                                 "width": 1400, "height": 800, "scale": 2},
                        "displaylogo": False})

st.caption("💡 グラフ右上のカメラアイコン（📷）からPNG画像として保存できます。点にカーソルを合わせると店舗詳細が表示されます。")

st.divider()

# ============================================================
# ⑥ Excel ダウンロード
# ============================================================
out_cols = [c for c in ["施設名","都道府県","地方","住所"] if c in df.columns] + [
    "総取扱処方箋数_num","月間処方箋枚数","1日処方箋枚数",
    "1時間あたり処方箋枚数","薬剤師_常勤_num","人時生産性"
]
df_out = df[out_cols].rename(columns={
    "総取扱処方箋数_num":"年間処方箋数","薬剤師_常勤_num":"常勤薬剤師数",
    "人時生産性":"人時生産性（枚/人/時間）"
})

buf = BytesIO()
with pd.ExcelWriter(buf, engine="openpyxl") as writer:
    df_out.to_excel(writer, index=False, sheet_name="生産性分析")
    ws = writer.sheets["生産性分析"]
    from openpyxl.styles import PatternFill, Font, Alignment
    fill = PatternFill(fill_type="solid", fgColor="1F4E79")
    font = Font(color="FFFFFF", bold=True)
    for cell in ws[1]:
        cell.fill = fill; cell.font = font
        cell.alignment = Alignment(horizontal="center")
    for col in ws.columns:
        w = max((len(str(c.value or "")) for c in col), default=10)
        ws.column_dimensions[col[0].column_letter].width = min(w + 2, 40)
buf.seek(0)

from datetime import datetime
st.download_button(
    label="📥 分析結果をExcelでダウンロード",
    data=buf,
    file_name=f"薬局生産性分析_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    type="primary", use_container_width=True,
)
st.divider()
st.caption(f"計算条件：月間営業日数 {work_days}日 ／ 1日営業時間 {work_hours}時間")
