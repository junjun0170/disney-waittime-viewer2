import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib
import datetime
import re
from urllib.parse import quote
import requests
from io import BytesIO
import pandas as pd


# --- ページ設定 ---
st.set_page_config(page_title="待ち時間グラフ", layout="centered")


# --- タブ構成 ---
tab1, tab2 = st.tabs(["🎢 TDS", "🏰 TDL"])

with tab1:
    # TOPリンク（現在のパスのみ取得）
    st.markdown(
        "<a href='/' target='_self' style='font-size:10px; font-weight:bold;'>TOP</a>",
        unsafe_allow_html=True
    )


    # Google DriveのファイルID
    file_id = "1pA6vXgJuOr5lNgIEHLVvLUj1sZufHgbN"  # あなたの log.xlsx のIDに置き換えてください
    download_url = f"https://drive.google.com/uc?export=download&id={file_id}"

    # ファイルをバイナリとして取得
    response = requests.get(download_url)
    response.raise_for_status()
    excel_data = BytesIO(response.content)

    # Excelを読み込み（例: シート名が 'log_tds_att' の場合）
    df = pd.read_excel(excel_data, sheet_name="log_tds_att", engine="openpyxl")

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
    query = st.query_params
    query = st.query_params
    preselected = query.get("selected", "---")

    # クエリに変化があったら再実行して画面を更新
    if "selected" in query and st.session_state.get("last_selected") != query["selected"]:
        st.session_state["last_selected"] = query["selected"]
        st.rerun()

    # --- アコーディオン表示準備 ---
    day_df = df.copy()
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
    name_day = df.copy()
    avg_map = name_day.groupby('名称')['待ち時間'].mean().sort_values(ascending=False)
    name_options = ["---"] + avg_map.index.tolist()
    name_filter = st.selectbox("アトラクション", name_options, index=name_options.index(preselected) if preselected in name_options else 0)

    # --- フィルタ ---
    if name_filter != "---":
        filtered = df[df['名称'] == name_filter]
    else:
        filtered = pd.DataFrame()

    # --- グラフ＆表の表示 ---
    if not filtered.empty:
        st.write("### 📈 待ち時間グラフ")
        fig, ax = plt.subplots(figsize=(6, 3))
        
        # ← selected_date を使っていた場合は、以下に変更
        base_date = df['取得時刻'].dt.date.min()

        #highlight_periods = [
        #    (datetime.time(8, 45), datetime.time(9, 15), 'red'),
        #    (datetime.time(12, 0), datetime.time(13, 0), 'blue'),
        #    (datetime.time(19, 30), datetime.time(20, 0), 'orange'),
        #]
        #
        #for start_t, end_t, color in highlight_periods:
        #    start_dt = datetime.datetime.combine(base_date, start_t)
        #    end_dt = datetime.datetime.combine(base_date, end_t)
        #    ax.axvspan(start_dt, end_dt, color=color, alpha=0.2)

        
        def extract_time_from_text(text):
            match = re.search(r'(\d{1,2}:\d{2})', str(text))
            return match.group(1) if match else "00:00"

        for title, group in filtered.groupby('表示名'):
            group = group.sort_values('取得時刻').reset_index(drop=True)

            rows = []
            for i in range(len(group) - 1):
                curr_row = group.iloc[i]
                next_row = group.iloc[i + 1]
                rows.append(curr_row)

                # 直後の時間までに5分以上あいていたら補完
                diff = next_row['取得時刻'] - curr_row['取得時刻']
                if diff > pd.Timedelta(minutes=10):
                   補完時刻 = next_row['取得時刻'] - pd.Timedelta(minutes=5)
                   補完行 = curr_row.copy()
                   補完行['取得時刻'] = 補完時刻
                   rows.append(補完行)

            rows.append(group.iloc[-1])  # 最後の行を追加

            # 補完済みのデータフレームに再構築
            group_filled = pd.DataFrame(rows).sort_values('取得時刻').reset_index(drop=True)

            # 平均などの計算
            avg_total = group_filled['待ち時間'].mean()
            recent_group = group_filled[group_filled['取得時刻'] >= group_filled['取得時刻'].max() - pd.Timedelta(hours=1)]
            avg_recent = recent_group['待ち時間'].mean() if not recent_group.empty else 0

            def extract_time_from_text(text):
                match = re.search(r'(\d{1,2}:\d{2})', str(text))
                return match.group(1) if match else "00:00"

            # 最新の1行
            latest_row = group_filled.iloc[-1]
            latest_info = str(latest_row['補足情報'])
            営業時間 = str(latest_row['営業時間'])
            更新時刻 = str(latest_row['更新時刻'])

            # 補足カラー
            color = 'black'
            if '中' in latest_info:
                color = 'red'
            elif '販売なし' in latest_info:
                color = 'gray'

                # 「販売中 → 販売なし」の切り替えを検出して終了時刻を追記
                sorted_info = group_filled[['補足情報', '更新時刻']].astype(str).reset_index(drop=True)
                for i in range(len(sorted_info) - 1):
                    before = sorted_info.loc[i, '補足情報']
                    after = sorted_info.loc[i + 1, '補足情報']
                    if '販売中' in before and '販売なし' in after:
                        match = re.search(r'(\d{1,2}:\d{2})', sorted_info.loc[i + 1, '更新時刻'])
                        if match:
                            latest_info += f"（終了時刻{match.group(1)}）"
                        break



            st.markdown(
                f"<div style='font-size:13px'>{title}<br>営業時間：{営業時間}<br>{更新時刻}<br><br>"
                f"全体平均：{avg_total:.1f}分　/　直近1時間平均：{avg_recent:.1f}分</div><br>"
                f"<span style='color:{color}'><div style='font-size:13px'>補足：{latest_info}</div></span>",
                unsafe_allow_html=True
            )

            # グラフ描画
            ax.plot(group_filled['取得時刻'], group_filled['待ち時間'], label=title)



        legend = ax.legend()
        if legend:
            legend.remove()
        
        # 基準日をデータから取得（任意の1日でOK）
        base_date = df['取得時刻'].dt.date.min()

        # 固定時刻範囲を生成（8:45〜21:00）
        x_start = datetime.datetime.combine(base_date, datetime.time(8, 45))
        x_end = datetime.datetime.combine(base_date, datetime.time(21, 0))
        ax.set_xlim([x_start, x_end])

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

with tab2:
    # TOPリンク（現在のパスのみ取得）
    st.markdown(
        "<a href='/' target='_self' style='font-size:10px; font-weight:bold;'>TOP</a>",
        unsafe_allow_html=True
    )


    # Google DriveのファイルID
    file_id = "1pA6vXgJuOr5lNgIEHLVvLUj1sZufHgbN"  # あなたの log.xlsx のIDに置き換えてください
    download_url = f"https://drive.google.com/uc?export=download&id={file_id}"

    # ファイルをバイナリとして取得
    response = requests.get(download_url)
    response.raise_for_status()
    excel_data = BytesIO(response.content)

    # Excelを読み込み（例: シート名が 'log_tdl_att' の場合）
    df = pd.read_excel(excel_data, sheet_name="log_tdl_att", engine="openpyxl")

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
    query = st.query_params
    query = st.query_params
    preselected = query.get("selected", "---")

    # クエリに変化があったら再実行して画面を更新
    if "selected" in query and st.session_state.get("last_selected") != query["selected"]:
        st.session_state["last_selected"] = query["selected"]
        st.rerun()

    # --- アコーディオン表示準備 ---
    day_df = df.copy()
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
    name_day = df.copy()
    avg_map = name_day.groupby('名称')['待ち時間'].mean().sort_values(ascending=False)
    name_options = ["---"] + avg_map.index.tolist()
    name_filter = st.selectbox("アトラクション", name_options, index=name_options.index(preselected) if preselected in name_options else 0)

    # --- フィルタ ---
    if name_filter != "---":
        filtered = df[df['名称'] == name_filter]
    else:
        filtered = pd.DataFrame()

    # --- グラフ＆表の表示 ---
    if not filtered.empty:
        st.write("### 📈 待ち時間グラフ")
        fig, ax = plt.subplots(figsize=(6, 3))
        
        # ← selected_date を使っていた場合は、以下に変更
        base_date = df['取得時刻'].dt.date.min()

        #highlight_periods = [
        #    (datetime.time(8, 45), datetime.time(9, 15), 'red'),
        #    (datetime.time(12, 0), datetime.time(13, 0), 'blue'),
        #    (datetime.time(19, 30), datetime.time(20, 0), 'orange'),
        #]
        #
        #for start_t, end_t, color in highlight_periods:
        #    start_dt = datetime.datetime.combine(base_date, start_t)
        #    end_dt = datetime.datetime.combine(base_date, end_t)
        #    ax.axvspan(start_dt, end_dt, color=color, alpha=0.2)

        
        def extract_time_from_text(text):
            match = re.search(r'(\d{1,2}:\d{2})', str(text))
            return match.group(1) if match else "00:00"

        for title, group in filtered.groupby('表示名'):
            group = group.sort_values('取得時刻').reset_index(drop=True)

            rows = []
            for i in range(len(group) - 1):
                curr_row = group.iloc[i]
                next_row = group.iloc[i + 1]
                rows.append(curr_row)

                # 直後の時間までに5分以上あいていたら補完
                diff = next_row['取得時刻'] - curr_row['取得時刻']
                if diff > pd.Timedelta(minutes=10):
                   補完時刻 = next_row['取得時刻'] - pd.Timedelta(minutes=5)
                   補完行 = curr_row.copy()
                   補完行['取得時刻'] = 補完時刻
                   rows.append(補完行)

            rows.append(group.iloc[-1])  # 最後の行を追加

            # 補完済みのデータフレームに再構築
            group_filled = pd.DataFrame(rows).sort_values('取得時刻').reset_index(drop=True)

            # 平均などの計算
            avg_total = group_filled['待ち時間'].mean()
            recent_group = group_filled[group_filled['取得時刻'] >= group_filled['取得時刻'].max() - pd.Timedelta(hours=1)]
            avg_recent = recent_group['待ち時間'].mean() if not recent_group.empty else 0

            def extract_time_from_text(text):
                match = re.search(r'(\d{1,2}:\d{2})', str(text))
                return match.group(1) if match else "00:00"

            # 最新の1行
            latest_row = group_filled.iloc[-1]
            latest_info = str(latest_row['補足情報'])
            営業時間 = str(latest_row['営業時間'])
            更新時刻 = str(latest_row['更新時刻'])

            # 補足カラー
            color = 'black'
            if '中' in latest_info:
                color = 'red'
            elif '販売なし' in latest_info:
                color = 'gray'

                # 「販売中 → 販売なし」の切り替えを検出して終了時刻を追記
                sorted_info = group_filled[['補足情報', '更新時刻']].astype(str).reset_index(drop=True)
                for i in range(len(sorted_info) - 1):
                    before = sorted_info.loc[i, '補足情報']
                    after = sorted_info.loc[i + 1, '補足情報']
                    if '販売中' in before and '販売なし' in after:
                        match = re.search(r'(\d{1,2}:\d{2})', sorted_info.loc[i + 1, '更新時刻'])
                        if match:
                            latest_info += f"（終了時刻{match.group(1)}）"
                        break



            st.markdown(
                f"<div style='font-size:13px'>{title}<br>営業時間：{営業時間}<br>{更新時刻}<br><br>"
                f"全体平均：{avg_total:.1f}分　/　直近1時間平均：{avg_recent:.1f}分</div><br>"
                f"<span style='color:{color}'><div style='font-size:13px'>補足：{latest_info}</div></span>",
                unsafe_allow_html=True
            )

            # グラフ描画
            ax.plot(group_filled['取得時刻'], group_filled['待ち時間'], label=title)



        legend = ax.legend()
        if legend:
            legend.remove()
        
        # 基準日をデータから取得（任意の1日でOK）
        base_date = df['取得時刻'].dt.date.min()

        # 固定時刻範囲を生成（8:45〜21:00）
        x_start = datetime.datetime.combine(base_date, datetime.time(8, 45))
        x_end = datetime.datetime.combine(base_date, datetime.time(21, 0))
        ax.set_xlim([x_start, x_end])

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
