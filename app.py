import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
import time
from st_gsheets_connection import GSheetsConnection

# --- 1. 系統初始化 ---
st.set_page_config(page_title="Harry 專業交易系統", layout="wide")

# CSS 注入：美化與動態效果
st.markdown("""
    <style>
    @keyframes blink { 0% { opacity: 1; } 50% { opacity: 0.3; } 100% { opacity: 1; } }
    .status-light { height: 10px; width: 10px; border-radius: 50%; display: inline-block; margin-right: 10px; }
    .light-green { background-color: #00ff00; box-shadow: 0 0 10px #00ff00; animation: blink 1.5s infinite; }
    .light-red { background-color: #ff0000; box-shadow: 0 0 10px #ff0000; }
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] { background-color: #1e1e1e; border-radius: 5px; padding: 10px; color: white; }
    </style>
""", unsafe_allow_html=True)

# 建立雲端資料庫連線
conn = st.connection("gsheets", type=GSheetsConnection)

# 1. 登入狀態初始化
if "login_state" not in st.session_state: 
    st.session_state.login_state = False

# 2. 帳號權限初始化 (維持從 Secrets 讀取以確保最高安全)
if "user_db" not in st.session_state:
    try:
        raw_users = st.secrets["user_db"]
        st.session_state.user_db = {u: {"pwd": str(p), "role": "admin" if u == "harry" else "user"} for u, p in raw_users.items()}
    except:
        st.session_state.user_db = {"harry": {"pwd": "123", "role": "admin"}}

# 3. 系統變數初始化
if "page" not in st.session_state: st.session_state.page = "HOME"
if "target_stock" not in st.session_state: st.session_state.target_stock = "2330.TW"

# --- 2. 核心功能函數 ---
def check_stock_exists(code):
    code = code.strip().upper()
    if "." in code: return code
    for ext in [".TW", ".TWO"]:
        t = yf.Ticker(f"{code}{ext}")
        if t.fast_info.get('last_price') is not None:
            return f"{code}{ext}"
    return f"{code}.TW"

# --- 3. 側邊欄：功能控制與狀態 ---
with st.sidebar:
    if st.session_state.login_state:
        st.markdown('<div><span class="status-light light-green"></span>系統已授權 (雲端同步中)</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div><span class="status-light light-red"></span>系統未授權</div>', unsafe_allow_html=True)
    
    st.write("---")
    
    if not st.session_state.login_state:
        st.subheader("🔑 系統登入")
        u = st.text_input("帳號", placeholder="輸入帳號")
        p = st.text_input("密碼", type="password", placeholder="輸入密碼")
        if st.button("確認登入", use_container_width=True):
            if u in st.session_state.user_db and st.session_state.user_db[u]["pwd"] == p:
                st.success(f"歡迎回來，{u}")
                time.sleep(0.5)
                st.session_state.login_state = True
                st.session_state.current_user = u
                st.session_state.user_role = st.session_state.user_db[u]["role"]
                st.rerun()
            else:
                st.error("❌ 帳號或密碼錯誤")
    else:
        st.write(f"👤 交易員：**{st.session_state.current_user}**")
        if st.button("🏠 系統首頁", use_container_width=True): st.session_state.page = "HOME"; st.rerun()
        if st.button("📢 專家推薦與公告", use_container_width=True): st.session_state.page = "RECOMMEND"; st.rerun()
        if st.button("⭐ 我的自選股清單", type="primary", use_container_width=True): st.session_state.page = "WATCHLIST"; st.rerun()
        if st.button("📊 專家績效排行", use_container_width=True): st.session_state.page = "PERFORMANCE"; st.rerun()

        st.container(height=100, border=False) 
        st.write("---")
        if st.session_state.user_role == "admin":
            if st.button("⚙️ 管理員後台系統", use_container_width=True):
                st.session_state.page = "ADMIN"; st.rerun()
        
        if st.button("🚪 登出交易系統", use_container_width=True):
            st.session_state.login_state = False
            st.rerun()

# --- 4. 主頁面內容 ---
if st.session_state.login_state:
    # 頂部標題與搜尋
    h_col1, h_col2 = st.columns([3, 1.5])
    with h_col1:
        title_map = {
            "HOME": "🏠 系統控制中心",
            "RECOMMEND": "📢 專家推薦與公告歷史",
            "WATCHLIST": "⭐ 我的自選股管理清單",
            "ANALYSIS": f"📈 技術分析：{st.session_state.target_stock.split('.')[0]}",
            "PERFORMANCE": "📊 專家績效排行 (開發中)",
            "ADMIN": "🛠️ 管理員系統後台"
        }
        st.title(title_map.get(st.session_state.page))
    
    with h_col2:
        st.write("")
        s_col, b_col = st.columns([3, 1])
        with s_col:
            raw_input = st.text_input("搜尋代碼", placeholder="例如: 2330", key="search_bar", label_visibility="collapsed")
        with b_col:
            if st.button("🔍"):
                if raw_input:
                    st.session_state.target_stock = check_stock_exists(raw_input)
                    st.session_state.page = "ANALYSIS"; st.rerun()

    # --- 分頁邏輯 ---
    if st.session_state.page == "HOME":
        st.markdown(f"### 🎊 歡迎回來，{st.session_state.current_user}！")
        st.info(f"📅 目前系統時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        st.write("---")
        st.markdown("#### 💡 操作小貼士：使用搜尋框快速查看 K 線，或從自選清單管理標的。")

    elif st.session_state.page == "RECOMMEND":
        # 從雲端讀取公告
        try:
            df = conn.read(worksheet="announcements", ttl="0s")
            if df.empty:
                st.info("目前暫無公告內容。")
            else:
                for idx, row in df.iloc[::-1].iterrows():
                    with st.expander(f"📅 {row['date']}"):
                        st.write(row['content'])
        except:
            st.error("雲端資料庫連線異常，請檢查 Google Sheets 設定。")

    elif st.session_state.page == "WATCHLIST":
        # 從雲端讀取自選股
        try:
            df_w = conn.read(worksheet="watchlist", ttl="0s")
            # 過濾出當前用戶的自選股
            my_watchlist = df_w[df_w['user'] == st.session_state.current_user]['stock'].tolist()
            
            if not my_watchlist:
                st.info("目前尚無自選股。")
            else:
                for stock in my_watchlist:
                    c1, c2, c3 = st.columns([3, 1, 1])
                    c1.markdown(f"#### 🔹 {stock}")
                    if c2.button("查看", key=f"v_{stock}"):
                        st.session_state.target_stock = stock; st.session_state.page = "ANALYSIS"; st.rerun()
                    if c3.button("移除", key=f"d_{stock}"):
                        # 移除邏輯：刪除該列並更新雲端
                        updated_w = df_w[~((df_w['user'] == st.session_state.current_user) & (df_w['stock'] == stock))]
                        conn.update(worksheet="watchlist", data=updated_w)
                        st.rerun()
        except:
            st.error("無法讀取自選清單。")

    elif st.session_state.page == "ANALYSIS":
        with st.spinner("獲取數據中..."):
            df = yf.download(st.session_state.target_stock, period="6mo", progress=False)
            if not df.empty:
                if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                df.index = pd.to_datetime(df.index).strftime('%Y-%m-%d')
                fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'])])
                fig.update_layout(height=550, template="plotly_dark", xaxis_rangeslider_visible=False, xaxis_type='category')
                st.plotly_chart(fig, use_container_width=True)
                
                if st.button("➕ 加入自選清單"):
                    df_w = conn.read(worksheet="watchlist", ttl="0s")
                    if not ((df_w['user'] == st.session_state.current_user) & (df_w['stock'] == st.session_state.target_stock)).any():
                        new_w = pd.concat([df_w, pd.DataFrame({"user": [st.session_state.current_user], "stock": [st.session_state.target_stock]})], ignore_index=True)
                        conn.update(worksheet="watchlist", data=new_w)
                        st.toast("已同步至雲端自選！")
            else:
                st.error("無效代碼。")

    elif st.session_state.page == "ADMIN":
        tab1, tab2 = st.tabs(["📢 公告管理", "👥 帳號權限管理"])
        with tab1:
            st.subheader("發布永久公告")
            a_date = st.date_input("日期", datetime.now())
            a_content = st.text_area("內容", height=150)
            if st.button("確認發布並存入雲端"):
                existing_df = conn.read(worksheet="announcements", ttl="0s")
                new_row = pd.DataFrame({"date": [str(a_date)], "content": [a_content]})
                updated_df = pd.concat([existing_df, new_row], ignore_index=True)
                conn.update(worksheet="announcements", data=updated_df)
                st.success("✅ 已永久存檔！")
        
        with tab2:
            st.write("目前系統帳號清單（唯讀自 Secrets）：")
            for user, info in st.session_state.user_db.items():
                st.text(f"👤 {user} ({info['role']})")

else:
    st.title("🏠 Harry 專業交易系統")
    st.warning("請在側邊欄登入以啟動系統。")
