import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta, date
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import io
import numpy as np

# secrets.toml から読み込み
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}"
}

# 今日の日付
today_str = datetime.now().strftime("%Y-%m-%d")

@st.cache_data(ttl=300)
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
        drop_rate = ((start_value - end_value) / start_value) * 100 if start_value != 0 else 0
    else:
        drop_rate = None

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(expanded_df["fetched_at"], expanded_df["standbytime"], linestyle="-")
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    ax.set_xlim(start_time, end_time)
    ax.set_xlabel("time")
    ax.set_ylabel("wait time")
    max_val = int(expanded_df["standbytime"].max())
    step = max(5, round(max_val / 10 / 5) * 5)
    ax.set_yticks(np.arange(0, max_val + step, step))
    ax.grid(True)
    plt.xticks(rotation=45)
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    buf.seek(0)
    return buf, drop_rate

@st.cache_data(ttl=300)
def fetch_latest_data(table_name):
    url = f"{SUPABASE_URL}/rest/v1/{table_name}"
    params = {
        "fetched_at": f"gte.{today_str}",
        "select": "*"
    }
    response = requests.get(url, headers=HEADERS, params=params)
    if response.status_code != 200:
        st.error(f"データ取得に失敗しました: {response.status_code}")
        return pd.DataFrame()
    data = response.json()
    df = pd.DataFrame(data)

    if df.empty:
        return pd.DataFrame()

    df["fetched_at"] = pd.to_datetime(df["fetched_at"])
    df = df.sort_values("fetched_at").dropna(subset=["facilityid"])
    df_latest = df.groupby("facilityid", as_index=False).last()
    return df_latest

@st.cache_data(ttl=300)
def fetch_shortname():
    res = requests.get(f"{SUPABASE_URL}/rest/v1/attraction_short_name", headers=HEADERS)
    return pd.DataFrame(res.json())

def merge_with_shortname(df, shortname_df):
    return pd.merge(df, shortname_df, on="facilityid", how="left")

@st.cache_data(ttl=300)
def get_facility_log(table_name, facility_id):
    url = f"{SUPABASE_URL}/rest/v1/{table_name}"
    params = {
        "facilityid": f"eq.{facility_id}",
        "fetched_at": f"gte.{str(date.today())}",
        "select": "fetched_at,standbytime"
    }
    response = requests.get(url, headers=HEADERS, params=params)
    return response.json() if response.status_code == 200 else []

def display_tab(df, title, key_prefix):
    st.write(f"### {'\U0001F3A2' if 'TDS' in title else '\U0001F3F0'} {title}待ち時間")

    sort_order = st.radio(
        "並び順を選択:",
        ("待順(長)", "待順(短)", "高減少率"),
        horizontal=True,
        key=f"{key_prefix}_sort_order"
    )

    df = df.dropna(subset=["shortname", "standbytime"])

    if sort_order == "高減少率":
        drop_rate_list = []
        for _, row in df.iterrows():
            raw_log = get_facility_log("tds_attraction_log" if "TDS" in title else "tdl_attraction_log", row["facilityid"])
            _, drop_rate = generate_wait_time_graph(raw_log, today_str) if raw_log else (None, 0.0)
            drop_rate_list.append(drop_rate if drop_rate is not None else 0.0)
        df = df.assign(drop_rate=drop_rate_list)
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

        # ログ取得
        raw_log = get_facility_log("tds_attraction_log" if "TDS" in title else "tdl_attraction_log", facility_id)
        drop_rate = None
        if raw_log:
            _, drop_rate = generate_wait_time_graph(raw_log, today_str)

        # アコーディオンタイトルに減少率表示
        drop_rate_display = f"（{drop_rate:.1f}%減少）" if drop_rate is not None else ""
        title_text = f"{wait}分：{name}{drop_rate_display}"

        with st.expander(title_text, expanded=False) as exp:
            st.markdown(f"""
                <small><b>施設名:</b> {row.get('facilitykananame', 'N/A')}<br>
                <b>運営状況:</b> {row.get('operatingstatus', 'N/A')} /
                <b>時間:</b> {row.get('operatinghoursfrom', 'N/A')} - {row.get('operatinghoursto', 'N/A')}<br>
                <b>更新:</b> {row.get('updatetime', fetched_time)}</small>
            """, unsafe_allow_html=True)

            # 発券状況の取得と表示
            status_url = f"{SUPABASE_URL}/rest/v1/" + ("tds_attraction_log" if "TDS" in title else "tdl_attraction_log")
            status_params = {
                "facilityid": f"eq.{facility_id}",
                "select": "dpastatuscd,ppstatuscd",
                "order": "fetched_at.desc",
                "limit": 1
            }
            status_res = requests.get(status_url, headers=HEADERS, params=status_params)
            status_row = status_res.json() if status_res.status_code == 200 else []

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

            if raw_log:
                buf, _ = generate_wait_time_graph(raw_log, today_str)
                st.image(buf)
            else:
                st.info("グラフ表示用のデータがありません。")

@st.cache_data(ttl=300)
def fetch_latest_status_log(table_name):
    url = f"{SUPABASE_URL}/rest/v1/{table_name}"
    params = {
        "select": "facilityid,dpastatuscd,ppstatuscd,operatingstatuscd,fetched_at",
        "order": "facilityid,fetched_at.desc",
    }
    res = requests.get(url, headers=HEADERS, params=params)
    if res.status_code != 200:
        return pd.DataFrame()
    df = pd.DataFrame(res.json())
    if df.empty:
        return pd.DataFrame()
    return df.sort_values("fetched_at").drop_duplicates(subset="facilityid", keep="last")

# データ準備
df_tds = fetch_latest_data("tds_attraction_log")
df_tdl = fetch_latest_data("tdl_attraction_log")
shortname_df = fetch_shortname()
df_tds = merge_with_shortname(df_tds, shortname_df)
df_tdl = merge_with_shortname(df_tdl, shortname_df)

# UI
st.set_page_config(page_title="待ち時間グラフ", layout="centered")
tab1, tab2, tab3 = st.tabs(["\U0001F3A2 TDS", "\U0001F3F0 TDL", "🎫 パス"])

with tab1:
    display_tab(df_tds, "TDS", key_prefix="tds")

with tab2:
    display_tab(df_tdl, "TDL", key_prefix="tdl")

with tab3:
    df_status_tds = fetch_latest_status_log("tds_attraction_log")
    df_status_tdl = fetch_latest_status_log("tdl_attraction_log")
    df_status_all = pd.concat([df_status_tds, df_status_tdl], ignore_index=True)

    df_all = pd.concat([df_tds.assign(park="TDS"), df_tdl.assign(park="TDL")], ignore_index=True)
    df_merged = pd.merge(df_all, df_status_all, on="facilityid", how="left")

    # 型が異なると比較できないので文字列化
    df_merged["dpastatuscd"] = df_merged["dpastatuscd"].astype(str)
    df_merged["ppstatuscd"] = df_merged["ppstatuscd"].astype(str)
    df_merged["operatingstatuscd"] = df_merged["operatingstatuscd"].astype(str)

    dpa_list = df_merged[df_merged["dpastatuscd"] == "1"]["facilitykananame"].dropna().unique().tolist()
    pp_list = df_merged[df_merged["ppstatuscd"] == "1"]["facilitykananame"].dropna().unique().tolist()
    linecut_list = df_merged[df_merged["operatingstatuscd"] == "045"]["facilitykananame"].dropna().unique().tolist()

    def render_section(title, items):
        st.markdown(f"### {title}")
        if items:
            for name in sorted(set(items)):
                st.markdown(f"- {name}")
        else:
            st.markdown("なし")

    render_section("DPA", dpa_list)
    render_section("プライオリティパス", pp_list)
    render_section("ラインカット", linecut_list)
