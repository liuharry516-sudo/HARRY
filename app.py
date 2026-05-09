import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os
import datetime
import time
import hashlib
import json
import uuid
import socket
from io import StringIO
from zoneinfo import ZoneInfo
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from sqlalchemy import create_engine, Column, Integer, String, Float, Text, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import logging

# ==============================================================================
# [BUGFIX] 設定日誌系統以便追蹤問題
# ==============================================================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==============================================================================
# [STAGE 1] 硬體級持久化鎖定 (解決「帳號重整就不見」的致命傷)
# ==============================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_STORAGE = os.path.join(BASE_DIR, "harry_data")
if not os.path.exists(BASE_STORAGE):
    os.makedirs(BASE_STORAGE, exist_ok=True)

# 應用密鑰檔案
APP_SECRET_FILE = os.path.join(BASE_STORAGE, "app_secret.key")
def get_app_secret():
    if os.path.exists(APP_SECRET_FILE):
        return open(APP_SECRET_FILE, "r").read().strip()
    s = os.urandom(32).hex()
    with open(APP_SECRET_FILE, "w") as f:
        f.write(s)
    return s

APP_SECRET = get_app_secret()

DB_ABS_PATH = os.path.join(BASE_STORAGE, "HARRY_SUPREME_V13.db")
engine = create_engine(f"sqlite:///{DB_ABS_PATH}", connect_args={"check_same_thread": False})
Base = declarative_base()

# ==============================================================================
# [BUGFIX] 移除 scoped_session，改用普通 sessionmaker + 每次請求建立新 session
# ==============================================================================
SessionLocal = sessionmaker(bind=engine)

def get_db():
    """獲取資料庫 session，確保線程安全"""
    return SessionLocal()

# ORM Models
class User(Base):
    __tablename__ = 'users'
    uid = Column(Integer, primary_key=True)
    username = Column(String(100), unique=True, nullable=False)
    password = Column(String(128), nullable=False)
    role = Column(String(50), default="user")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.now)

class AuditLog(Base):
    __tablename__ = 'audit_logs'
    id = Column(Integer, primary_key=True)
    actor = Column(String(100))
    action = Column(String(200))
    target = Column(String(200))
    created_at = Column(DateTime, default=datetime.datetime.now)

class FinancialCache(Base):
    __tablename__ = 'financial_cache'
    id = Column(Integer, primary_key=True)
    symbol = Column(String(50), index=True)
    fetched_at = Column(DateTime, default=datetime.datetime.now)
    info_text = Column(Text)
    financials_csv = Column(Text)
    balance_csv = Column(Text)
    cashflow_csv = Column(Text)
    institutional_csv = Column(Text)
    major_csv = Column(Text)

class Watchlist(Base):
    __tablename__ = 'watchlist'
    id = Column(Integer, primary_key=True)
    owner = Column(String(100))
    symbol = Column(String(50))
    created_at = Column(DateTime, default=datetime.datetime.now)

class ManagerHolding(Base):
    __tablename__ = 'manager_holdings'
    id = Column(Integer, primary_key=True)
    symbol = Column(String(50))
    shares = Column(Float, default=0.0)
    avg_price = Column(Float, default=0.0)
    entry_date = Column(DateTime, default=datetime.datetime.now)
    active = Column(Boolean, default=True)

class ManagerTransaction(Base):
    __tablename__ = 'manager_transactions'
    id = Column(Integer, primary_key=True)
    actor = Column(String(100))
    action = Column(String(10))
    symbol = Column(String(50))
    shares = Column(Float)
    price = Column(Float)
    created_at = Column(DateTime, default=datetime.datetime.now)

class PortfolioMeta(Base):
    __tablename__ = 'portfolio_meta'
    id = Column(Integer, primary_key=True)
    initial_capital = Column(Float, default=10000.0)
    cash = Column(Float, default=10000.0)
    updated_at = Column(DateTime, default=datetime.datetime.now)

class PortfolioSnapshot(Base):
    __tablename__ = 'portfolio_snapshots'
    id = Column(Integer, primary_key=True)
    value = Column(Float)
    created_at = Column(DateTime, default=datetime.datetime.now)

class Subscriber(Base):
    __tablename__ = 'subscribers'
    id = Column(Integer, primary_key=True)
    email = Column(String(200))
    created_at = Column(DateTime, default=datetime.datetime.now)

class Notification(Base):
    __tablename__ = 'notifications'
    id = Column(Integer, primary_key=True)
    subject = Column(String(255))
    body = Column(Text)
    created_at = Column(DateTime, default=datetime.datetime.now)
    sent = Column(Boolean, default=False)

class SystemNotice(Base):
    __tablename__ = 'notices'
    nid = Column(Integer, primary_key=True)
    title = Column(String(255))
    body = Column(Text)
    author = Column(String(100))
    created_at = Column(DateTime, default=datetime.datetime.now)

class InviteToken(Base):
    __tablename__ = 'invite_tokens'
    id = Column(Integer, primary_key=True)
    token = Column(String(128), unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.now)
    expires_at = Column(DateTime, nullable=True)
    used = Column(Boolean, default=False)
    assigned_user = Column(String(100), nullable=True)

Base.metadata.create_all(engine)

# ==============================================================================
# [BUGFIX] 改進的時區與市場狀態檢查
# ==============================================================================
def tz_now():
    """返回台北時區的當前時間"""
    return datetime.datetime.now(ZoneInfo("Asia/Taipei"))

def is_market_open(dt: datetime.datetime = None) -> bool:
    """檢查台灣股市是否開盤（台北時間）"""
    now = dt or tz_now()
    # 移除時區信息以進行比較
    if isinstance(now, datetime.datetime) and now.tzinfo:
        now = now.replace(tzinfo=None)
    
    # 週一(0)~週五(4) 09:00-13:30
    if now.weekday() >= 5:
        return False
    open_time = now.replace(hour=9, minute=0, second=0, microsecond=0)
    close_time = now.replace(hour=13, minute=30, second=0, microsecond=0)
    return open_time <= now <= close_time

def render_status_light(label: str, color: str = "#10b981", blink: bool = False):
    """渲染狀態指示燈"""
    blink_speed = float(st.session_state.get('blink_speed', 1.0))
    anim_style = f"animation: harry-blinker {blink_speed}s linear infinite;" if blink else ""
    size = 14
    html = f"""
    <div style='display:flex;align-items:center;gap:10px'>
        <div class='harry-light' style='width:{size}px;height:{size}px;background:{color};border-radius:50%;{anim_style}'></div>
        <div style='color:#d1d5db'>{label}</div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

# ==============================================================================
# [BUGFIX] 改進的股票資料取得函式 - 增加逾時處理與備用方案
# ==============================================================================
def safe_ticker_fetch(symbol: str, retries: int = 3, backoff: float = 1.0, timeout: int = 10):
    """
    安全地從 yfinance 取得股票資料，包含重試機制與逾時處理
    """
    db = get_db()
    last_exc = None
    
    for attempt in range(max(1, retries)):
        try:
            # 建立 Ticker 物件（yfinance 使用預設逾時）
            tk = yf.Ticker(symbol)
            
            # 分別取得各項資料，每項失敗獨立處理
            info = {}
            try:
                info = tk.info or {}
            except Exception as e:
                logger.warning(f"Failed to fetch info for {symbol}: {e}")
                info = {}
            
            financials = pd.DataFrame()
            try:
                financials = tk.financials or pd.DataFrame()
            except Exception as e:
                logger.warning(f"Failed to fetch financials for {symbol}: {e}")
            
            balance = pd.DataFrame()
            try:
                balance = tk.balance_sheet or pd.DataFrame()
            except Exception as e:
                logger.warning(f"Failed to fetch balance for {symbol}: {e}")
            
            cashflow = pd.DataFrame()
            try:
                cashflow = tk.cashflow or pd.DataFrame()
            except Exception as e:
                logger.warning(f"Failed to fetch cashflow for {symbol}: {e}")
            
            inst = pd.DataFrame()
            try:
                inst = tk.institutional_holders or pd.DataFrame()
            except Exception as e:
                logger.warning(f"Failed to fetch institutional for {symbol}: {e}")
            
            major = pd.DataFrame()
            try:
                major = tk.major_holders or pd.DataFrame()
            except Exception as e:
                logger.warning(f"Failed to fetch major for {symbol}: {e}")
            
            logger.info(f"Successfully fetched data for {symbol} on attempt {attempt + 1}")
            db.close()
            return info, financials, balance, cashflow, inst, major
            
        except Exception as e:
            last_exc = e
            logger.warning(f"Attempt {attempt + 1} failed for {symbol}: {e}")
            try:
                log = AuditLog(actor='system', action='yfinance_retry', target=f"{symbol}: {str(e)[:100]}")
                db.add(log)
                db.commit()
            except Exception:
                db.rollback()
            
            if attempt < retries - 1:
                wait_time = backoff * (2 ** attempt)
                logger.info(f"Waiting {wait_time}s before retry...")
                time.sleep(wait_time)
    
    try:
        log = AuditLog(actor='system', action='yfinance_fetch_failed', target=f"{symbol}: {str(last_exc)[:100]}")
        db.add(log)
        db.commit()
    except Exception:
        db.rollback()
    
    db.close()
    logger.error(f"All retries exhausted for {symbol}")
    return {}, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

# ==============================================================================
# [BUGFIX] 改進的價格取得函式 - 使用 Ticker.info 的 currentPrice 欄位
# ==============================================================================
def get_latest_price(symbol: str, timeout: int = 10):
    """
    取得最新股價，優先使用 info['currentPrice']，次選 info['regularMarketPrice']，
    最後才用歷史資料
    """
    try:
        tk = yf.Ticker(symbol)
        
        # 嘗試從 info 取得各種價格欄位
        try:
            info = tk.info or {}
            price = (info.get('currentPrice') or 
                    info.get('regularMarketPrice') or 
                    info.get('previousClose'))
            if price and price > 0:
                logger.info(f"Got price for {symbol} from info: {price}")
                return float(price)
        except Exception as e:
            logger.warning(f"Failed to get price from info for {symbol}: {e}")
        
        # Fallback 到歷史資料
        try:
            hist = tk.history(period='5d')
            if not hist.empty and 'Close' in hist.columns:
                price = float(hist['Close'].iloc[-1])
                if price and price > 0:
                    logger.info(f"Got price for {symbol} from history: {price}")
                    return price
        except Exception as e:
            logger.warning(f"Failed to get price from history for {symbol}: {e}")
        
        logger.error(f"Could not get price for {symbol}")
        return None
        
    except Exception as e:
        logger.error(f"Error in get_latest_price for {symbol}: {e}")
        return None

# ==============================================================================
# [BUGFIX] 改進的郵件發送函式 - 增強的錯誤處理和重試
# ==============================================================================
SMTP_CONFIG_FILE = os.path.join(BASE_STORAGE, "smtp_config.json")

def load_smtp_config():
    """加載 SMTP 設定（優先檔案，次選環境變數）"""
    if os.path.exists(SMTP_CONFIG_FILE):
        try:
            with open(SMTP_CONFIG_FILE, 'r') as f:
                txt = f.read().strip()
                if not txt:
                    logger.warning("SMTP config file is empty")
                    return None
                return json.loads(txt)
        except Exception as e:
            logger.error(f"Failed to load SMTP config from file: {e}")

    # Fallback: 環境變數
    host = os.environ.get('SMTP_HOST') or os.environ.get('MAIL_HOST')
    if host:
        try:
            cfg = {
                'host': host,
                'port': int(os.environ.get('SMTP_PORT', os.environ.get('MAIL_PORT', 587))),
                'username': os.environ.get('SMTP_USER') or os.environ.get('MAIL_USER'),
                'password': os.environ.get('SMTP_PASS') or os.environ.get('MAIL_PASS'),
                'from': os.environ.get('SMTP_FROM') or os.environ.get('MAIL_FROM') or host,
                'tls': str(os.environ.get('SMTP_TLS', 'True')).lower() in ('1', 'true', 'yes'),
                'ssl': str(os.environ.get('SMTP_SSL', 'False')).lower() in ('1', 'true', 'yes'),
            }
            logger.info(f"Loaded SMTP config from environment: {cfg['host']}")
            return cfg
        except Exception as e:
            logger.error(f"Failed to load SMTP config from environment: {e}")
            return None

    logger.info("No SMTP config found")
    return None

def save_smtp_config(cfg: dict):
    """保存 SMTP 設定到檔案"""
    try:
        with open(SMTP_CONFIG_FILE, 'w') as f:
            json.dump(cfg, f, indent=2)
        logger.info("SMTP config saved successfully")
    except Exception as e:
        logger.error(f"Failed to save SMTP config: {e}")

def send_email(to_email: str, subject: str, body: str, cfg: dict):
    """
    發送郵件，支援重試機制和詳細錯誤日誌
    """
    db = get_db()
    host = cfg.get('host')
    port = int(cfg.get('port', 587))
    username = cfg.get('username')
    password = cfg.get('password')
    use_tls = bool(cfg.get('tls', True))
    use_ssl = bool(cfg.get('ssl', False))
    from_addr = cfg.get('from') or username or host

    if not host:
        raise ValueError('SMTP host is not configured')

    last_exc = None
    attempts = int(cfg.get('retries', 3)) if cfg.get('retries') else 3
    
    for attempt in range(attempts):
        try:
            logger.info(f"Attempt {attempt + 1} to send email to {to_email}")
            
            # 使用 MIME 構建郵件（更可靠）
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = from_addr
            msg['To'] = to_email
            
            # 郵件內容（支援 HTML）
            msg_text = MIMEText(body, 'plain', 'utf-8')
            msg.attach(msg_text)

            # 連接和發送
            if use_ssl or port == 465:
                logger.info(f"Connecting via SSL to {host}:{port}")
                with smtplib.SMTP_SSL(host, port, timeout=15) as server:
                    if username and password:
                        server.login(username, password)
                    server.send_message(msg)
            else:
                logger.info(f"Connecting via SMTP to {host}:{port}")
                with smtplib.SMTP(host, port, timeout=15) as server:
                    server.ehlo()
                    if use_tls:
                        server.starttls()
                        server.ehlo()
                    if username and password:
                        server.login(username, password)
                    server.send_message(msg)

            logger.info(f"Email sent successfully to {to_email}")
            
            try:
                log = AuditLog(actor='system', action='smtp_send_ok', 
                             target=f"{to_email}@{host}:{port}")
                db.add(log)
                db.commit()
            except Exception:
                db.rollback()
            
            db.close()
            return True
            
        except smtplib.SMTPAuthenticationError as e:
            last_exc = e
            logger.error(f"SMTP authentication failed: {e}")
            try:
                log = AuditLog(actor='system', action='smtp_auth_failed', 
                             target=f"{to_email}: Authentication error")
                db.add(log)
                db.commit()
            except Exception:
                db.rollback()
            raise  # 認證錯誤不重試
            
        except smtplib.SMTPException as e:
            last_exc = e
            logger.error(f"SMTP error on attempt {attempt + 1}: {e}")
            try:
                log = AuditLog(actor='system', action='smtp_send_failed', 
                             target=f"{to_email}: {str(e)[:100]}")
                db.add(log)
                db.commit()
            except Exception:
                db.rollback()
            
            if attempt < attempts - 1:
                wait_time = (2 ** attempt)
                logger.info(f"Waiting {wait_time}s before retry...")
                time.sleep(wait_time)
        
        except Exception as e:
            last_exc = e
            logger.error(f"Unexpected error on attempt {attempt + 1}: {e}")
            try:
                log = AuditLog(actor='system', action='smtp_send_failed', 
                             target=f"{to_email}: {str(e)[:100]}")
                db.add(log)
                db.commit()
            except Exception:
                db.rollback()
            
            if attempt < attempts - 1:
                time.sleep(2 ** attempt)

    db.close()
    if last_exc:
        raise last_exc
    raise Exception(f"Failed to send email after {attempts} attempts")

# ==============================================================================
# [BUGFIX] 改進的通知系統
# ==============================================================================
def notify_subscribers(subject: str, body: str):
    """
    通知所有訂閱者，優先使用 SMTP，失敗時寫入 outbox
    """
    db = get_db()
    
    try:
        notif = Notification(subject=subject, body=body, sent=False)
        db.add(notif)
        log = AuditLog(actor='system', action='notify', target=subject[:100])
        db.add(log)
        db.commit()
    except Exception:
        db.rollback()

    subs = db.query(Subscriber).all()
    total = len(subs)
    result = {'mode': 'none', 'total_subs': total, 'sent_count': 0, 'failures': [], 'outbox_written': 0}

    smtp_cfg = load_smtp_config()
    if not smtp_cfg:
        logger.warning("No SMTP config, using outbox mode")
        outdir = os.path.join(BASE_STORAGE, 'outbox')
        os.makedirs(outdir, exist_ok=True)
        out_count = 0
        for s in subs:
            try:
                safe_email = s.email.replace('@', '_at_').replace('.', '_dot_')
                fname = os.path.join(outdir, f"{int(time.time())}_{safe_email}.eml")
                with open(fname, 'w', encoding='utf-8') as f:
                    f.write(f"To: {s.email}\n")
                    f.write(f"Subject: {subject}\n")
                    f.write(f"Date: {datetime.datetime.now().isoformat()}\n\n")
                    f.write(body)
                out_count += 1
                try:
                    log = AuditLog(actor='system', action='notify_outbox', target=s.email)
                    db.add(log)
                    db.commit()
                except Exception:
                    db.rollback()
            except Exception as e:
                logger.error(f"Failed to write outbox for {s.email}: {e}")
                try:
                    log = AuditLog(actor='system', action='notify_outbox_failed', 
                                 target=f"{s.email}: {str(e)[:100]}")
                    db.add(log)
                    db.commit()
                except Exception:
                    db.rollback()
        
        result.update({'mode': 'outbox', 'outbox_written': out_count})
        db.close()
        return result

    # SMTP 模式：發送郵件
    sent_count = 0
    failures = []
    for s in subs:
        try:
            send_email(s.email, subject, body, smtp_cfg)
            sent_count += 1
            try:
                log = AuditLog(actor='system', action='notify_sent', target=s.email)
                db.add(log)
                db.commit()
            except Exception:
                db.rollback()
        except Exception as e:
            error_msg = str(e)[:100]
            failures.append(error_msg)
            logger.error(f"Failed to send email to {s.email}: {error_msg}")
            try:
                log = AuditLog(actor='system', action='notify_failed', 
                             target=f"{s.email}: {error_msg}")
                db.add(log)
                db.commit()
            except Exception:
                db.rollback()

    if sent_count > 0:
        try:
            notif = db.query(Notification).order_by(Notification.created_at.desc()).first()
            if notif:
                notif.sent = True
                db.commit()
        except Exception:
            db.rollback()

    result.update({'mode': 'smtp', 'sent_count': sent_count, 'failures': failures})
    db.close()
    return result

# ==============================================================================
# 其他輔助函式
# ==============================================================================
def hash_password(password: str, username: str) -> str:
    s = f"{password}|{username}|{APP_SECRET}"
    return hashlib.sha256(s.encode()).hexdigest()

def verify_password(stored: str, password: str, username: str) -> bool:
    if not stored:
        return False
    if len(stored) == 64 and all(c in '0123456789abcdef' for c in stored.lower()):
        return stored == hash_password(password, username)
    if stored == password:
        try:
            db = get_db()
            u = db.query(User).filter_by(username=username).first()
            if u:
                u.password = hash_password(password, username)
                db.commit()
            db.close()
        except Exception:
            pass
        return True
    return False

def get_watchlist(owner: str):
    db = get_db()
    result = db.query(Watchlist).filter_by(owner=owner).all()
    db.close()
    return result

def add_watchlist(owner: str, symbol: str):
    db = get_db()
    try:
        if not db.query(Watchlist).filter_by(owner=owner, symbol=symbol).first():
            db.add(Watchlist(owner=owner, symbol=symbol))
            db.add(AuditLog(actor=owner, action='add_watchlist', target=symbol))
            db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()

def remove_watchlist(owner: str, symbol: str):
    db = get_db()
    try:
        w = db.query(Watchlist).filter_by(owner=owner, symbol=symbol).first()
        if w:
            db.delete(w)
            db.add(AuditLog(actor=owner, action='remove_watchlist', target=symbol))
            db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()

def init_portfolio():
    db = get_db()
    try:
        p = db.query(PortfolioMeta).first()
        if not p:
            p = PortfolioMeta(initial_capital=10000.0, cash=10000.0)
            db.add(p)
            db.commit()
        db.close()
        return p
    except Exception:
        db.rollback()
        db.close()
        return None

def compute_portfolio_value():
    db = get_db()
    try:
        p = init_portfolio() or PortfolioMeta()
        holdings = db.query(ManagerHolding).filter(ManagerHolding.active == True).all()
        total = float(p.cash or 0.0)
        for h in holdings:
            price = get_latest_price(h.symbol) or 0.0
            total += (h.shares or 0.0) * price
        db.close()
        return total
    except Exception:
        db.close()
        return 0.0

def record_snapshot():
    db = get_db()
    try:
        value = compute_portfolio_value()
        db.add(PortfolioSnapshot(value=value))
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()

def process_buy(actor: str, symbol: str, shares: float, price: float = None):
    db = get_db()
    try:
        p = init_portfolio() or PortfolioMeta()
        if price is None:
            price = get_latest_price(symbol) or 0.0
        
        if price <= 0:
            raise ValueError(f"Invalid price for {symbol}: {price}")
        
        cost = price * shares
        if cost > (p.cash or 0.0):
            raise Exception(f"Insufficient cash: need {cost}, have {p.cash}")
        
        p.cash = (p.cash or 0.0) - cost
        h = db.query(ManagerHolding).filter_by(symbol=symbol, active=True).first()
        if h:
            new_shares = (h.shares or 0.0) + shares
            h.avg_price = ((h.avg_price or 0.0) * (h.shares or 0.0) + cost) / new_shares
            h.shares = new_shares
        else:
            db.add(ManagerHolding(symbol=symbol, shares=shares, avg_price=price))
        
        db.add(ManagerTransaction(actor=actor, action='buy', symbol=symbol, shares=shares, price=price))
        db.add(AuditLog(actor=actor, action='manager_buy', target=f"{symbol}:{shares}@{price}"))
        db.commit()
        db.close()
        
        record_snapshot()
        notif_result = notify_subscribers(f"管理員持股變動: {symbol}", 
                                         f"管理員 {actor} 執行 BUY {shares} 股，價格 {price}")
        return notif_result
    except Exception as e:
        db.rollback()
        db.close()
        raise

def process_sell(actor: str, symbol: str, shares: float, price: float = None):
    db = get_db()
    try:
        p = init_portfolio() or PortfolioMeta()
        if price is None:
            price = get_latest_price(symbol) or 0.0
        
        if price <= 0:
            raise ValueError(f"Invalid price for {symbol}: {price}")
        
        h = db.query(ManagerHolding).filter_by(symbol=symbol, active=True).first()
        if not h or (h.shares or 0.0) < shares:
            raise Exception(f"Insufficient shares: need {shares}, have {h.shares if h else 0}")
        
        proceed = price * shares
        p.cash = (p.cash or 0.0) + proceed
        h.shares = (h.shares or 0.0) - shares
        if h.shares <= 0:
            h.active = False
        
        db.add(ManagerTransaction(actor=actor, action='sell', symbol=symbol, shares=shares, price=price))
        db.add(AuditLog(actor=actor, action='manager_sell', target=f"{symbol}:{shares}@{price}"))
        db.commit()
        db.close()
        
        record_snapshot()
        notif_result = notify_subscribers(f"管理員持股變動: {symbol}", 
                                         f"管理員 {actor} 執行 SELL {shares} 股，價格 {price}")
        return notif_result
    except Exception as e:
        db.rollback()
        db.close()
        raise

def add_subscriber(email: str):
    db = get_db()
    try:
        if not db.query(Subscriber).filter_by(email=email).first():
            db.add(Subscriber(email=email))
            db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()

def create_invite_token(expires_hours: int = 72) -> str:
    db = get_db()
    try:
        token = uuid.uuid4().hex
        expires_at = datetime.datetime.now() + datetime.timedelta(hours=expires_hours)
        it = InviteToken(token=token, expires_at=expires_at)
        db.add(it)
        db.commit()
        db.close()
        return token
    except Exception:
        db.rollback()
        db.close()
        return ""

def validate_and_consume_invite(token: str):
    db = get_db()
    try:
        if not token:
            return None
        
        it = db.query(InviteToken).filter_by(token=token).first()
        if not it or it.used:
            db.close()
            return None
        
        if it.expires_at and datetime.datetime.now() > it.expires_at:
            db.close()
            return None

        for _ in range(5):
            uname = f"guest_{uuid.uuid4().hex[:6]}"
            if not db.query(User).filter_by(username=uname).first():
                break
        
        pwd = uuid.uuid4().hex[:12]
        pwd_h = hash_password(pwd, uname)
        db.add(User(username=uname, password=pwd_h, role='user'))
        it.used = True
        it.assigned_user = uname
        db.add(AuditLog(actor='system', action='invite_consumed', target=uname))
        db.commit()
        db.close()
        return uname
    except Exception:
        db.rollback()
        db.close()
        return None

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'

def make_shareable_link(invite_token: str = None, port: int = None) -> str:
    port = port or int(os.environ.get('STREAMLIT_SERVER_PORT') or os.environ.get('PORT') or 8503)
    host = get_local_ip()
    if invite_token:
        return f"http://{host}:{port}/?invite={invite_token}"
    return f"http://{host}:{port}/"

def compute_portfolio_metrics():
    db = get_db()
    try:
        p = init_portfolio() or PortfolioMeta()
        holdings = db.query(ManagerHolding).filter(ManagerHolding.active == True).all()
        current_value = compute_portfolio_value()
        initial = p.initial_capital or 0.0
        total_pnl = current_value - initial
        
        unrealized = 0.0
        for h in holdings:
            price = get_latest_price(h.symbol) or 0.0
            unrealized += (price - (h.avg_price or 0.0)) * (h.shares or 0.0)
        
        realized = total_pnl - unrealized
        db.close()
        
        return {
            'initial': initial,
            'current_value': current_value,
            'total_pnl': total_pnl,
            'total_return_pct': (current_value / initial - 1) * 100 if initial else 0.0,
            'realized': realized,
            'unrealized': unrealized,
        }
    except Exception:
        db.close()
        return {
            'initial': 0,
            'current_value': 0,
            'total_pnl': 0,
            'total_return_pct': 0,
            'realized': 0,
            'unrealized': 0,
        }

def settle_portfolio(actor: str):
    db = get_db()
    try:
        holdings = db.query(ManagerHolding).filter(ManagerHolding.active == True).all()
        summary = []
        for h in holdings:
            try:
                price = get_latest_price(h.symbol) or 0.0
                shares = h.shares or 0.0
                if shares > 0 and price > 0:
                    process_sell(actor, h.symbol, shares, price)
                    summary.append({'symbol': h.symbol, 'shares': shares, 'price': price})
            except Exception as e:
                logger.warning(f"Failed to sell {h.symbol}: {e}")
                continue
        
        db.close()
        record_snapshot()
        notify_subscribers(f"管理員結算完成 by {actor}", f"已清算 {len(summary)} 檔持股")
        return summary
    except Exception as e:
        db.close()
        logger.error(f"Settlement failed: {e}")
        raise

# ==============================================================================
# [STAGE 2] 量化引擎
# ==============================================================================
class HarryEngine:
    @staticmethod
    def get_indicators(df):
        """計算技術指標"""
        close = df['Close'].copy()
        
        # MACD
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        df['MACD_LINE'] = ema12 - ema26
        df['MACD_SIGNAL'] = df['MACD_LINE'].ewm(span=9, adjust=False).mean()
        df['MACD_HIST'] = (df['MACD_LINE'] - df['MACD_SIGNAL']) * 2
        
        # 25日乖離率
        df['MA25'] = close.rolling(window=25).mean()
        df['BIAS_25'] = ((close - df['MA25']) / df['MA25']) * 100
        
        # 布林通道
        df['MA20'] = close.rolling(window=20).mean()
        df['STD20'] = close.rolling(window=20).std()
        df['BB_UP'] = df['MA20'] + (df['STD20'] * 2)
        df['BB_LOW'] = df['MA20'] - (df['STD20'] * 2)
        
        return df

# ==============================================================================
# [STAGE 3] 財務資料牆
# ==============================================================================
def render_financial_wall(symbol):
    """渲染股票資訊牆"""
    db = get_db()
    
    # 檢查快取
    cache = db.query(FinancialCache).filter_by(symbol=symbol).first()
    use_cache = False
    if cache:
        age = datetime.datetime.now() - cache.fetched_at
        if age.total_seconds() < 60 * 60 * 24:
            use_cache = True

    if use_cache:
        logger.info(f"Using cached data for {symbol}")
        try:
            info = json.loads(cache.info_text) if cache.info_text else {}
        except:
            info = {}
        try:
            financials = pd.read_csv(StringIO(cache.financials_csv), index_col=0) if cache.financials_csv else pd.DataFrame()
        except:
            financials = pd.DataFrame()
        try:
            balance = pd.read_csv(StringIO(cache.balance_csv), index_col=0) if cache.balance_csv else pd.DataFrame()
        except:
            balance = pd.DataFrame()
        try:
            cashflow = pd.read_csv(StringIO(cache.cashflow_csv), index_col=0) if cache.cashflow_csv else pd.DataFrame()
        except:
            cashflow = pd.DataFrame()
        try:
            inst = pd.read_csv(StringIO(cache.institutional_csv)) if cache.institutional_csv else pd.DataFrame()
        except:
            inst = pd.DataFrame()
        try:
            major = pd.read_csv(StringIO(cache.major_csv)) if cache.major_csv else pd.DataFrame()
        except:
            major = pd.DataFrame()
    else:
        logger.info(f"Fetching fresh data for {symbol}")
        with st.spinner(f"正在取得 {symbol} 的資料..."):
            info, financials, balance, cashflow, inst, major = safe_ticker_fetch(symbol, retries=2, backoff=1.0)

        # 寫入快取
        try:
            if info or not financials.empty or not balance.empty or not cashflow.empty:
                if not cache:
                    cache = FinancialCache(symbol=symbol)
                    db.add(cache)
                cache.fetched_at = datetime.datetime.now()
                cache.info_text = json.dumps(info)
                cache.financials_csv = financials.to_csv() if not financials.empty else ''
                cache.balance_csv = balance.to_csv() if not balance.empty else ''
                cache.cashflow_csv = cashflow.to_csv() if not cashflow.empty else ''
                cache.institutional_csv = inst.to_csv(index=False) if not inst.empty else ''
                cache.major_csv = major.to_csv(index=False) if not major.empty else ''
                db.commit()
        except Exception as e:
            logger.error(f"Failed to cache data: {e}")
            db.rollback()

    db.close()

    st.markdown("## 🏢 企業核心檔案與營運摘要")
    company_name = info.get('shortName', info.get('longName', symbol))
    industry = info.get('industry', '未知')
    sector = info.get('sector', '未知')
    st.markdown(f"**{company_name}** — {industry} | {sector}")
    
    summary = info.get('longBusinessSummary', '無資料')
    if summary:
        st.info(summary[:500] + "..." if len(summary) > 500 else summary)

    # 價格與狀態
    price = get_latest_price(symbol)
    prev_close = info.get('previousClose') or info.get('regularMarketPreviousClose')
    change = None
    if price is not None and prev_close is not None:
        change = price - prev_close

    c_a, c_b = st.columns([1, 2])
    with c_a:
        st.metric("即時價格", f"{price if price is not None else 'N/A'}", 
                 delta=f"{change:.2f}" if change is not None else None)
    with c_b:
        if change is None:
            render_status_light("價格未知", color="#6b7280")
        else:
            color = "#10b981" if change >= 0 else "#ef4444"
            render_status_light("漲" if change >= 0 else "跌", color=color, blink=is_market_open())

    # 自選股
    try:
        current_user = st.session_state.user
    except:
        current_user = None
    
    if current_user:
        db = get_db()
        exists = db.query(Watchlist).filter_by(owner=current_user, symbol=symbol).first()
        db.close()
        
        if exists:
            if st.button("從自選移除"):
                remove_watchlist(current_user, symbol)
                st.rerun()
        else:
            if st.button("加入自選股"):
                add_watchlist(current_user, symbol)
                st.rerun()

    # 財務三表
    st.markdown("## 📄 財務三表深度解剖")
    tab_inc, tab_bal, tab_cas = st.tabs(["損益表", "資產負債表", "現金流量表"])

    with tab_inc:
        st.subheader("利潤與營收明細")
        if not financials.empty:
            st.dataframe(financials, use_container_width=True, height=500)
        else:
            st.info("無財務報表資料")

    with tab_bal:
        st.subheader("資產與負債配比")
        if not balance.empty:
            st.dataframe(balance, use_container_width=True, height=500)
        else:
            st.info("無資產負債表資料")

    with tab_cas:
        st.subheader("現金流向監控")
        if not cashflow.empty:
            st.dataframe(cashflow, use_container_width=True, height=500)
        else:
            st.info("無現金流量表資料")

    st.markdown("## 💎 法人籌碼與內部人監控")
    c1, c2 = st.columns(2)
    with c1:
        st.write("**機構投資人**")
        if not inst.empty:
            st.dataframe(inst, use_container_width=True)
        else:
            st.info("無機構投資人資料")
    with c2:
        st.write("**前十大持股**")
        if not major.empty:
            st.dataframe(major, use_container_width=True)
        else:
            st.info("無前十大持股資料")

    # 關鍵指標
    c3, c4, c5 = st.columns(3)
    with c3:
        st.metric("市值", f"{info.get('marketCap', 'N/A')}")
    with c4:
        st.metric("PE Ratio", f"{info.get('trailingPE', 'N/A')}")
    with c5:
        st.metric("營收", f"{info.get('totalRevenue', 'N/A')}")

# ==============================================================================
# [STAGE 4] 主介面
# ==============================================================================
def main():
    st.set_page_config(page_title="HARRY SUPREME TITAN V13", layout="wide")
    
    st.markdown("""<style>
        .stApp { background: linear-gradient(90deg,#05060a,#0a0e14); color: #d1d5db; }
        .stTabs [data-baseweb="tab-list"] { gap: 24px; }
        .stTabs [data-baseweb="tab"] { height: 50px; background-color: #1f2937; border-radius: 4px; padding: 0 20px; }
        .harry-header { font-size: 26px; font-weight:700; background: linear-gradient(90deg,#60a5fa,#a78bfa); -webkit-background-clip:text; color:transparent; }
        .harry-light { display:inline-block; border-radius:50%; box-shadow: 0 0 8px rgba(255,255,255,0.03); vertical-align:middle; }
        @keyframes harry-blinker { 0%{opacity:1} 50%{opacity:0.15; transform:scale(0.92);} 100%{opacity:1} }
        @keyframes harry-pulse { 0%{box-shadow:0 0 0 0 rgba(255,255,255,0)} 70%{box-shadow:0 0 12px 6px rgba(255,255,255,0.02);} 100%{box-shadow:0 0 0 0 rgba(255,255,255,0);} }
        @keyframes marquee { 0%{transform:translateX(0%)} 100%{transform:translateX(-100%)} }
    </style>""", unsafe_allow_html=True)

    if "logged" not in st.session_state:
        st.session_state.logged = False

    # 邀請連結登入
    try:
        params = st.query_params
        invite_token = params.get('invite', [None])[0] if isinstance(params, dict) else None
        if invite_token and not st.session_state.get('logged'):
            created_user = validate_and_consume_invite(invite_token)
            if created_user:
                st.session_state.logged = True
                st.session_state.user = created_user
                st.session_state.role = 'user'
                st.success(f"邀請連結自動登入為 {created_user}")
                st.rerun()
    except Exception as e:
        logger.warning(f"Invite link processing failed: {e}")

    # 側邊欄登入
    with st.sidebar:
        st.title("TITAN V13 FIXED")
        if not st.session_state.logged:
            st.subheader("🔐 系統認證")
            u = st.text_input("帳號")
            p = st.text_input("密鑰", type="password")
            if st.button("解鎖終端"):
                db = get_db()
                user = db.query(User).filter_by(username=u).first()
                db.close()
                
                if user and user.is_active and verify_password(user.password, p, u):
                    st.session_state.logged = True
                    st.session_state.user = u
                    st.session_state.role = user.role
                    st.success("登入成功")
                    st.rerun()
                else:
                    st.error("帳號或密碼錯誤")
            return
        else:
            st.success(f"登入身份: {st.session_state.user} [{st.session_state.role}]")
            
            if 'blink_speed' not in st.session_state:
                st.session_state.blink_speed = 1.0
            st.session_state.blink_speed = st.slider("閃爍速度", 0.2, 3.0, float(st.session_state.blink_speed), 0.1)
            
            menu = st.radio("功能導航", [
                "回首頁", 
                "股票資料中心", 
                "自選股",
                "管理員公告",
                "管理員績效",
                "管理員後台",
                "問題回報"
            ])
            
            if st.button("安全登出"):
                st.session_state.logged = False
                st.rerun()

    # 頁面渲染
    if menu == "回首頁":
        st.title("🏠 系統控制中心")
        now = tz_now()
        st.markdown(f"**台北時間**: {now.strftime('%Y-%m-%d %H:%M:%S')}")
        if is_market_open(now):
            render_status_light("市場開盤中", color="#10b981", blink=True)
        else:
            render_status_light("市場休市", color="#6b7280", blink=False)

        st.subheader("📢 系統公告")
        db = get_db()
        all_n = db.query(SystemNotice).order_by(SystemNotice.created_at.desc()).all()
        db.close()
        
        if all_n:
            for n in all_n:
                with st.expander(f"📌 {n.title} - {n.created_at.strftime('%Y-%m-%d')}"):
                    st.write(n.body)
        else:
            st.info("尚無公告")

    elif menu == "股票資料中心":
        st.title("📈 股票資料中心")
        cols = st.columns([3, 1])
        with cols[0]:
            q = st.text_input("搜尋台股代碼 (如 2330)", "2330").strip()
        with cols[1]:
            if st.button("查詢"):
                if q and q.isdigit():
                    q = q + ".TW"
                st.session_state._search_target = q.upper()
                st.rerun()

        target = st.session_state.get('_search_target', '2330.TW')
        render_financial_wall(target)
        
        st.divider()
        st.subheader("📊 技術圖表")
        try:
            with st.spinner(f"正在繪製 {target} 的圖表..."):
                hist = yf.Ticker(target).history(period="1y")
                if not hist.empty:
                    df = HarryEngine.get_indicators(hist)
                    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.02)
                    fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], 
                                                low=df['Low'], close=df['Close'], name="K棒"), row=1, col=1)
                    fig.add_trace(go.Bar(x=df.index, y=df['MACD_HIST'], name="MACD"), row=2, col=1)
                    fig.add_trace(go.Scatter(x=df.index, y=df['BIAS_25'], name="25日乖離"), row=3, col=1)
                    fig.update_layout(height=900, template="plotly_dark", xaxis_rangeslider_visible=False)
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.warning("無法取得歷史資料")
        except Exception as e:
            logger.error(f"Chart rendering error: {e}")
            st.error(f"圖表繪製失敗: {e}")

    elif menu == "自選股":
        st.title("⭐ 我的自選股")
        user = st.session_state.user
        wl = get_watchlist(user)
        
        st.write("新增自選股")
        ns = st.text_input("代碼 (如 2330.TW)", "")
        if st.button("加入自選") and ns:
            add_watchlist(user, ns.upper())
            st.rerun()

        if wl:
            for w in wl:
                cols = st.columns([4, 1, 1])
                cols[0].write(f"**{w.symbol}**")
                if cols[1].button("查看", key=f"w_{w.id}"):
                    st.session_state._search_target = w.symbol
                    st.rerun()
                if cols[2].button("刪除", key=f"wd_{w.id}"):
                    remove_watchlist(user, w.symbol)
                    st.rerun()
        else:
            st.info("尚無自選股")

    elif menu == "管理員公告":
        if st.session_state.role != "admin":
            st.error("權限不足")
        else:
            st.subheader("📣 發布公告")
            with st.form("new_notice"):
                nt = st.text_input("標題")
                nb = st.text_area("內容")
                if st.form_submit_button("發布"):
                    if nt and nb:
                        db = get_db()
                        try:
                            db.add(SystemNotice(title=nt, body=nb, author=st.session_state.user))
                            db.add(AuditLog(actor=st.session_state.user, action='create_notice', target=nt))
                            db.commit()
                            st.success("公告已發布")
                        except Exception as e:
                            db.rollback()
                            st.error(f"發布失敗: {e}")
                        finally:
                            db.close()
                    else:
                        st.warning("請輸入標題與內容")

            st.markdown("---")
            st.subheader("目前公告")
            db = get_db()
            notices = db.query(SystemNotice).order_by(SystemNotice.created_at.desc()).all()
            db.close()
            
            for n in notices:
                cols = st.columns([6, 1])
                with cols[0]:
                    st.write(f"**{n.title}** — {n.author} ({n.created_at.strftime('%Y-%m-%d')})")
                    st.write(n.body)
                with cols[1]:
                    if st.button("刪除", key=f"notice_del_{n.nid}"):
                        db = get_db()
                        try:
                            db.delete(db.query(SystemNotice).filter_by(nid=n.nid).first())
                            db.add(AuditLog(actor=st.session_state.user, action='delete_notice', target=n.title))
                            db.commit()
                        except Exception as e:
                            db.rollback()
                            st.error(f"刪除失敗: {e}")
                        finally:
                            db.close()
                        st.rerun()

    elif menu == "管理員績效":
        st.title("📊 管理員績效")
        metrics = compute_portfolio_metrics()
        st.metric("初始資金", f"{metrics['initial']:.2f}")
        st.metric("目前資產淨值", f"{metrics['current_value']:.2f}")
        st.metric("總報酬 (%)", f"{metrics['total_return_pct']:.2f}%")

        st.subheader("訂閱管理")
        sub_email = st.text_input("訂閱 Email")
        if st.button("訂閱") and sub_email:
            add_subscriber(sub_email)
            st.success("已訂閱")

        if st.session_state.role == 'admin':
            st.subheader("交易操作")
            with st.form("trade"):
                t_symbol = st.text_input("代碼", "2330.TW")
                t_action = st.selectbox("動作", ["buy", "sell"])
                t_shares = st.number_input("股數", 1.0)
                t_price = st.number_input("價格 (0=自動取得)", 0.0)
                
                if st.form_submit_button("送出"):
                    try:
                        price = float(t_price) if t_price > 0 else None
                        if t_action == 'buy':
                            notif = process_buy(st.session_state.user, t_symbol.upper(), float(t_shares), price)
                        else:
                            notif = process_sell(st.session_state.user, t_symbol.upper(), float(t_shares), price)
                        
                        if isinstance(notif, dict):
                            mode = notif.get('mode')
                            if mode == 'smtp':
                                st.success(f"已寄出通知給 {notif.get('sent_count', 0)} 位訂閱者")
                            elif mode == 'outbox':
                                st.info(f"已寫入 {notif.get('outbox_written', 0)} 封郵件到本地 outbox")
                        st.success("交易已紀錄")
                    except Exception as e:
                        st.error(f"交易失敗: {e}")

            if st.button("結算所有持股"):
                try:
                    summary = settle_portfolio(st.session_state.user)
                    st.success(f"已結算 {len(summary)} 檔")
                except Exception as e:
                    st.error(f"結算失敗: {e}")

        st.markdown("---")
        st.subheader("目前持股")
        db = get_db()
        holdings = db.query(ManagerHolding).filter(ManagerHolding.active == True).all()
        db.close()
        
        if holdings:
            rows = []
            for h in holdings:
                curp = get_latest_price(h.symbol) or 0.0
                unreal = (curp - (h.avg_price or 0.0)) * (h.shares or 0.0)
                rows.append({
                    "代碼": h.symbol,
                    "張數": h.shares,
                    "平均成本": h.avg_price,
                    "目前價": curp,
                    "未實現盈虧": unreal
                })
            st.dataframe(pd.DataFrame(rows))
        else:
            st.info("尚無持股")

    elif menu == "管理員後台":
        if st.session_state.role != "admin":
            st.error("權限不足")
        else:
            st.subheader("👥 帳號管理")
            with st.form("new_user"):
                nu = st.text_input("帳號名稱")
                np = st.text_input("密碼")
                nr = st.selectbox("權限", ["admin", "user"])
                if st.form_submit_button("建立帳號"):
                    db = get_db()
                    try:
                        if not nu:
                            st.warning("請輸入帳號名稱")
                        elif db.query(User).filter_by(username=nu).first():
                            st.warning("帳號已存在")
                        else:
                            pwd_h = hash_password(np, nu)
                            db.add(User(username=nu, password=pwd_h, role=nr))
                            db.add(AuditLog(actor=st.session_state.user, action="create_user", target=nu))
                            db.commit()
                            st.success(f"帳號 {nu} 已建立")
                    except Exception as e:
                        db.rollback()
                        st.error(f"建立失敗: {e}")
                    finally:
                        db.close()

            st.write("資料庫帳號：")
            db = get_db()
            users = db.query(User).all()
            db.close()
            
            if users:
                st.dataframe(pd.DataFrame([
                    {"ID": u.uid, "帳號": u.username, "權限": u.role, "啟用": u.is_active}
                    for u in users
                ]))

            st.markdown("---")
            st.subheader("SMTP 設定")
            smtp_cfg = load_smtp_config() or {}
            with st.form("smtp_form"):
                s_host = st.text_input("Host", smtp_cfg.get('host', ''))
                s_port = st.number_input("Port", int(smtp_cfg.get('port', 587)))
                s_user = st.text_input("Username", smtp_cfg.get('username', ''))
                s_pwd = st.text_input("Password", type='password')
                s_from = st.text_input("From", smtp_cfg.get('from', ''))
                if st.form_submit_button("儲存"):
                    cfg = {
                        'host': s_host,
                        'port': s_port,
                        'username': s_user,
                        'password': s_pwd or smtp_cfg.get('password', ''),
                        'from': s_from,
                        'tls': True
                    }
                    save_smtp_config(cfg)
                    st.success("已儲存")

            test_email = st.text_input("測試 Email")
            if st.button("寄送測試郵件"):
                cfg = load_smtp_config()
                if cfg and test_email:
                    try:
                        send_email(test_email, "測試郵件", "這是測試郵件", cfg)
                        st.success("已寄出")
                    except Exception as e:
                        st.error(f"寄送失敗: {e}")

            st.markdown("---")
            st.subheader("邀請連結")
            if st.button("產生邀請連結"):
                token = create_invite_token(72)
                link = make_shareable_link(token)
                st.code(link)

    elif menu == "問題回報":
        st.title("🛠 問題回報")
        with st.form("issue"):
            email = st.text_input("Email")
            desc = st.text_area("問題")
            if st.form_submit_button("送出"):
                if email and desc:
                    db = get_db()
                    try:
                        db.add(AuditLog(actor=email, action='issue', target=desc[:120]))
                        db.commit()
                        st.success("已送出")
                    except Exception:
                        db.rollback()
                    finally:
                        db.close()
                else:
                    st.warning("請填寫完整")

if __name__ == "__main__":
    db = get_db()
    if db.query(User).count() == 0:
        pwd_h = hash_password("123", "harry")
        db.add(User(username="harry", password=pwd_h, role="admin"))
        db.commit()
        logger.info("初始化超級管理員帳號: harry/123")
    db.close()
    main()
