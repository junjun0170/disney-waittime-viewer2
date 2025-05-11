#!/usr/bin/env python
# coding: utf-8

# In[7]:


import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import datetime
import matplotlib.dates as mdates

st.set_page_config(layout="wide")
plt.rcParams['font.family'] = 'Meiryo'  # 日本語対応

# === Google Drive 共有リンクからファイルIDを取得して貼り付け ===
FILE_ID = "12RIUjsM110hw6tMpa_vitk2WCH1pdwZQ"  # ← ここに差し替える
CSV_URL = f"https://drive.google.com/uc?id={FILE_ID}"

# === CSV読み込み ===
@st.cache_data(ttl=300)  # 5分キャッシュ
def load_data():
    df = pd.read_csv(CSV_URL)
    df.columns = df.columns.str.strip()
    df['待ち時間'] = pd.to_numeric(df['待ち時間'], errors='coerce').fillna(0)
    df['取得時刻'] = pd.to_datetime(df['取得時刻'], errors='coerce')
    df['時刻'] = df['取得時刻'].dt.time
    df['表示名'] = df['名称'] + "（" + df['エリア'] + "）"
    return df

df = load_data()

# === 傾向分類 ===
def judge_recent_decrease(group):
    one_hour_ago = group['取得時刻'].max() - pd.Timedelta(hours=1)
    recent = group[group['取得時刻'] >= one_hour_ago].sort_values('取得時刻')
    return "減少" if len(recent) >= 2 and recent['待ち時間'].iloc[-1] < recent['待ち時間'].iloc[0] else "その他"

df['傾向'] = df.groupby('表示名').apply(judge_recent_decrease).reindex(df['表示名']).values

# === UI ===
st.title("🎢 アトラクション待ち時間ビューア（Google Drive連携）")

col1, col2, col3 = st.columns(3)
selected_date = col1.date_input("📅 日付選択", value=datetime.date.today())
trend_filter = col2.selectbox("📉 傾向で絞り込み", ["全て", "減少"])
name_options = ["全て"] + sorted(df['名称'].unique())
selected_name = col3.selectbox("🎠 アトラクション", name_options)

# === データフィルタリング ===
filtered = df[df['取得時刻'].dt.date == selected_date]
if trend_filter != "全て":
    filtered = filtered[filtered['傾向'] == trend_filter]
if selected_name != "全て":
    filtered = filtered[filtered['名称'] == selected_name]

if filtered.empty:
    st.warning("⚠️ 該当データがありません。")
else:
    st.dataframe(filtered[['名称', '時刻', '待ち時間', '営業時間', '運営状況', '補足情報', '更新時刻']])

    fig, ax = plt.subplots(figsize=(10, 4))
    for name, group in filtered.groupby('表示名'):
        group_sorted = group.sort_values('取得時刻')
        ax.plot(group_sorted['取得時刻'], group_sorted['待ち時間'], marker='o', label=name)

    ax.set_title("待ち時間推移")
    ax.set_xlabel("取得時刻")
    ax.set_ylabel("待ち時間（分）")
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    ax.grid(True, linestyle='--', alpha=0.5)
    ax.legend()
    st.pyplot(fig)


# In[ ]:




