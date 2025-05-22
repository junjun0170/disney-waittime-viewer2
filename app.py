import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta, date
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import io

# --- Secrets 読み込み ---
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}"
}

today_str = datetime.now().strftime("%Y-%m-%d")

# --- 最新データ取得（TDS / TDL） ---
@st.cache_data(ttl=300)
def fetch_latest_data(table_name):
    url = f"{SUPABASE_URL}/rest/v1/{table_name}"
    params = {
        "fetched_at": f"gte.{today_str}",
        "select": "*"
    }
    res = requests.get(url, headers=HEADERS, params=params)
    if res.status_code != 200:
        return pd.DataFrame()
    df = pd.DataFrame(res.json())
    if df.empty:
        return pd.DataFrame()
    df["fetched_at"] = pd.to_datetime(df["fetched_at"], errors="coerce")
    df = df.dropna(subset=["facilityid"])
    return df.sort_values("fetched_at").groupby("facilityid", as_index=False).last()

# --- 略称データ取得 ---
@st.cache_data(ttl=300)
def fetch_shortname():
    url = f"{SUPABASE_URL}/rest/v1/attraction_short_name"
    res = requests.get(url, headers=HEADERS)
    return pd.DataFrame(res.json()) if res.status_code == 200 else pd.DataFrame()

# --- 結合処理 ---
def merge_with_shortname(df, shortname_df):
    return pd.merge(df, shortname_df, on="facilityid", how="left")

# --- ログ全体取得 ---
@st.cache_data(ttl=300)
def fetch_full_log_df(table_name):
    url = f"{SUPABASE_URL}/rest/v1/{table_name}"
    params = {
        "fetched_at": f"gte.{today_str}",
        "select": "facilityid,fetched_at,standbytime"
    }
    res = requests.get(url, headers=HEADERS, params=params)
    if res.status_code != 200:
        return pd.DataFrame()
    df = pd.DataFrame(res.json())
    df["fetched_at"] = pd.to_datetime(df["fetched_at"], errors="coerce")
    return df

# --- 最新ステータス取得 ---
@st.cache_data(ttl=300)
def fetch_latest_status(table_name):
    url = f"{SUPABASE_URL}/rest/v1/{table_name}"
    params = {
        "select": "facilityid,dpastatuscd,ppstatuscd,fetched_at",
        "order": "facilityid,fetched_at.desc"
    }
    res = requests.get(url, headers=HEADERS, params=params)
    if res.status_code != 200:
        return pd.DataFrame()
    df = pd.DataFrame(res.json())
    df["fetched_at"] = pd.to_datetime(df["fetched_at"], errors="coerce")
    df = df.sort_values("fetched_at").drop_duplicates("facilityid", keep="last")
    return df

# --- 減少率計算 ---
@st.cache_data(ttl=300)
def calculate_drop_rates(log_df):
    drop_rate_map = {}
    grouped = log_df.groupby("facilityid")
    for facilityid, group in grouped:
        group = group.sort_values("fetched_at")
        now = group["fetched_at"].max()
        one_hour_ago = now - timedelta(hours=1)
        df_hour = group[(group["fetched_at"] >= one_hour_ago) & (group["fetched_at"] <= now)]
        if df_hour.empty:
            drop_rate_map[facilityid] = 0.0
            continue
        start, end = df_hour.iloc[0]["standbytime"], df_hour.iloc[-1]["standbytime"]
        drop = ((start - end) / start) * 100 if start else 0
        drop_rate_map[facilityid] = round(drop, 1)
    return drop_rate_map

# --- グラフ描画（補完ルール含む） ---
def draw_wait_time_chart(log_df, facility_id):
    df = log_df[log_df["facilityid"] == facility_id].copy()
    if df.empty:
        st.info("グラフ表示用のデータがありません。")
        return
    df = df.sort_values("fetched_at")

    # 補間処理（5分単位で線形補完）
    df = df.set_index("fetched_at").resample("5min").ffill().reset_index()

    start_time = datetime.combine(date.today(), datetime.strptime("08:30", "%H:%M").time())
    end_time = datetime.combine(date.today(), datetime.strptime("21:30", "%H:%M").time())
    df = df[(df["fetched_at"] >= start_time) & (df["fetched_at"] <= end_time)]

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(df["fetched_at"], df["standbytime"], linestyle="-")
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    ax.set_xlim(start_time, end_time)
    ax.set_xlabel("時刻")
    ax.set_ylabel("待ち時間（分）")
    max_val = int(df["standbytime"].max()) if not df.empty else 60
    step = max(5, round(max_val / 10 / 5) * 5)
    ax.set_yticks(np.arange(0, max_val + step, step))
    ax.grid(True)
    plt.xticks(rotation=45)
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    buf.seek(0)
    st.image(buf)

# --- タブUI表示 ---
def display_tab(df, log_df, drop_rates, title):
    st.write(f"### {'\U0001F3A2' if 'TDS' in title else '\U0001F3F0'} {title}待ち時間")

    df = df.dropna(subset=["shortname", "standbytime"])
    sort_order = st.radio("並び順を選択:", ("待順(長)", "待順(短)", "高減少率"), horizontal=True, key=title)

    if sort_order == "高減少率":
        df["drop_rate"] = df["facilityid"].map(drop_rates)
        df = df.sort_values("drop_rate", ascending=False)
    elif sort_order == "待順(短)":
        df = df.sort_values("standbytime")
    else:
        df = df.sort_values("standbytime", ascending=False)

    for _, row in df.iterrows():
        facility_id = row["facilityid"]
        drop = drop_rates.get(facility_id, 0.0)
        fetched_at = row.get("fetched_at")
        fetched_str = fetched_at.strftime('%H:%M:%S') if pd.notnull(fetched_at) else "N/A"
        title_text = f"{int(row['standbytime'])}分：{row['shortname']}（{drop:.1f}%減少）"
        with st.expander(title_text):
            st.markdown(f"""
                <small><b>施設名:</b> {row.get('facilitykananame', 'N/A')}<br>
                <b>運営状況:</b> {row.get('operatingstatus', 'N/A')}<br>
                <b>更新:</b> {fetched_str}</small>
            """, unsafe_allow_html=True)

            # 発券状況表示
            dpa = str(row.get("dpastatuscd", ""))
            pp = str(row.get("ppstatuscd", ""))
            if dpa == "1":
                st.markdown('<small><span style="color:red">**発券状況**: DPA販売中</span></small>', unsafe_allow_html=True)
            elif dpa == "2":
                st.markdown('<small><span style="color:gray">**発券状況**: DPA販売終了</span></small>', unsafe_allow_html=True)
            if pp == "1":
                st.markdown('<small><span style="color:red">**発券状況**: PP発券中</span></small>', unsafe_allow_html=True)
            elif pp == "2":
                st.markdown('<small><span style="color:gray">**発券状況**: PP発券終了</span></small>', unsafe_allow_html=True)

            draw_wait_time_chart(log_df, facility_id)

# --- データ取得 ---
df_tds = fetch_latest_data("tds_attraction_log")
df_tdl = fetch_latest_data("tdl_attraction_log")
shortname_df = fetch_shortname()

status_tds = fetch_latest_status("tds_attraction_log")
status_tdl = fetch_latest_status("tdl_attraction_log")

# 結合
df_tds = merge_with_shortname(df_tds, shortname_df)
df_tdl = merge_with_shortname(df_tdl, shortname_df)
df_tds = pd.merge(df_tds, status_tds, on="facilityid", how="left")
df_tdl = pd.merge(df_tdl, status_tdl, on="facilityid", how="left")

# 数値変換
df_tds["standbytime"] = pd.to_numeric(df_tds["standbytime"], errors="coerce")
df_tdl["standbytime"] = pd.to_numeric(df_tdl["standbytime"], errors="coerce")

# ログ全取得 + 減少率事前計算
log_tds = fetch_full_log_df("tds_attraction_log")
log_tdl = fetch_full_log_df("tdl_attraction_log")
drop_tds = calculate_drop_rates(log_tds)
drop_tdl = calculate_drop_rates(log_tdl)

# UI表示
st.set_page_config(page_title="待ち時間グラフ", layout="centered")
tab1, tab2 = st.tabs(["🎢 TDS", "🏰 TDL"])

with tab1:
    display_tab(df_tds, log_tds, drop_tds, "TDS")

with tab2:
    display_tab(df_tdl, log_tdl, drop_tdl, "TDL")
