"""
Harry Professional Trading System - Ultimate Edition
包含完整帳號管理、管理員權限、自選股追蹤、專業技術指標 (MACD/布林/乖離率) 模組
"""

import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time

# ==========================================
# 1. 系統環境與 UI 初始化
# ==========================================
st.set_page_config(
    page_title="Harry 專業交易系統 | 旗艦版", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# 注入高階 CSS 樣式 (呼吸燈、分頁美化、按鈕懸浮效果)
st.markdown("""
    <style>
    /* 狀態呼吸燈動畫 */
    @keyframes blink { 0% { opacity: 1; } 50% { opacity: 0.3; } 100% { opacity: 1; } }
    .status-light { height: 12px; width: 12px; border-radius: 50%; display: inline-block; margin-right: 10px; }
    .light-green { background-color: #00ff00; box-shadow: 0 0 12px #00ff00; animation: blink 1.5s infinite; }
    .light-red { background-color: #ff0000; box-shadow: 0 0 12px #ff0000; }
    .light-yellow { background-color: #ffcc00; box-shadow: 0 0 12px #ffcc00; }
    
    /* 分頁標籤美化 */
    .stTabs [data-baseweb="tab-list"] { gap: 15px; border-bottom: 2px solid #333; padding-bottom: 5px; }
    .stTabs [data-baseweb="tab"] { 
        background-color: #1e1e1e; 
        border-radius: 8px 8px 0px 0px; 
        padding: 12px 24px; 
        color: #ddd; 
        font-weight: bold;
        transition: all 0.3s ease;
    }
    .stTabs [data-baseweb="tab"][aria-selected="true"] {
        background-color: #4CAF50;
        color: white;
    }
    
    /* 隱藏預設 Streamlit 元素 */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    </style>
""", unsafe_allow_html=True)


# ==========================================
# 2. 核心資料庫模擬 (Session State 初始化)
# ==========================================
# 這裡使用 session_state 作為內存資料庫，確保所有 CRUD 操作立刻生效不報錯

# 2.1 登入狀態
if "login_state" not in st.session_state: 
    st.session_state.login_state = False
if "current_user" not in st.session_state:
    st.session_state.current_user = None
if "user_role" not in st.session_state:
    st.session_state.user_role = None

# 2.2 帳號資料庫 (包含封鎖狀態)
if "user_db" not in st.session_state:
    # 預設管理員與一個測試用戶
    default_users = {
        "harry": {"pwd": "123", "role": "admin", "status": "active", "created_at": "2024-01-01"},
        "guest": {"pwd": "123", "role": "user", "status": "active", "created_at": "2024-01-01"}
    }
    try:
        # 嘗試從 Secrets 讀取，並補齊欄位
        raw_users = st.secrets["user_db"]
        st.session_state.user_db = {}
        for u, p in raw_users.items():
            st.session_state.user_db[u] = {
                "pwd": str(p), 
                "role": "admin" if u == "harry" else "user",
                "status": "active",
                "created_at": datetime.now().strftime('%Y-%m-%d')
            }
    except:
        st.session_state.user_db = default_users

# 2.3 公告資料庫 (支援日期設定)
if "announcements_db" not in st.session_state:
    st.session_state.announcements_db = [
        {"id": 1, "date": datetime.now().strftime('%Y-%m-%d'), "author": "系統管理員", "content": "歡迎使用 Harry 專業交易系統，本系統具備完整技術分析模組。"}
    ]

# 2.4 自選股清單資料庫 (區分不同使用者)
if "watchlist_db" not in st.session_state:
    st.session_state.watchlist_db = {
        "harry": ["2330.TW", "2317.TW", "2603.TW"],
        "guest": ["0050.TW"]
    }

# 2.5 頁面導航狀態
if "page" not in st.session_state: st.session_state.page = "HOME"
if "target_stock" not in st.session_state: st.session_state.target_stock = "2330.TW"


# ==========================================
# 3. 專業技術分析與工具模組
# ==========================================
def validate_stock_code(code):
    """驗證股票代碼並自動補齊後綴"""
    code = code.strip().upper()
    if "." in code: return code
    # 簡單偵測：若是數字開頭且小於 4 碼，可能不合法
    if code.isdigit() and len(code) < 4: return None
    
    # 嘗試抓取看是否存在
    for ext in [".TW", ".TWO"]:
        try:
            t = yf.Ticker(f"{code}{ext}")
            if t.fast_info.get('last_price') is not None:
                return f"{code}{ext}"
        except:
            continue
    return f"{code}.TW"

def calc_macd(df, fast=12, slow=26, signal=9):
    """計算 MACD 指標"""
    ema_fast = df['Close'].ewm(span=fast, adjust=False).mean()
    ema_slow = df['Close'].ewm(span=slow, adjust=False).mean()
    df['MACD'] = ema_fast - ema_slow
    df['Signal_Line'] = df['MACD'].ewm(span=signal, adjust=False).mean()
    df['MACD_Histogram'] = df['MACD'] - df['Signal_Line']
    return df

def calc_bollinger_bands(df, window=20, num_std=2):
    """計算布林通道"""
    df['BB_Mid'] = df['Close'].rolling(window=window).mean()
    df['BB_Std'] = df['Close'].rolling(window=window).std()
    df['BB_Up'] = df['BB_Mid'] + (df['BB_Std'] * num_std)
    df['BB_Low'] = df['BB_Mid'] - (df['BB_Std'] * num_std)
    return df

def calc_bias(df, window=25):
    """計算 25日乖離率 (Bias)"""
    ma_25 = df['Close'].rolling(window=window).mean()
    df['Bias_25'] = ((df['Close'] - ma_25) / ma_25) * 100
    return df

def draw_professional_chart(df, ticker):
    """繪製專業技術分析圖表 (K線 + 布林 + MACD + 乖離率)"""
    # 建立多子圖 (列數, 行數, 共享X軸, 高度比例)
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, 
                        vertical_spacing=0.03, 
                        row_heights=[0.6, 0.2, 0.2],
                        subplot_titles=(f"K線與布林通道 ({ticker})", "MACD (12, 26, 9)", "25日乖離率 (%)"))

    # --- Row 1: K線圖與布林通道 ---
    fig.add_trace(go.Candlestick(
        x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
        name='K棒', increasing_line_color='#ef5350', decreasing_line_color='#26a69a'
    ), row=1, col=1)
    
    # 布林通道線
    fig.add_trace(go.Scatter(x=df.index, y=df['BB_Up'], line=dict(color='rgba(173, 216, 230, 0.5)', width=1), name='BB上軌'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['BB_Low'], line=dict(color='rgba(173, 216, 230, 0.5)', width=1), name='BB下軌', fill='tonexty', fillcolor='rgba(173, 216, 230, 0.1)'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['BB_Mid'], line=dict(color='orange', width=1.5, dash='dash'), name='BB中軌(20MA)'), row=1, col=1)

    # --- Row 2: MACD ---
    colors = ['#26a69a' if val >= 0 else '#ef5350' for val in df['MACD_Histogram']]
    fig.add_trace(go.Bar(x=df.index, y=df['MACD_Histogram'], marker_color=colors, name='MACD柱狀圖'), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['MACD'], line=dict(color='blue', width=1.5), name='MACD線'), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['Signal_Line'], line=dict(color='orange', width=1.5), name='訊號線'), row=2, col=1)

    # --- Row 3: 25日乖離率 ---
    fig.add_trace(go.Scatter(x=df.index, y=df['Bias_25'], line=dict(color='purple', width=1.5), name='25日乖離率'), row=3, col=1)
    fig.add_hline(y=0, line_dash="dash", line_color="gray", row=3, col=1) # 零軸

    # 圖表整體設定
    fig.update_layout(
        height=850, 
        template="plotly_dark", 
        xaxis_rangeslider_visible=False,
        hovermode="x unified",
        margin=dict(l=40, r=40, t=40, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    
    # 去除假日空白 (針對台股)
    fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
    return fig


# ==========================================
# 4. 側邊欄控制中心 (導航與登入)
# ==========================================
with st.sidebar:
    st.markdown("## ⚙️ 系統控制台")
    
    # 狀態顯示器
    if st.session_state.login_state:
        status_color = "light-green" if st.session_state.user_db[st.session_state.current_user]["status"] == "active" else "light-yellow"
        st.markdown(f'<div><span class="status-light {status_color}"></span>系統連線正常 (授權完畢)</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div><span class="status-light light-red"></span>系統未登入 / 未授權</div>', unsafe_allow_html=True)
    
    st.divider()

    # 登入邏輯
    if not st.session_state.login_state:
        st.subheader("🔑 系統登入")
        with st.form("login_form"):
            login_user = st.text_input("帳號名稱", placeholder="請輸入使用者帳號")
            login_pwd = st.text_input("存取密碼", type="password", placeholder="請輸入密碼")
            submit_login = st.form_submit_button("執行登入", use_container_width=True)
            
            if submit_login:
                if login_user not in st.session_state.user_db:
                    st.error("❌ 查無此帳號，請聯絡管理員。")
                elif st.session_state.user_db[login_user]["pwd"] != login_pwd:
                    st.error("🔒 密碼驗證失敗。")
                elif st.session_state.user_db[login_user]["status"] == "blocked":
                    st.error("⛔ 此帳號已被管理員封鎖，禁止存取。")
                else:
                    st.session_state.login_state = True
                    st.session_state.current_user = login_user
                    st.session_state.user_role = st.session_state.user_db[login_user]["role"]
                    
                    # 確保新用戶有自選清單
                    if login_user not in st.session_state.watchlist_db:
                        st.session_state.watchlist_db[login_user] = []
                        
                    st.success(f"✅ 登入成功！緩衝中...")
                    time.sleep(0.8)
                    st.rerun()
    
    # 登入後的選單導航
    else:
        # 用戶資訊卡片
        user_role_display = "👑 管理員 (Sudo)" if st.session_state.user_role == "admin" else "👤 交易員 (User)"
        st.info(f"**目前身分**：\n{st.session_state.current_user}\n{user_role_display}")
        
        st.markdown("### 📌 功能導航")
        nav_options = {
            "🏠 系統首頁": "HOME",
            "📢 專家推薦與公告": "RECOMMEND",
            "⭐ 我的自選清單": "WATCHLIST",
            "📈 專業技術分析": "ANALYSIS",
            "📊 專家績效排行": "PERFORMANCE"
        }
        
        for btn_text, page_code in nav_options.items():
            # 讓當前頁面按鈕顯示為 Primary
            btn_type = "primary" if st.session_state.page == page_code else "secondary"
            if st.button(btn_text, use_container_width=True, type=btn_type):
                st.session_state.page = page_code
                st.rerun()

        st.container(height=30, border=False) # 墊高排版
        
        # 管理員專屬後台按鈕
        if st.session_state.user_role == "admin":
            st.markdown("### 🛠️ 後台管理")
            btn_type = "primary" if st.session_state.page == "ADMIN" else "secondary"
            if st.button("⚙️ 進入系統後台 (Sudo)", use_container_width=True, type=btn_type):
                st.session_state.page = "ADMIN"
                st.rerun()
        
        st.divider()
        if st.button("🚪 安全登出系統", use_container_width=True):
            st.session_state.login_state = False
            st.session_state.current_user = None
            st.session_state.user_role = None
            st.session_state.page = "HOME"
            st.rerun()


# ==========================================
# 5. 主畫面路由與內容渲染
# ==========================================
if not st.session_state.login_state:
    # 未登入畫面
    st.title("🛡️ Harry 專業量化交易系統")
    st.markdown("### 系統狀態：鎖定中")
    st.warning("請於左側控制台輸入授權帳號與密碼以進入系統。")
    st.image("https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?auto=format&fit=crop&q=80&w=1000", caption="Professional Trading Desk", use_container_width=True)

else:
    # 頂部搜尋列 (全域通用)
    col_title, col_search = st.columns([2.5, 1.5])
    with col_search:
        st.write("") # 微調對齊
        with st.form("search_form", border=False):
            scol1, scol2 = st.columns([3, 1])
            search_val = scol1.text_input("🔍 代碼快搜", placeholder="輸入代碼 (例: 2330)", label_visibility="collapsed")
            if scol2.form_submit_button("分析", use_container_width=True):
                if search_val:
                    valid_code = validate_stock_code(search_val)
                    if valid_code:
                        st.session_state.target_stock = valid_code
                        st.session_state.page = "ANALYSIS"
                        st.rerun()
                    else:
                        st.error("代碼格式錯誤")

    # 根據路由顯示對應頁面
    page = st.session_state.page

    # ----------------------------------------
    # [頁面] 系統首頁 (HOME)
    # ----------------------------------------
    if page == "HOME":
        with col_title: st.title("🏠 系統控制中心")
        
        st.markdown(f"### 歡迎回來，**{st.session_state.current_user}**。")
        st.caption(f"🕒 伺服器時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        st.divider()
        
        h_col1, h_col2, h_col3 = st.columns(3)
        h_col1.metric("關注自選數量", len(st.session_state.watchlist_db.get(st.session_state.current_user, [])))
        h_col2.metric("最新公告數量", len(st.session_state.announcements_db))
        h_col3.metric("系統狀態", "🟢 運行中")
        
        st.markdown("""
        #### 💡 系統操作指南：
        1. **快速搜尋**：利用右上角搜尋框，輸入股票代碼即可快速跳轉至技術分析圖表。
        2. **技術分析**：圖表內建 MACD、布林通道與 25日乖離率，符合進階交易員需求。
        3. **自選清單**：在分析頁面可將標的加入「我的自選」，方便後續追蹤。
        4. **管理員權限**：系統支援多帳號管理，具備封鎖、刪除與發布特定日期公告之權限。
        """)

    # ----------------------------------------
    # [頁面] 專家推薦與公告 (RECOMMEND)
    # ----------------------------------------
    elif page == "RECOMMEND":
        with col_title: st.title("📢 專家推薦與系統公告")
        
        if not st.session_state.announcements_db:
            st.info("📭 目前系統無任何公告訊息。")
        else:
            # 依據日期反向排序 (最新的在最上面)
            sorted_announcements = sorted(st.session_state.announcements_db, key=lambda x: x["date"], reverse=True)
            for ann in sorted_announcements:
                with st.expander(f"📅 發布日期：{ann['date']} | 發布者：{ann['author']}", expanded=True):
                    st.write(ann['content'])

    # ----------------------------------------
    # [頁面] 我的自選清單 (WATCHLIST)
    # ----------------------------------------
    elif page == "WATCHLIST":
        with col_title: st.title("⭐ 我的自選股管理")
        
        my_list = st.session_state.watchlist_db.get(st.session_state.current_user, [])
        if not my_list:
            st.info("您目前沒有追蹤任何標的。請利用右上角搜尋並加入自選。")
        else:
            # 建立動態更新的資料表
            st.write("以下為您關注的標的清單：")
            
            for stock in my_list:
                w_col1, w_col2, w_col3, w_col4 = st.columns([2, 2, 1, 1])
                w_col1.markdown(f"### 🏷️ {stock}")
                
                # 即時抓取最新價格 (輕量化抓取)
                try:
                    tk = yf.Ticker(stock)
                    price = tk.fast_info.get('last_price', 0)
                    prev_close = tk.fast_info.get('previous_close', 0)
                    if price and prev_close:
                        change = price - prev_close
                        pct = (change / prev_close) * 100
                        color = "red" if change > 0 else "green" # 台股紅漲綠跌
                        sign = "+" if change > 0 else ""
                        w_col2.markdown(f"<h4 style='color:{color};'>$ {price:.2f} ({sign}{pct:.2f}%)</h4>", unsafe_allow_html=True)
                    else:
                        w_col2.write("讀取中...")
                except:
                    w_col2.write("資料異常")

                if w_col3.button("📈 分析", key=f"view_{stock}", use_container_width=True):
                    st.session_state.target_stock = stock
                    st.session_state.page = "ANALYSIS"
                    st.rerun()
                
                if w_col4.button("🗑️ 移除", key=f"del_{stock}", type="primary", use_container_width=True):
                    st.session_state.watchlist_db[st.session_state.current_user].remove(stock)
                    st.toast(f"已將 {stock} 移出自選清單")
                    st.rerun()
                st.divider()

    # ----------------------------------------
    # [頁面] 專業技術分析 (ANALYSIS)
    # ----------------------------------------
    elif page == "ANALYSIS":
        target = st.session_state.target_stock
        with col_title: st.title(f"📈 技術分析中控台：{target}")
        
        # 加入自選功能
        my_watchlist = st.session_state.watchlist_db.get(st.session_state.current_user, [])
        is_in_watchlist = target in my_watchlist
        
        a_col1, a_col2 = st.columns([1, 4])
        with a_col1:
            if not is_in_watchlist:
                if st.button("➕ 加入我的自選", type="primary", use_container_width=True):
                    st.session_state.watchlist_db[st.session_state.current_user].append(target)
                    st.toast(f"✅ 成功將 {target} 加入自選")
                    st.rerun()
            else:
                if st.button("✔️ 已在自選 (點擊移除)", use_container_width=True):
                    st.session_state.watchlist_db[st.session_state.current_user].remove(target)
                    st.toast(f"🗑️ 已將 {target} 移出")
                    st.rerun()
        
        with st.spinner("🚀 正在從 Yahoo Finance 獲取歷史資料與計算指標..."):
            try:
                # 抓取過去半年資料
                df = yf.download(target, period="6mo", progress=False)
                
                if df.empty:
                    st.error("⚠️ 無法獲取資料，請確認該股票代碼是否正確或已下市。")
                else:
                    # 處理多重索引問題 (yf 新版常見問題)
                    if isinstance(df.columns, pd.MultiIndex):
                        df.columns = df.columns.get_level_values(0)
                    
                    # 執行技術指標計算
                    df = calc_macd(df)
                    df = calc_bollinger_bands(df)
                    df = calc_bias(df)
                    
                    # 濾除 NaN 以免圖表前段空白
                    df = df.dropna(subset=['MACD', 'BB_Up', 'Bias_25'])
                    
                    # 繪製圖表
                    fig = draw_professional_chart(df, target)
                    st.plotly_chart(fig, use_container_width=True)
                    
            except Exception as e:
                st.error(f"系統執行分析時發生錯誤：{e}")

    # ----------------------------------------
    # [頁面] 專家績效排行 (PERFORMANCE)
    # ----------------------------------------
    elif page == "PERFORMANCE":
        with col_title: st.title("📊 專家績效評估排行榜")
        st.warning("🚧 此模組目前正在進行量化回測對接開發，敬請期待後續版本更新。")
        st.image("https://images.unsplash.com/photo-1642543492481-44e81e3914a7?auto=format&fit=crop&q=80&w=1000", caption="Performance Analytics - Coming Soon", use_container_width=True)


    # ----------------------------------------
    # [頁面] 管理員後台 (ADMIN) - Sudo Only
    # ----------------------------------------
    elif page == "ADMIN":
        if st.session_state.user_role != "admin":
            st.error("🛑 存取被拒。您沒有權限進入此頁面。")
        else:
            with col_title: st.title("🛠️ Sudo 系統後台管理")
            
            tab_notice, tab_users = st.tabs(["📢 公告與推薦發布", "👥 用戶權限與帳號管理"])
            
            # --- Tab 1: 發布公告 ---
            with tab_notice:
                st.subheader("✍️ 新增系統公告或個股推薦")
                with st.form("new_announcement_form"):
                    n_date = st.date_input("設定發布日期", datetime.now())
                    n_content = st.text_area("請輸入公告內容或推薦理由", height=150)
                    submit_notice = st.form_submit_button("🚀 確認發布至全系統", type="primary")
                    
                    if submit_notice:
                        if n_content.strip() == "":
                            st.error("內容不可為空！")
                        else:
                            new_id = len(st.session_state.announcements_db) + 1
                            st.session_state.announcements_db.append({
                                "id": new_id,
                                "date": n_date.strftime('%Y-%m-%d'),
                                "author": st.session_state.current_user,
                                "content": n_content
                            })
                            st.success("✅ 公告發布成功！所有用戶皆可看見。")
            
            # --- Tab 2: 帳號管理 ---
            with tab_users:
                st.subheader("➕ 新增用戶帳號")
                with st.expander("展開新增面板"):
                    with st.form("new_user_form"):
                        c1, c2, c3 = st.columns(3)
                        new_u = c1.text_input("新帳號名稱")
                        new_p = c2.text_input("初始密碼", type="password")
                        new_role = c3.selectbox("權限等級", ["user", "admin"])
                        
                        if st.form_submit_button("執行創建"):
                            if new_u in st.session_state.user_db:
                                st.warning("⚠️ 該帳號名稱已被使用。")
                            elif not new_u or not new_p:
                                st.error("⚠️ 帳號與密碼欄位不可空白。")
                            else:
                                st.session_state.user_db[new_u] = {
                                    "pwd": new_p,
                                    "role": new_role,
                                    "status": "active",
                                    "created_at": datetime.now().strftime('%Y-%m-%d')
                                }
                                st.session_state.watchlist_db[new_u] = []
                                st.success(f"✅ 成功建立帳號：{new_u}")
                                st.rerun()

                st.divider()
                st.subheader("📋 現有帳號管理清單")
                
                # 建立資料表視圖
                for user, info in st.session_state.user_db.items():
                    u_col1, u_col2, u_col3, u_col4 = st.columns([2, 1, 1, 2])
                    
                    # 帳號與身分
                    role_badge = "👑 管理員" if info['role'] == "admin" else "👤 一般"
                    status_badge = "🟢 正常" if info['status'] == "active" else "🔴 封鎖中"
                    u_col1.markdown(f"**{user}** <br><small>{role_badge} | {status_badge}</small>", unsafe_allow_html=True)
                    
                    # 建立時間
                    u_col2.write(f"建立於:\n{info.get('created_at', 'N/A')}")
                    
                    # 操作按鈕 (禁止刪除或封鎖自己)
                    if user != st.session_state.current_user:
                        # 封鎖 / 解封
                        action_text = "解鎖帳號" if info['status'] == "blocked" else "封鎖帳號"
                        btn_type = "secondary" if info['status'] == "blocked" else "primary"
                        if u_col3.button(action_text, key=f"block_{user}", type=btn_type, use_container_width=True):
                            st.session_state.user_db[user]['status'] = "active" if info['status'] == "blocked" else "blocked"
                            st.toast(f"已更新 {user} 的狀態為：{st.session_state.user_db[user]['status']}")
                            st.rerun()
                            
                        # 刪除
                        if u_col4.button("🗑️ 永久刪除", key=f"del_{user}", use_container_width=True):
                            del st.session_state.user_db[user]
                            if user in st.session_state.watchlist_db:
                                del st.session_state.watchlist_db[user]
                            st.toast(f"✅ 已徹底刪除帳號：{user}")
                            st.rerun()
                    else:
                        u_col3.write("*無法操作本機帳號*")
                    
                    st.markdown("---")
