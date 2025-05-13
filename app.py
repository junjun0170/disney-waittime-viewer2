import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib
import datetime
import re

# 本番対応フォント（文字化け防止）
matplotlib.rcParams['font.family'] = 'Noto Sans CJK JP'

# --- ページ設定 ---
st.set_page_config(page_title="待ち時間グラフ", layout="centered")

# --- データ読み込み ---
file_id = "12RIUjsM110hw6tMpa_vitk2WCH1pdwZQ"
gsheet_url = f"https://drive.google.com/uc?id={file_id}"
df = pd.read_csv(gsheet_url)
df.columns = df.columns.str.strip()
df['待ち時間'] = pd.to_numeric(df['待ち時間'], errors='coerce').fillna(0)
df['取得時刻'] = pd.to_datetime(df['取得時刻'], errors='coerce')
df['時刻'] = df['取得時刻'].dt.time
df['表示名'] = df['名称'] + "（" + df['エリア'] + "）"

# --- 傾向分類（直近1時間で減少） ---
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

trend_filter = st.selectbox("傾向", ["全て", "減少"], index=0)
name_day = df[df['取得時刻'].dt.date == datetime.date.today()]
if trend_filter != "全て":
    name_day = name_day[name_day['傾向'] == trend_filter]

avg_map = name_day.groupby('名称')['待ち時間'].mean().sort_values(ascending=False)
name_options = ["---"] + avg_map.index.tolist()
name_filter = st.selectbox("アトラクション", name_options, index=0)

# --- フィルタ処理 ---
if name_filter != "---":
    filtered = df[df['取得時刻'].dt.date == datetime.date.today()]
    if trend_filter != "全て":
        filtered = filtered[filtered['傾向'] == trend_filter]
    filtered = filtered[filtered['名称'] == name_filter]
else:
    filtered = pd.DataFrame()

# --- グラフ＆表の表示 ---
if not filtered.empty:
    st.write("### 📈 待ち時間グラフ")

    fig, ax = plt.subplots(figsize=(6, 3))
    legend_texts = []
    legend_colors = []

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

        label_text = title
        ax.plot(group_sorted['取得時刻'], group_sorted['待ち時間'], marker='o', label=label_text)
        legend_texts.append(label_text)
        legend_colors.append(color)

    legend = ax.legend(loc="upper left", fontsize=8)
    for text, color in zip(legend.get_texts(), legend_colors):
        text.set_color(color)

    ax.set_xlabel("取得時刻")
    ax.set_ylabel("待ち時間（分）")
    ax.grid(True, linestyle='--', alpha=0.5)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    fig.autofmt_xdate()
    fig.tight_layout()
    st.pyplot(fig)

    st.write("### 📋 待ち時間データ")
    two_hours_ago = filtered['取得時刻'].max() - pd.Timedelta(hours=2)
    recent_filtered = filtered[filtered['取得時刻'] >= two_hours_ago].sort_values('取得時刻', ascending=False)
    st.dataframe(recent_filtered[['時刻', '待ち時間', '運営状況', '補足情報']], use_container_width=True)
