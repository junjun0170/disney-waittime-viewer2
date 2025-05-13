import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib
import datetime
import re
from urllib.parse import quote
matplotlib.rcParams['font.family'] = 'Noto Sans CJK JP'

# --- ページ設定 ---
st.set_page_config(page_title="待ち時間グラフ", layout="centered")

# TOPリンク（現在のパスのみ取得）
st.markdown(
    "<a href='/' target='_self' style='font-size:10px; font-weight:bold;'>TOP</a>",
    unsafe_allow_html=True
)

# --- データ読み込み ---
file_id = "1-Yaxjs124GbN3Q1j-AszzUpWYGMQ3xmw"
gsheet_url = f"https://drive.google.com/uc?id={file_id}"
df = pd.read_csv(gsheet_url)
df.columns = df.columns.str.strip()
df['待ち時間'] = pd.to_numeric(df['待ち時間'], errors='coerce').fillna(0)
df['取得時刻'] = pd.to_datetime(df['取得時刻'], errors='coerce')
df['時刻'] = df['取得時刻'].dt.time
df['表示名'] = df['名称'] + "（" + df['エリア'] + "）"

# --- 傾向分類 ---
def judge_recent_decrease(group):
    one_hour_ago = group['取得時刻'].max() - pd.Timedelta(hours=1)
    recent = group[group['取得時刻'] >= one_hour_ago].sort_values('取得時刻')
    if len(recent) >= 2:
        start_value = recent['待ち時間'].iloc[0]
        avg_recent = recent['待ち時間'].mean()
        return "減少" if start_value > avg_recent else "その他"
    else:
        return "その他"

df['傾向'] = df.groupby('表示名', group_keys=False).apply(judge_recent_decrease)

# --- UI ---
st.write("### 🎢 TDS待ち時間")
selected_date = st.date_input("日付を選択", value=datetime.date.today())
query = st.query_params
query = st.query_params
preselected = query.get("selected", "---")

# クエリに変化があったら再実行して画面を更新
if "selected" in query and st.session_state.get("last_selected") != query["selected"]:
    st.session_state["last_selected"] = query["selected"]
    st.rerun()

# --- アコーディオン表示準備 ---
day_df = df[df['取得時刻'].dt.date == selected_date]
latest_df = day_df.sort_values("取得時刻").groupby('表示名').tail(1)

# 📉 減少中
decreasing_df = []
for name, group in day_df.groupby("表示名"):
    group = group.sort_values("取得時刻")
    recent = group[group["取得時刻"] >= group["取得時刻"].max() - pd.Timedelta(hours=1)]
    if len(recent) >= 2 and recent["待ち時間"].mean() < recent["待ち時間"].iloc[0]:
        latest_time = group.iloc[-1]["待ち時間"]
        decreasing_df.append((name, int(latest_time)))

if decreasing_df:
    with st.expander("📉 待ち時間減少中"):
        for name, time in decreasing_df:
            true_name = name.split("（")[0]  # 表示名から名称を抽出
            encoded = quote(true_name)
            st.markdown(
                f"<a href='?selected={encoded}' target='_self' style='font-size:11px'>{name}（{time}分）</a>",
                unsafe_allow_html=True
            )



# ⚠ 一時運営中止
paused_df = latest_df[latest_df["運営状況"] == "一時運営中止"]
if not paused_df.empty:
    with st.expander("⚠ システム調整中"):
        for _, row in paused_df.iterrows():
            encoded = quote(row['名称'])
            st.markdown(
                f"<a href='?selected={encoded}' target='_self' style='font-size:11px'>{row['表示名']}（{int(row['待ち時間'])}分）</a>",
                unsafe_allow_html=True
            )

# 🟥 補足「中」
suspicious_df = latest_df[latest_df["補足情報"].astype(str).str.contains("中", na=False)]
if not suspicious_df.empty:
    with st.expander("🟥 DPA販売中"):
        for _, row in suspicious_df.iterrows():
            encoded = quote(row['名称'])
            st.markdown(
                f"<a href='?selected={encoded}' target='_self' style='font-size:11px'>{row['表示名']}（{int(row['待ち時間'])}分）</a>",
                unsafe_allow_html=True
            )

# プルダウン
name_day = df[df['取得時刻'].dt.date == selected_date]
avg_map = name_day.groupby('名称')['待ち時間'].mean().sort_values(ascending=False)
name_options = ["---"] + avg_map.index.tolist()
name_filter = st.selectbox("アトラクション", name_options, index=name_options.index(preselected) if preselected in name_options else 0)

# --- フィルタ ---
if name_filter != "---":
    filtered = df[(df['取得時刻'].dt.date == selected_date) & (df['名称'] == name_filter)]
else:
    filtered = pd.DataFrame()

# --- グラフ＆表の表示 ---
if not filtered.empty:
    st.write("### 📈 待ち時間グラフ")
    fig, ax = plt.subplots(figsize=(6, 3))

    def extract_time_from_text(text):
        match = re.search(r'(\d{1,2}:\d{2})', str(text))
        return match.group(1) if match else "00:00"

    for title, group in filtered.groupby('表示名'):
        avg_total = group['待ち時間'].mean()
        recent_group = group[group['取得時刻'] >= group['取得時刻'].max() - pd.Timedelta(hours=1)]
        avg_recent = recent_group['待ち時間'].mean() if not recent_group.empty else 0
        group_sorted = group.sort_values('取得時刻')
        latest_row = group_sorted.iloc[-1]

        latest_info_raw = latest_row.get('補足情報', '')
        latest_info = '' if pd.isna(latest_info_raw) else str(latest_info_raw)
        営業時間 = str(latest_row.get('営業時間', ''))
        更新時刻 = str(latest_row.get('更新時刻', ''))

        color = 'black'
        if '中' in latest_info:
            color = 'red'
        elif 'なし' in latest_info:
            color = 'gray'
            change_row = group_sorted[group_sorted['補足情報'] == latest_info].head(1)
            if not change_row.empty:
                end_text = str(change_row.iloc[0]['更新時刻'])
                time_str = extract_time_from_text(end_text)
                latest_info += f" (終了時刻{time_str})"

        st.markdown(
            f"<div style='font-size:13px'>{title}<br>営業時間：{営業時間}<br>{更新時刻}<br><br>"
            f"全体平均：{avg_total:.1f}分　/　直近1時間平均：{avg_recent:.1f}分</div><br>"
            f"<span style='color:{color}'><div style='font-size:13px'>補足：{latest_info}</div></span>",
            unsafe_allow_html=True
        )

        ax.plot(group_sorted['取得時刻'], group_sorted['待ち時間'], marker=None, label=title)

    legend = ax.legend()
    if legend:
        legend.remove()
    ax.set_xlabel("Time")
    ax.set_ylabel("Wait Time")
    ax.grid(True, linestyle='--', alpha=0.5)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    fig.autofmt_xdate()
    fig.tight_layout()
    st.pyplot(fig)

    st.write("### 📋 待ち時間データ")
    two_hours_ago = filtered['取得時刻'].max() - pd.Timedelta(hours=2)
    recent_filtered = filtered[filtered['取得時刻'] >= two_hours_ago].sort_values('取得時刻', ascending=False)
    st.dataframe(recent_filtered[['時刻', '待ち時間', '運営状況', '補足情報']], use_container_width=True)
