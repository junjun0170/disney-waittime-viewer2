import streamlit as st
from supabase import create_client
import pandas as pd
from datetime import datetime, timedelta, date
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import io

# Supabase接続設定
url = "https://rfrnpofepmlezzqijlzt.supabase.co"
key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJmcm5wb2ZlcG1sZXp6cWlqbHp0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDc2NjMwMTgsImV4cCI6MjA2MzIzOTAxOH0.3iJiZj61kYDMlIcJvz-VBV0JiAlLw9R7mAYutjYFoEA"
supabase = create_client(url, key)

# 今日の日付
today_str = datetime.now().strftime("%Y-%m-%d")

# グラフ生成関数 + 直近1時間の減少率を返す
def generate_wait_time_graph(raw_data, date_str):
    df = pd.DataFrame(raw_data)
    df["fetched_at"] = pd.to_datetime(df["fetched_at"])
    df = df.sort_values("fetched_at")

    expanded_rows = []
    for i in range(len(df) - 1):
        current_row = df.iloc[i]
        next_row = df.iloc[i + 1]
        expanded_rows.append(current_row.to_dict())

        diff = (next_row["fetched_at"] - current_row["fetched_at"]).total_seconds() / 60
        if diff > 10:
            for j in range(1, int(diff // 5)):
                expanded_rows.append({
                    "fetched_at": current_row["fetched_at"] + timedelta(minutes=5 * j),
                    "standbytime": current_row["standbytime"]
                })

    expanded_rows.append(df.iloc[-1].to_dict())
    expanded_df = pd.DataFrame(expanded_rows)

    start_time = datetime.strptime(f"{date_str} 08:30", "%Y-%m-%d %H:%M")
    end_time = datetime.strptime(f"{date_str} 21:30", "%Y-%m-%d %H:%M")
    expanded_df = expanded_df[(expanded_df["fetched_at"] >= start_time) & (expanded_df["fetched_at"] <= end_time)]

    now = expanded_df["fetched_at"].max()
    one_hour_ago = now - timedelta(hours=1)
    df_last_hour = expanded_df[(expanded_df["fetched_at"] >= one_hour_ago) & (expanded_df["fetched_at"] <= now)]

    if not df_last_hour.empty:
        start_value = df_last_hour.iloc[0]["standbytime"]
        end_value = df_last_hour.iloc[-1]["standbytime"]
        if start_value != 0:
            drop_rate = ((start_value - end_value) / start_value) * 100
        else:
            drop_rate = 0
    else:
        drop_rate = None

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(expanded_df["fetched_at"], expanded_df["standbytime"], linestyle="-")
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    ax.set_xlim(start_time, end_time)
    ax.set_xlabel("time")
    ax.set_ylabel("wait time")
    import numpy as np
    max_val = int(expanded_df["standbytime"].max())
    step = max(5, round(max_val / 10 / 5) * 5)  # 最低5分刻み、最大値に応じて調整
    ax.set_yticks(np.arange(0, max_val + step, step))
    ax.grid(True)
    plt.xticks(rotation=45)
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    buf.seek(0)
    return buf, drop_rate

# データ取得関数
def fetch_latest_data(table_name):
    response = supabase.table(table_name).select("*").gte("fetched_at", today_str).execute()
    df = pd.DataFrame(response.data)

    if df.empty:
        return pd.DataFrame()

    df["fetched_at"] = pd.to_datetime(df["fetched_at"])
    df = df.sort_values("fetched_at").dropna(subset=["facilityid"])
    df_latest = df.groupby("facilityid", as_index=False).last()
    return df_latest

# attraction_short_nameの取得
shortname_df = pd.DataFrame(
    supabase.table("attraction_short_name").select("*").execute().data
)

# TDS / TDL ログ取得
df_tds = fetch_latest_data("tds_attraction_log")
df_tdl = fetch_latest_data("tdl_attraction_log")

def merge_with_shortname(df):
    return pd.merge(df, shortname_df, on="facilityid", how="left")

df_tds = merge_with_shortname(df_tds)
df_tdl = merge_with_shortname(df_tdl)

# 表示用関数
def display_tab(df, title, key_prefix):
    if "TDS" in title:
        st.write(f"### \U0001F3A2 {title}待ち時間")
    else:
        st.write(f"### \U0001F3F0 {title}待ち時間")

    with st.container():
        st.markdown("<style>.stRadio > div{font-size:8px;}</style>", unsafe_allow_html=True)
        sort_order = st.radio(
            "並び順を選択:",
            ("待ち(長い順)", "待ち(短い順)", "高減少率"),
            horizontal=True,
            key=f"{key_prefix}_sort_order"
        )

    df = df.dropna(subset=["shortname", "standbytime"])

    if sort_order == "高減少率":
        df = df.copy()
        df["drop_rate"] = 0.0
        for i, row in df.iterrows():
            raw_log = supabase.table("tds_attraction_log" if "TDS" in title else "tdl_attraction_log") \
                .select("fetched_at, standbytime") \
                .eq("facilityid", row["facilityid"]) \
                .gte("fetched_at", str(date.today())) \
                .execute().data
            if raw_log:
                _, drop_rate = generate_wait_time_graph(raw_log, str(date.today()))
                if drop_rate is not None:
                    df.at[i, "drop_rate"] = drop_rate
        df_sorted = df.sort_values("drop_rate", ascending=False)
    elif sort_order == "待ち(短い順)":
        df_sorted = df.sort_values("standbytime")
    else:
        df_sorted = df.sort_values("standbytime", ascending=False)

    for _, row in df_sorted.iterrows():
        name = row['shortname']
        wait = int(row['standbytime'])
        facility_id = row['facilityid']
        fetched_time = row['fetched_at'].strftime('%H:%M:%S')

        log_table = "tds_attraction_log" if "TDS" in title else "tdl_attraction_log"
        raw_log = supabase.table(log_table) \
            .select("fetched_at, standbytime") \
            .eq("facilityid", facility_id) \
            .gte("fetched_at", str(date.today())) \
            .execute().data

        drop_rate_display = ""
        if raw_log:
            buf, drop_rate = generate_wait_time_graph(raw_log, str(date.today()))
            if drop_rate is not None:
                drop_rate_display = f" (減少率: {drop_rate:.1f}%)"
        else:
            buf = None

        title_text = f"{wait}分：{name}{drop_rate_display}"
        with st.expander(title_text, expanded=False):
            st.markdown(f"<small>**施設名**: {row.get('facilitykananame', 'N/A')}</small>", unsafe_allow_html=True)
            st.markdown(f"<small>**運営状況**: {row.get('operatingstatus', 'N/A')} / **運営時間**: {row.get('operatinghoursfrom', 'N/A')} - {row.get('operatinghoursto', 'N/A')}</small>", unsafe_allow_html=True)
            st.markdown(f"<small>**更新時間**: {row.get('updatetime', fetched_time)}</small>", unsafe_allow_html=True)

            status_row = supabase.table(log_table) \
                .select("dpastatuscd, ppstatuscd") \
                .eq("facilityid", facility_id) \
                .order("fetched_at", desc=True) \
                .limit(1).execute().data

            if status_row:
                status = status_row[0]
                dpa = status.get("dpastatuscd")
                pp = status.get("ppstatuscd")

                if dpa is not None:
                    dpa = str(dpa)
                    if dpa == "1":
                        st.markdown('<small><span style="color:red">**発券状況**: DPA販売中</span></small>', unsafe_allow_html=True)
                    elif dpa == "2":
                        st.markdown('<small><span style="color:gray">**発券状況**: DPA販売終了</span></small>', unsafe_allow_html=True)
                elif pp is not None:
                    pp = str(pp)
                    if pp == "1":
                        st.markdown('<small><span style="color:red">**発券状況**: プライオリティパス発券中</span></small>', unsafe_allow_html=True)
                    elif pp == "2":
                        st.markdown('<small><span style="color:gray">**発券状況**: プライオリティパス発券終了</span></small>', unsafe_allow_html=True)

            if buf:
                st.image(buf)
            else:
                st.info("グラフ表示用のデータがありません。")

# Streamlit UI設定
st.set_page_config(page_title="待ち時間グラフ", layout="centered")
tab1, tab2 = st.tabs(["\U0001F3A2 TDS", "\U0001F3F0 TDL"])

with tab1:
    display_tab(df_tds, "TDS", key_prefix="tds")

with tab2:
    display_tab(df_tdl, "TDL", key_prefix="tdl")
    