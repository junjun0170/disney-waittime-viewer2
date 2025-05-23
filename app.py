# disney_waittime_app.py

import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import io

# --- 設定とヘッダー ---
st.set_page_config(page_title="待ち時間グラフ", layout="centered")

from streamlit_autorefresh import st_autorefresh

# 自動更新（5分）トグル
if st.toggle("🔁 自動更新（5分ごと）", key="autorefresh_toggle"):
    st_autorefresh(interval=300_000, key="auto_refresh")

# --- Supabase設定 ---
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}"
}
today_str = datetime.now().strftime("%Y-%m-%d")

# --- データ取得 ---
@st.cache_data(ttl=300)
def fetch_attraction_logs(table_name):
    url = f"{SUPABASE_URL}/rest/v1/{table_name}"
    columns = ["facilityid", "fetched_at", "standbytime", "facilitykananame",
               "operatingstatus", "operatinghoursfrom", "operatinghoursto",
               "updatetime", "dpastatuscd", "ppstatuscd", "operatingstatuscd"]
    params = {"fetched_at": f"gte.{today_str}", "select": ",".join(columns)}
    res = requests.get(url, headers=HEADERS, params=params)
    df = pd.DataFrame(res.json()) if res.status_code == 200 else pd.DataFrame()
    if not df.empty:
        df["fetched_at"] = pd.to_datetime(df["fetched_at"])
        df["standbytime"] = pd.to_numeric(df["standbytime"], errors="coerce")
    return df

@st.cache_data(ttl=86400)
def fetch_shortname_table():
    url = f"{SUPABASE_URL}/rest/v1/attraction_short_name"
    params = {"select": "facilityid,shortname"}
    res = requests.get(url, headers=HEADERS, params=params)
    return pd.DataFrame(res.json()) if res.status_code == 200 else pd.DataFrame()

# --- データ整形 ---
@st.cache_data(ttl=300)
def preprocess_logs(df_log, shortname_df, park_name):
    df_latest = df_log.sort_values("fetched_at").groupby("facilityid", as_index=False).last()
    df_latest = pd.merge(df_latest, shortname_df, on="facilityid", how="left")
    drop_rates = []
    for fid in df_latest["facilityid"]:
        df_fac = df_log[df_log["facilityid"] == fid].sort_values("fetched_at")
        now = df_fac["fetched_at"].max()
        one_hour_ago = now - timedelta(hours=1)
        df_hour = df_fac[(df_fac["fetched_at"] >= one_hour_ago) & (df_fac["fetched_at"] <= now)]
        if df_hour.empty or len(df_hour) < 2:
            drop_rates.append(None)
        else:
            start = df_hour.iloc[0]["standbytime"]
            end = df_hour.iloc[-1]["standbytime"]
            rate = ((start - end) / start) * 100 if start else None
            drop_rates.append(rate)
    df_latest["drop_rate"] = drop_rates
    df_latest["park"] = park_name
    df_latest["standbytime"] = pd.to_numeric(df_latest["standbytime"], errors="coerce").astype("Int64")
    return df_latest

# --- グラフ補間 ---
@st.cache_data(ttl=300)
def generate_expanded_log(df_log, facility_id, date_str):
    df = df_log[df_log["facilityid"] == facility_id].sort_values("fetched_at")
    if df.empty: return pd.DataFrame()
    expanded_rows = []
    for i in range(len(df) - 1):
        current_row, next_row = df.iloc[i], df.iloc[i + 1]
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
    return expanded_df[(expanded_df["fetched_at"] >= start_time) & (expanded_df["fetched_at"] <= end_time)]

# --- グラフ描画 ---
def draw_wait_time_chart(expanded_df):
    if expanded_df.empty: return None, None
    now = expanded_df["fetched_at"].max()
    one_hour_ago = now - timedelta(hours=1)
    df_hour = expanded_df[(expanded_df["fetched_at"] >= one_hour_ago) & (expanded_df["fetched_at"] <= now)]
    drop_rate = None
    if not df_hour.empty and len(df_hour) >= 2:
        start, end = df_hour.iloc[0]["standbytime"], df_hour.iloc[-1]["standbytime"]
        drop_rate = ((start - end) / start) * 100 if start else None
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(expanded_df["fetched_at"], expanded_df["standbytime"], linestyle="-")
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    ax.set_xlim(expanded_df["fetched_at"].min(), expanded_df["fetched_at"].max())
    ax.set_xlabel("時間")
    ax.set_ylabel("待ち時間（分）")
    max_val = int(expanded_df["standbytime"].max())
    step = max(5, round(max_val / 10 / 5) * 5)
    ax.set_yticks(np.arange(0, max_val + step, step))
    ax.grid(True)
    plt.xticks(rotation=45)
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    buf.seek(0)
    plt.close(fig)
    return buf, drop_rate

# --- TDS/TDL 表示 ---
def display_tab(df_processed, df_log, park_label, today_str):
    st.write(f"### {'🎢' if park_label == 'TDS' else '🏰'} {park_label} 待ち時間")
    sort_order = st.radio("並び順を選択：", ("待順(長)", "待順(短)", "高減少率"), horizontal=True, key=f"{park_label}_sort_order")
    df = df_processed.dropna(subset=["shortname", "standbytime"])
    df_sorted = df.sort_values("drop_rate", ascending=False) if sort_order == "高減少率" \
        else df.sort_values("standbytime", ascending=(sort_order == "待順(短)"))
    for _, row in df_sorted.iterrows():
        name, wait, fid = row["shortname"], row["standbytime"], row["facilityid"]
        drop = row.get("drop_rate")
        updated = row["fetched_at"].strftime('%H:%M')
        drop_txt = f"（{drop:.1f}%減少）" if drop is not None else ""
        with st.expander(f"{wait}分：{name}{drop_txt}", expanded=False):
            st.markdown(f"""
                <small><b>施設名:</b> {row.get('facilitykananame', 'N/A')}<br>
                <b>運営状況:</b> {row.get('operatingstatus', 'N/A')} / 
                <b>営業時間:</b> {row.get('operatinghoursfrom', 'N/A')} - {row.get('operatinghoursto', 'N/A')}<br>
                <b>更新:</b> {row.get('updatetime', updated)}</small>
            """, unsafe_allow_html=True)
            for label, code, msg_on, msg_off in [("dpastatuscd", "1", "DPA販売中", "DPA販売終了"), ("ppstatuscd", "1", "プライオリティパス発券中", "プライオリティパス発券終了")]:
                status = str(row.get(label, ""))
                if status == "1":
                    st.markdown(f'<small><span style="color:red">**発券状況**: {msg_on}</span></small>', unsafe_allow_html=True)
                elif status == "2":
                    st.markdown(f'<small><span style="color:gray">**発券状況**: {msg_off}</span></small>', unsafe_allow_html=True)
            if st.toggle("グラフを表示", key=f"{fid}_toggle"):
                expanded_df = generate_expanded_log(df_log, fid, today_str)
                buf, _ = draw_wait_time_chart(expanded_df)
                if buf: st.image(buf)
                else: st.info("グラフデータがありません。")
                  
# --- 発券状況まとめ ---
def display_pass_summary(df_tds, df_tdl):
    df_all = pd.concat([df_tds, df_tdl], ignore_index=True)
    dpa_list = df_all[df_all["dpastatuscd"] == "1"][["park", "facilitykananame"]].dropna().drop_duplicates()
    pp_list = df_all[df_all["ppstatuscd"] == "1"][["park", "facilitykananame"]].dropna().drop_duplicates()
    linecut_list = df_all[df_all["operatingstatuscd"] == "045"][["park", "facilitykananame"]].dropna().drop_duplicates()

    def render_section(title, df_section):
        st.markdown(f"### {title}")
        if df_section.empty:
            st.markdown("なし")
        else:
            for _, row in df_section.sort_values(["park", "facilitykananame"]).iterrows():
                st.markdown(f"- ({row['park']}) {row['facilitykananame']}")

    render_section("🎫 DPA販売中", dpa_list)
    render_section("🎫 プライオリティパス発券中", pp_list)
    render_section("🚫 ラインカット中", linecut_list)

# --- 注目施設表示 ---
def display_alert_tab(df_all):
    alert_df = df_all[(df_all["standbytime"] <= 40) & (df_all["drop_rate"].fillna(0) >= 30)].copy()
    st.markdown("### 🔔 今が狙い目の施設（条件: 待ち時間 ≤ 40分 & 減少率 ≥ 30%）")
    if alert_df.empty:
        st.info("現在、条件に合致する施設はありません。")
    else:
        for _, row in alert_df.sort_values("drop_rate", ascending=False).iterrows():
            st.markdown(f"- ({row['park']}) {row['shortname']}：{row['standbytime']}分（{row['drop_rate']:.1f}%減少）")

# --- 一覧表示 ---
def display_facility_table(df_all):
    df_view = df_all.copy()
    df_view = df_view[["park", "shortname", "standbytime", "drop_rate", "dpastatuscd", "ppstatuscd", "operatingstatus", "updatetime"]].rename(columns={
        "park": "パーク", "shortname": "アトラクション名", "standbytime": "待ち時間（分）", "drop_rate": "減少率（%）",
        "dpastatuscd": "DPA", "ppstatuscd": "PP", "operatingstatus": "運営状況", "updatetime": "更新"
    })
    df_view["DPA"] = df_view["DPA"].replace({"1": "販売中", "2": "終了"})
    df_view["PP"] = df_view["PP"].replace({"1": "発券中", "2": "終了"})
    st.markdown("### 📋 全施設一覧（並び替え・検索可能）")
    st.dataframe(df_view, use_container_width=True)

# --- UI構成 ---
df_log_tds = fetch_attraction_logs("tds_attraction_log")
df_log_tdl = fetch_attraction_logs("tdl_attraction_log")
df_shortname = fetch_shortname_table()
df_processed_tds = preprocess_logs(df_log_tds, df_shortname, "TDS")
df_processed_tdl = preprocess_logs(df_log_tdl, df_shortname, "TDL")

tab1, tab2, tab3, tab4, tab5 = st.tabs(["🎢 TDS", "🏰 TDL", "🎫 パス状況", "🔔 注目施設", "📋 一覧表示"])

with tab1:
    display_tab(df_processed_tds, df_log_tds, "TDS", today_str)

with tab2:
    display_tab(df_processed_tdl, df_log_tdl, "TDL", today_str)

with tab3:
    display_pass_summary(df_processed_tds, df_processed_tdl)

with tab4:
    df_alert_source = pd.concat([df_processed_tds, df_processed_tdl], ignore_index=True)
    display_alert_tab(df_alert_source)

with tab5:
    df_all = pd.concat([df_processed_tds, df_processed_tdl], ignore_index=True)
    display_facility_table(df_all)
