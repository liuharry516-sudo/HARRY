import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
import time

# --- 1. 系統初始化 ---
st.set_page_config(page_title="Harry 專業交易系統", layout="wide")

# CSS 注入 (閃爍狀態燈與美化)
st.markdown("""
    <style>
    @keyframes blink { 0% { opacity: 1; } 50% { opacity: 0.3; } 100% { opacity: 1; } }
    .status-light { height: 10px; width: 10px; border-radius: 50%; display: inline-block; margin-right: 10px; }
    .light-green { background-color: #00ff00; box-shadow: 0 0 10px #00ff00; animation: blink 1.5s infinite; }
    .light-red { background-color: #ff0000; box-shadow: 0 0 10px #ff0000; }
    </style>
""", unsafe_allow_html=True)

# --- 2. 雲端資料讀取 (這就是你在 Colab 測過的邏輯) ---
def load_gsheet_csv(worksheet_name):
    # 你的 Google Sheet ID
    sheet_id = "1i8fslqGdZ6F6Cdx8aU3DfYJ2twuKLWhuPaiQdQ8kv1g"
    # 根據分頁名稱決定 gid (假設第一個分頁是公告，第二個是自選)
    # 如果你只有一個分頁，用 gid=0 即可
    gid = "0" if worksheet_name == "announcements" else "123456789" # 這裡的 gid 需視你實際試算表分頁而定
    csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
    try:
        return pd.read_csv(csv_url)
    except:
        return pd.DataFrame()

# 登入狀態初始化
if "login_state" not in st.session_state: st.session_state.login_state = False
if "user_db" not in st.session_state:
    try:
        st.session_state.user_db = {u: {"pwd": str(p), "role": "admin" if u == "harry" else "user"} for u, p in st.secrets["user_db"].items()}
    except:
        st.session_state.user_db = {"harry": {"pwd": "123", "role": "admin"}}

if "page" not in st.session_state: st.session_state.page = "HOME"
if "target_stock" not in st.session_state: st.session_state.target_stock = "2330.TW"

# --- 3. 核心功能函數 ---
def check_stock_exists(code):
    code = code.strip().upper()
    if "." in code: return code
    for ext in [".TW", ".TWO"]:
        t = yf.Ticker(f"{code}{ext}")
        if t.fast_info.get('last_price') is not None: return f"{code}{ext}"
    return f"{code}.TW"

# --- 4. 側邊欄 ---
with st.sidebar:
    st.markdown(f'<div><span class="status-light {"light-green" if st.session_state.login_state else "light-red"}"></span>系統{"已" if st.session_state.login_state else "未"}授權</div>', unsafe_allow_html=True)
    if not st.session_state.login_state:
        u = st.text_input("帳號")
        p = st.text_input("密碼", type="password")
        if st.button("確認登入"):
            if u in st.session_state.user_db and st.session_state.user_db[u]["pwd"] == p:
                st.session_state.login_state = True
                st.session_state.current_user = u
                st.session_state.user_role = st.session_state.user_db[u]["role"]
                st.rerun()
    else:
        if st.button("🏠 首頁"): st.session_state.page = "HOME"; st.rerun()
        if st.button("📢 專家公告"): st.session_state.page = "RECOMMEND"; st.rerun()
        if st.button("⭐ 自選股"): st.session_state.page = "WATCHLIST"; st.rerun()
        if st.button("🚪 登出"): st.session_state.login_state = False; st.rerun()

# --- 5. 主頁面內容 ---
if st.session_state.login_state:
    if st.session_state.page == "HOME":
        st.title("🏠 系統控制中心")
        st.info(f"歡迎，{st.session_state.current_user}")
        raw_input = st.text_input("搜尋代碼", placeholder="例如: 2330")
        if st.button("🔍"):
            st.session_state.target_stock = check_stock_exists(raw_input)
            st.session_state.page = "ANALYSIS"; st.rerun()

    elif st.session_state.page == "RECOMMEND":
        st.title("📢 專家公告")
        df = load_gsheet_csv("announcements")
        if not df.empty:
            for _, row in df.iloc[::-1].iterrows():
                with st.expander(f"📅 {row.get('date', 'N/A')}"): st.write(row.get('content', '無內容'))
        else:
            st.info("暫無公告。")

    elif st.session_state.page == "ANALYSIS":
        st.title(f"📈 分析：{st.session_state.target_stock}")
        df = yf.download(st.session_state.target_stock, period="6mo", progress=False)
        if not df.empty:
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'])])
            fig.update_layout(height=500, template="plotly_dark", xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)
else:
    st.title("🏠 Harry 專業交易系統")
    st.warning("請登入。")
