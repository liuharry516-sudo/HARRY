import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
import time

# --- 1. 系統初始化 ---
st.set_page_config(page_title="Harry 專業交易系統", layout="wide")

# CSS 注入：實現閃爍呼吸燈與美化
st.markdown("""
    <style>
    @keyframes blink { 0% { opacity: 1; } 50% { opacity: 0.3; } 100% { opacity: 1; } }
    .status-light { height: 10px; width: 10px; border-radius: 50%; display: inline-block; margin-right: 10px; }
    .light-green { background-color: #00ff00; box-shadow: 0 0 10px #00ff00; animation: blink 1.5s infinite; }
    .light-red { background-color: #ff0000; box-shadow: 0 0 10px #ff0000; }
    </style>
""", unsafe_allow_html=True)

# 1. 登入狀態初始化
if "login_state" not in st.session_state: 
    st.session_state.login_state = False

# 2. 從 Secrets 讀取帳號密碼 (隱藏帳號關鍵處)
if "user_db" not in st.session_state:
    try:
        # 從 Streamlit 後台抓取 user_db 內容
        raw_users = st.secrets["user_db"]
        # 轉換格式，讓程式可以使用
        st.session_state.user_db = {u: {"pwd": str(p), "role": "admin"} for u, p in raw_users.items()}
    except:
        # 如果後台沒設定好，給一個預設值防止程式當掉
        st.session_state.user_db = {"admin": {"pwd": "password", "role": "admin"}}

# 3. 其他資料初始化
if "watchlist" not in st.session_state: st.session_state.watchlist = []
if "recommendations" not in st.session_state: st.session_state.recommendations = {}
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

# --- 3. 側邊欄：功能與狀態燈 ---
with st.sidebar:
    if st.session_state.login_state:
        st.markdown('<div><span class="status-light light-green"></span>系統已授權 (連線中)</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div><span class="status-light light-red"></span>系統未授權</div>', unsafe_allow_html=True)
    
    st.write("---")
    
    if not st.session_state.login_state:
        st.subheader("🔑 系統登入")
        u = st.text_input("帳號", placeholder="輸入帳號")
        p = st.text_input("密碼", type="password", placeholder="輸入密碼")
        
        if st.button("確認登入", use_container_width=True):
            if u not in st.session_state.user_db:
                st.error("❌ 查無此帳號，請重新確認。")
            elif st.session_state.user_db[u]["pwd"] != p:
                st.error("🔒 密碼錯誤，請重新輸入。")
            else:
                msg = st.empty()
                msg.success(f"✅ 登入成功！歡迎回來，{u}")
                time.sleep(1)
                st.session_state.login_state = True
                st.session_state.current_user = u
                st.session_state.user_role = st.session_state.user_db[u]["role"]
                st.rerun()
    else:
        st.write(f"👤 交易員：**{st.session_state.current_user}**")
        if st.button("🏠 系統首頁", use_container_width=True):
            st.session_state.page = "HOME"; st.rerun()
        if st.button("📢 專家推薦與公告", use_container_width=True):
            st.session_state.page = "RECOMMEND"; st.rerun()
        if st.button("⭐ 我的自選股清單", type="primary", use_container_width=True):
            st.session_state.page = "WATCHLIST"; st.rerun()
        if st.button("📊 專家績效排行", use_container_width=True):
            st.session_state.page = "PERFORMANCE"; st.rerun()

        st.container(height=100, border=False) 
        
        st.write("---")
        if st.session_state.user_role == "admin":
            if st.button("⚙️ 管理員後台系統", use_container_width=True):
                st.session_state.page = "ADMIN"; st.rerun()
        
        if st.button("🚪 登出交易系統", use_container_width=True):
            st.session_state.login_state = False
            st.session_state.page = "HOME"; st.rerun()

# --- 4. 主頁面內容 ---
if st.session_state.login_state:
    h_col1, h_col2 = st.columns([3, 1.5])
    with h_col1:
        title_map = {
            "HOME": "🏠 系統控制中心",
            "RECOMMEND": "📢 專家推薦與公告歷史",
            "WATCHLIST": "⭐ 我的自選股管理清單",
            "ANALYSIS": f"📈 技術分析：{st.session_state.target_stock.split('.')[0]}",
            "PERFORMANCE": "📊 專家績效排行 (開發中)",
            "ADMIN": "🛠️ 管理員公告發布系統"
        }
        st.title(title_map.get(st.session_state.page))
        
    with h_col2:
        st.write("")
        s_col, b_col = st.columns([3, 1])
        with s_col:
            raw_input = st.text_input("快速搜尋代碼", placeholder="例如: 2330", label_visibility="collapsed")
        with b_col:
            if st.button("🔍"):
                if raw_input:
                    st.session_state.target_stock = check_stock_exists(raw_input)
                    st.session_state.page = "ANALYSIS"; st.rerun()

    if st.session_state.page == "HOME":
        st.markdown(f"### 🎊 歡迎回來，{st.session_state.current_user}！")
        st.info(f"📅 目前系統時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        st.write("---")
        st.markdown("""
        #### 💡 操作小貼士：
        * 使用上方 **搜尋框** 快速切換任何台股 K 線圖。
        * 點擊左側 **我的自選** 管理您關注的標的。
        * 專家最新動態請查看 **推薦與公告**。
        """)

    elif st.session_state.page == "WATCHLIST":
        st.subheader("📋 您的自選清單")
        if not st.session_state.watchlist:
            st.info("目前尚無自選股。")
        else:
            for stock in st.session_state.watchlist:
                c1, c2, c3 = st.columns([3, 1, 1])
                c1.markdown(f"#### 🔹 {stock.split('.')[0]}")
                if c2.button("查看分析", key=f"v_{stock}"):
                    st.session_state.target_stock = stock; st.session_state.page = "ANALYSIS"; st.rerun()
                if c3.button("移除", key=f"d_{stock}"):
                    st.session_state.watchlist.remove(stock); st.rerun()

    elif st.session_state.page == "ANALYSIS":
        with st.spinner("正在調取即時數據..."):
            df = yf.download(st.session_state.target_stock, period="6mo", progress=False)
            if not df.empty:
                if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                df.index = pd.to_datetime(df.index).strftime('%Y-%m-%d')
                fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'])])
                fig.update_layout(height=550, template="plotly_dark", xaxis_rangeslider_visible=False, xaxis_type='category')
                st.plotly_chart(fig, use_container_width=True)
                if st.button(f"➕ 加入自選"):
                    if st.session_state.target_stock not in st.session_state.watchlist:
                        st.session_state.watchlist.append(st.session_state.target_stock)
                        st.toast("已加入自選！")
            else:
                st.error("查無此股票資料，請檢查代碼是否輸入正確。")

    elif st.session_state.page == "ADMIN":
        st.subheader("📝 管理員公告中心")
        a_date = st.date_input("公告日期", datetime.now())
        a_content = st.text_area("發布內容", height=200)
        if st.button("確認發布公告"):
            st.session_state.recommendations[str(a_date)] = a_content
            st.success("公告已儲存並同步至用戶端。")

    elif st.session_state.page == "PERFORMANCE":
        st.warning("🚧 模組開發中：正在進行專家績效回測數據對接...")

    elif st.session_state.page == "RECOMMEND":
        if not st.session_state.recommendations:
            st.info("目前暫無公告內容。")
        else:
            for d, c in sorted(st.session_state.recommendations.items(), reverse=True):
                with st.expander(f"📅 {d}"):
                    st.write(c)
else:
    st.title("🏠 Harry 專業交易系統")
    st.warning("請在左側側邊欄輸入帳號密碼以解鎖系統。")
