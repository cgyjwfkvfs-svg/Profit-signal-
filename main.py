"""
╔══════════════════════════════════════════════════════════════════════════╗
║         SMC SIGNAL ENGINE  v5  — 2 SETUPS UNIQUEMENT                   ║
║                                                                          ║
║  SETUP 1 — SÉQUENCE SMC TRADER (Instagram) :                            ║
║    ① BOS    → confirme le biais (haussier/baissier)                    ║
║    ② SWEEP  → le prix chasse les stops sous/au-dessus d'un swing       ║
║               (bougie marquée "X" sur ses charts)                       ║
║    ③ MSS    → Market Structure Shift après le sweep                     ║
║    ④ FVG/OB → zone d'entrée dans le retracement                        ║
║    SL : sous/au-dessus de la bougie X (PAS juste sous l'OB)            ║
║    TP : prochaine liquidité BSL/SSL (swing H/L opposé)                  ║
║                                                                          ║
║  SETUP 2 — AMD H1 (Accumulation → Manipulation → Distribution) :        ║
║    ① ACCUMULATION : range comprimé sur H1                               ║
║    ② MANIPULATION : sweep du range high/low                             ║
║    ③ DISTRIBUTION : entrée FVG/OB dans le sens institutionnel           ║
║    SL : sous le low du sweep (manipulation candle)                      ║
║    TP : prochain BSL/SSL                                                 ║
║                                                                          ║
║  TIMEFRAMES :  H1 (AMD + biais)  →  30M (MSS/confirmation)             ║
║                →  15M (FVG/OB entrée)                                   ║
║                                                                          ║
║  MARCHÉS :  Gold · BTC · GER30 · US30 · NAS100 · Oil                  ║
║             EUR/USD · GBP/USD · USD/JPY · USD/CAD · USD/CHF            ║
║             AUD/USD · NZD/USD  + croisées principales                   ║
╚══════════════════════════════════════════════════════════════════════════╝

Installation :
    pip install yfinance pandas numpy colorama flask requests

Usage :
    python main-smc-v5.py                   # scan live (défaut)
    python main-smc-v5.py --cat priority    # Gold + BTC + Indices
    python main-smc-v5.py --cat forex       # Forex majeures
    python main-smc-v5.py --cat all         # Tout
    python main-smc-v5.py --symbol GC=F     # symbole unique
    python main-smc-v5.py --scan            # scan unique (test)
    python main-smc-v5.py --min-score 70    # filtre score
"""

import argparse
import threading
import time
import os
import requests
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional

import logging
import sys
import numpy as np
import pandas as pd
import yfinance as yf
from flask import Flask, jsonify

# ─────────────────────────────────────────────────────────────
#  LOGGING
# ─────────────────────────────────────────────────────────────
logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("smc")

# ─────────────────────────────────────────────────────────────
#  COLORAMA
# ─────────────────────────────────────────────────────────────
try:
    from colorama import Fore, Style, init as colorama_init
    colorama_init(autoreset=True)
    COLOR = True
except ImportError:
    COLOR = False

def c(text: str, color: str = "green") -> str:
    if not COLOR:
        return text
    colors = {
        "green": Fore.GREEN, "red": Fore.RED, "yellow": Fore.YELLOW,
        "cyan": Fore.CYAN, "white": Fore.WHITE, "magenta": Fore.MAGENTA,
        "blue": Fore.BLUE,
    }
    return colors.get(color, "") + text + Style.RESET_ALL


# ═════════════════════════════════════════════════════════════
#  CONFIGURATION
# ═════════════════════════════════════════════════════════════
HTF  = "1h"    # H1  — biais AMD + BOS principal
MTF  = "30m"   # 30M — MSS + confirmation structure
LTF  = "15m"   # 15M — FVG / OB entrée précise

SCORE_THRESHOLD = 70     # score minimum pour émettre un signal
MIN_RR          = 2.0    # ratio risque/récompense minimum
RISK_USD        = 25.0   # risque par trade en dollars

# AMD : fenêtre d'analyse en nombre de bougies H1
AMD_LOOKBACK = 40

# Liquidité : tolérance pour détecter un sweep (fraction de ATR)
SWEEP_ATR_RATIO = 0.03

# Limite signaux par symbole par jour
MAX_SIGNALS_PER_DAY = 3

# Intervalle de scan en secondes
SCAN_INTERVAL = 30

# ─────────────────────────────────────────────────────────────
#  SESSIONS ACTIVES (UTC)
# ─────────────────────────────────────────────────────────────
SESSION_WINDOWS_UTC: list[tuple[int, int]] = [
    (7,  11),   # London open
    (13, 17),   # NY open + overlap
]

def is_session_active() -> bool:
    hour = datetime.now(timezone.utc).hour
    return any(s <= hour < e for s, e in SESSION_WINDOWS_UTC)

def is_weekend() -> bool:
    return datetime.now(timezone.utc).weekday() >= 5

def is_crypto(symbol: str) -> bool:
    return symbol in ("BTC-USD", "ETH-USD")


# ─────────────────────────────────────────────────────────────
#  ATR MINIMUMS PAR INSTRUMENT (sur 15M)
# ─────────────────────────────────────────────────────────────
ATR_MIN: dict[str, float] = {
    "EURUSD=X": 0.00020, "GBPUSD=X": 0.00025, "USDJPY=X": 0.025,
    "USDCHF=X": 0.00020, "AUDUSD=X": 0.00018, "NZDUSD=X": 0.00016,
    "USDCAD=X": 0.00020, "GBPJPY=X": 0.040,   "EURJPY=X": 0.030,
    "GBPAUD=X": 0.00035, "GBPCAD=X": 0.00035, "GBPNZD=X": 0.00045,
    "EURGBP=X": 0.00015, "EURAUD=X": 0.00028, "EURCAD=X": 0.00028,
    "AUDJPY=X": 0.022,   "CADJPY=X": 0.022,   "CHFJPY=X": 0.025,
    "NZDJPY=X": 0.020,
    "GC=F"    : 2.00,    "SI=F"    : 0.06,
    "CL=F"    : 0.40,    "BZ=F"    : 0.40,
    "BTC-USD" : 100.0,
    "^GSPC"   : 8.0,     "^NDX"    : 25.0,    "^DJI"    : 80.0,
    "^GDAXI"  : 40.0,
}
ATR_MIN_DEFAULT = 0.00015

SPREAD_TABLE: dict[str, float] = {
    "EURUSD=X": 0.00008, "GBPUSD=X": 0.00010, "USDJPY=X": 0.009,
    "USDCHF=X": 0.00010, "AUDUSD=X": 0.00010, "NZDUSD=X": 0.00013,
    "USDCAD=X": 0.00012, "EURGBP=X": 0.00013, "EURJPY=X": 0.012,
    "EURAUD=X": 0.00020, "EURCAD=X": 0.00020, "EURNZD=X": 0.00025,
    "GBPJPY=X": 0.018,   "GBPAUD=X": 0.00025, "GBPCAD=X": 0.00025,
    "GBPNZD=X": 0.00030, "AUDJPY=X": 0.012,   "CADJPY=X": 0.015,
    "CHFJPY=X": 0.015,   "NZDJPY=X": 0.015,
    "GC=F"    : 0.30,    "SI=F"    : 0.015,
    "CL=F"    : 0.03,    "BZ=F"    : 0.04,
    "BTC-USD" : 15.0,
    "^GSPC"   : 0.30,    "^NDX"    : 0.50,    "^DJI"    : 2.00,
    "^GDAXI"  : 1.00,
}

def get_spread(symbol: str) -> float:
    return SPREAD_TABLE.get(symbol, 0.00015)

def check_volatility(symbol: str, df_ltf: pd.DataFrame) -> tuple[bool, str]:
    if df_ltf.empty or len(df_ltf) < 14:
        return False, "données insuffisantes"
    atr = (df_ltf["high"] - df_ltf["low"]).rolling(14).mean().iloc[-1]
    atr_min = ATR_MIN.get(symbol, ATR_MIN_DEFAULT)
    if atr < atr_min * 0.7:
        return False, f"ATR trop faible ({round(atr, 6)} < {round(atr_min*0.7, 6)})"
    spread = get_spread(symbol)
    ratio = spread / atr if atr > 0 else 1.0
    if ratio > 0.30:
        return False, f"spread/ATR={round(ratio*100,1)}% trop élevé"
    if is_crypto(symbol):
        return True, ""
    if is_weekend():
        return False, "weekend — marché fermé"
    if not is_session_active():
        return False, "hors session London/NY"
    return True, ""


# ─────────────────────────────────────────────────────────────
#  CORRÉLATION GUARD
# ─────────────────────────────────────────────────────────────
_CORR_GROUPS: dict[str, str] = {
    "EURUSD=X": "USD", "GBPUSD=X": "USD", "AUDUSD=X": "USD", "NZDUSD=X": "USD",
    "USDJPY=X": "USD", "USDCHF=X": "USD", "USDCAD=X": "USD",
    "GBPJPY=X": "JPY", "EURJPY=X": "JPY", "AUDJPY=X": "JPY",
    "CADJPY=X": "JPY", "CHFJPY=X": "JPY", "NZDJPY=X": "JPY",
    "GBPAUD=X": "GBP", "GBPCAD=X": "GBP", "GBPNZD=X": "GBP", "EURGBP=X": "GBP",
    "EURAUD=X": "EUR", "EURCAD=X": "EUR", "EURNZD=X": "EUR",
    "GC=F": "GOLD", "SI=F": "GOLD",
    "CL=F": "OIL",  "BZ=F": "OIL",
    "BTC-USD": "BTC",
    "^GSPC": "US_IDX", "^NDX": "US_IDX", "^DJI": "US_IDX",
    "^GDAXI": "EU_IDX",
}
_active_corr: dict[str, float] = {}
CORR_TTL = 900

def correlation_guard(symbol: str, direction: str) -> tuple[bool, str]:
    group = _CORR_GROUPS.get(symbol)
    if group is None:
        return True, ""
    key    = f"{group}:{direction}"
    now_ts = time.time()
    if key in _active_corr:
        if now_ts - _active_corr[key] > CORR_TTL:
            del _active_corr[key]
        else:
            return False, f"corrélation {group} {direction} active"
    _active_corr[key] = now_ts
    return True, ""

def correlation_guard_reset():
    _active_corr.clear()


# ─────────────────────────────────────────────────────────────
#  LIMITE JOURNALIÈRE PAR SYMBOLE
# ─────────────────────────────────────────────────────────────
_daily_counts: dict[str, int] = {}
_daily_date: str = ""

def _check_reset_daily():
    global _daily_date, _daily_counts
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if today != _daily_date:
        _daily_date   = today
        _daily_counts = {}

def check_daily_limit(symbol: str) -> bool:
    _check_reset_daily()
    return _daily_counts.get(symbol, 0) < MAX_SIGNALS_PER_DAY

def increment_daily_count(symbol: str):
    _check_reset_daily()
    _daily_counts[symbol] = _daily_counts.get(symbol, 0) + 1


# ═════════════════════════════════════════════════════════════
#  TELEGRAM
# ═════════════════════════════════════════════════════════════
_TG_TOKEN = os.environ.get("TG_TOKEN", "")
if not _TG_TOKEN:
    raise EnvironmentError(
        "Variable TG_TOKEN manquante.\n"
        "Définissez-la dans Render → Environment : TG_TOKEN=<votre_token>"
    )
TELEGRAM_TOKEN    = _TG_TOKEN
TELEGRAM_GROUP_ID = "-1002335466840"
TELEGRAM_CHAT_ID  = None

_setup_sent: dict[str, bool] = {}

def _setup_key(symbol: str, direction: str, score: int) -> str:
    return f"{symbol}:{direction}:{(score // 5) * 5}"

def is_setup_already_sent(symbol: str, direction: str, score: int) -> bool:
    return _setup_sent.get(_setup_key(symbol, direction, score), False)

def mark_setup_sent(symbol: str, direction: str, score: int):
    _setup_sent[_setup_key(symbol, direction, score)] = True

def reset_setup(symbol: str):
    for k in [k for k in _setup_sent if k.startswith(f"{symbol}:")]:
        del _setup_sent[k]

def _tg_url(method: str) -> str:
    return f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}"

def tg_send(text: str, chat_id: str) -> bool:
    try:
        r = requests.post(
            _tg_url("sendMessage"),
            json={"chat_id": chat_id, "text": text,
                  "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=10,
        )
        return r.status_code == 200
    except Exception as e:
        log.warning(f"[TG] Erreur : {e}")
        return False

def tg_get_chat_id() -> Optional[str]:
    global TELEGRAM_GROUP_ID
    try:
        r = requests.get(_tg_url("getUpdates"), timeout=10)
        updates = r.json().get("result", [])
        personal_id = None
        for upd in reversed(updates):
            msg = upd.get("message") or upd.get("channel_post", {})
            if not msg:
                continue
            chat = msg.get("chat", {})
            ctype = chat.get("type", "")
            cid = str(chat.get("id", ""))
            if ctype in ("group", "supergroup") and not TELEGRAM_GROUP_ID:
                TELEGRAM_GROUP_ID = cid
            elif ctype == "private" and not personal_id:
                personal_id = cid
        return personal_id
    except Exception:
        return None


def tg_format_signal(sig: "Signal") -> str:
    dec       = 2 if sig.entry > 100 else 5
    dir_emoji = "🔴 SHORT" if sig.direction == "SHORT" else "🟢 LONG"
    score_bar = "█" * (sig.score // 10) + "░" * (10 - sig.score // 10)
    rr_bar    = "⭐" * min(int(sig.rr), 5)
    ts        = sig.timestamp.strftime("%d/%m/%Y %H:%M UTC")
    risk_d    = round(abs(sig.entry - sig.sl), dec)
    gain_d    = round(abs(sig.tp - sig.entry), dec)
    gain_usd  = round(RISK_USD * sig.rr, 2)
    spread_d  = round(get_spread(sig.symbol), dec)

    if sig.mode == "SMC_TRADER":
        mode_badge = "★ SMC TRADER — BOS · Sweep(X) · MSS · FVG/OB"
        mode_color = "★"
    else:
        mode_badge = "🔮 AMD H1 — Accumulation · Manipulation · Distribution"
        mode_color = "🔮"

    msg = (
        f"<b>⚡ SMC SIGNAL v5  {mode_color}</b>\n"
        f"<b>{mode_badge}</b>\n"
        f"{'─'*32}\n"
        f"<b>Marché    :</b>  <code>{sig.symbol}</code>\n"
        f"<b>Direction :</b>  <b>{dir_emoji}</b>\n"
        f"<b>Biais H1  :</b>  {sig.htf_bias}\n"
        f"<b>TF        :</b>  H1 → 30M → 15M\n"
        f"{'─'*32}\n"
        f"<b>📍 Entrée      :</b>  <code>{sig.entry}</code>\n"
        f"<b>🔴 Stop Loss   :</b>  <code>{sig.sl}</code>  "
        f"<i>(bougie X  Δ={risk_d})</i>\n"
        f"<b>🟢 Take Profit :</b>  <code>{sig.tp}</code>  "
        f"<i>(liq. BSL/SSL  Δ={gain_d})</i>\n"
        f"<b>📊 Spread      :</b>  <code>{spread_d}</code>\n"
        f"<b>⚖  R : R net   :</b>  <b>1 : {sig.rr}</b>  {rr_bar}\n"
        f"{'─'*32}\n"
        f"<b>💰 LOT SIZE    :</b>  <b><code>{sig.lot} lot</code></b>\n"
        f"<b>⚠  Risque      :</b>  <b>${sig.risk_usd}</b>  →  gain ≈ <b>${gain_usd}</b>\n"
        f"{'─'*32}\n"
        f"<b>Score :</b>  [{score_bar}]  {sig.score}/100\n"
        f"<b>Confluence :</b>\n"
    )
    for r in sig.reasons:
        msg += f"  • {r}\n"
    msg += f"{'─'*32}\n<i>🕐 {ts}</i>"
    return msg


def tg_notify(sig: "Signal") -> None:
    global TELEGRAM_CHAT_ID
    if is_setup_already_sent(sig.symbol, sig.direction, sig.score):
        log.info(f"  [TG] ⏭ Setup déjà envoyé — {sig.symbol} {sig.direction}")
        return
    mark_setup_sent(sig.symbol, sig.direction, sig.score)

    if not TELEGRAM_CHAT_ID:
        TELEGRAM_CHAT_ID = tg_get_chat_id()

    msg = tg_format_signal(sig)
    if TELEGRAM_CHAT_ID:
        ok = tg_send(msg, TELEGRAM_CHAT_ID)
        log.info(f"  [TG] {'✓ DM' if ok else '✗ DM échoué'}")
    if TELEGRAM_GROUP_ID:
        ok_g = tg_send(msg, TELEGRAM_GROUP_ID)
        log.info(f"  [TG] {'✓ Groupe' if ok_g else '✗ Groupe échoué'}")


# ═════════════════════════════════════════════════════════════
#  DATA CLASSES
# ═════════════════════════════════════════════════════════════

@dataclass
class Signal:
    symbol:    str
    direction: str       # "LONG" | "SHORT"
    entry:     float
    sl:        float     # SL sous/au-dessus de la bougie X
    tp:        float     # TP = prochaine liquidité BSL/SSL
    rr:        float
    score:     int
    timestamp: datetime
    htf_bias:  str
    lot:       float = 0.0
    risk_usd:  float = RISK_USD
    mode:      str   = "SMC_TRADER"   # "SMC_TRADER" | "AMD"
    reasons:   list  = field(default_factory=list)


# ═════════════════════════════════════════════════════════════
#  HELPERS
# ═════════════════════════════════════════════════════════════

def fetch(symbol: str, interval: str, period: str = "5d",
          retries: int = 3, retry_delay: int = 15) -> pd.DataFrame:
    for attempt in range(1, retries + 1):
        try:
            try:
                df = yf.download(symbol, interval=interval, period=period,
                                 auto_adjust=True, progress=False,
                                 multi_level_index=False)
            except TypeError:
                df = yf.download(symbol, interval=interval, period=period,
                                 auto_adjust=True, progress=False)
            if df.empty:
                return df
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0).str.lower()
            else:
                df.columns = df.columns.str.lower()
            df.dropna(inplace=True)
            return df
        except Exception as e:
            err = str(e).lower()
            if ("rate" in err or "429" in err) and attempt < retries:
                time.sleep(retry_delay * attempt)
                continue
            return pd.DataFrame()
    return pd.DataFrame()


def compute_lot(symbol: str, entry: float, sl: float,
                risk_usd: float = RISK_USD) -> float:
    sl_dist = abs(entry - sl)
    if sl_dist == 0:
        return 0.0
    sym = symbol.upper().replace("=X", "").replace("-", "").replace("^", "")
    if symbol == "GC=F":
        lot = risk_usd / (sl_dist * 100.0)
    elif symbol == "SI=F":
        lot = risk_usd / (sl_dist * 50.0)
    elif symbol in ("CL=F", "BZ=F"):
        lot = risk_usd / (sl_dist * 1000.0)
    elif is_crypto(symbol):
        return round(risk_usd / sl_dist, 6)
    elif sym in ("GSPC", "NDX", "DJI", "GDAXI"):
        lot = risk_usd / (sl_dist * 10.0)
    elif sym.endswith("JPY"):
        sl_pips = sl_dist / 0.01
        pip_val = 1000.0 / entry
        lot = risk_usd / (sl_pips * pip_val)
    elif sym.startswith("USD"):
        sl_pips = sl_dist / 0.0001
        pip_val = 10.0 / entry
        lot = risk_usd / (sl_pips * pip_val)
    else:
        sl_pips = sl_dist / 0.0001
        lot = risk_usd / (sl_pips * 10.0)
    return max(0.01, round(lot, 2))


def swing_highs(df: pd.DataFrame) -> list[tuple[int, float]]:
    result = []
    for i in range(1, len(df) - 1):
        if df["high"].iloc[i] > df["high"].iloc[i-1] and df["high"].iloc[i] > df["high"].iloc[i+1]:
            result.append((i, df["high"].iloc[i]))
    return result

def swing_lows(df: pd.DataFrame) -> list[tuple[int, float]]:
    result = []
    for i in range(1, len(df) - 1):
        if df["low"].iloc[i] < df["low"].iloc[i-1] and df["low"].iloc[i] < df["low"].iloc[i+1]:
            result.append((i, df["low"].iloc[i]))
    return result


# ═════════════════════════════════════════════════════════════
#  DÉTECTEURS DE BASE
# ═════════════════════════════════════════════════════════════

def detect_bos(df: pd.DataFrame, lookback: int = 10) -> list[dict]:
    """Break Of Structure — cassure d'un swing H/L sur `lookback` bougies."""
    bos_list = []
    for i in range(lookback, len(df)):
        window     = df.iloc[i - lookback:i]
        close      = df["close"].iloc[i]
        swing_low  = window["low"].min()
        swing_high = window["high"].max()
        if close < swing_low:
            bos_list.append({"index": i, "type": "bearish", "level": swing_low})
        elif close > swing_high:
            bos_list.append({"index": i, "type": "bullish", "level": swing_high})
    return bos_list


def detect_fvg(df: pd.DataFrame) -> list[dict]:
    """Fair Value Gap — déséquilibre entre bougie[i-2] et bougie[i]."""
    fvgs = []
    for i in range(2, len(df)):
        h0 = df["high"].iloc[i-2]
        l0 = df["low"].iloc[i-2]
        h2 = df["high"].iloc[i]
        l2 = df["low"].iloc[i]
        # FVG haussier : low[i] > high[i-2]
        if l2 > h0:
            fvgs.append({"direction": "bullish", "top": l2, "bottom": h0, "index": i})
        # FVG baissier : high[i] < low[i-2]
        elif h2 < l0:
            fvgs.append({"direction": "bearish", "top": l0, "bottom": h2, "index": i})
    return fvgs


def detect_ob(df: pd.DataFrame, bos_list: list[dict]) -> list[dict]:
    """
    Order Block : dernière bougie OPPOSÉE avant un BOS.
    Ex : dernière bougie haussière avant un BOS bearish = Supply OB.
    """
    obs = []
    for bos in bos_list:
        idx = bos["index"]
        bos_type = bos["type"]
        for j in range(idx - 1, max(0, idx - 8), -1):
            o  = df["open"].iloc[j]
            cl = df["close"].iloc[j]
            h  = df["high"].iloc[j]
            l  = df["low"].iloc[j]
            if bos_type == "bearish" and cl > o:   # dernière haussière → Supply OB
                obs.append({"direction": "bearish", "top": h, "bottom": l, "index": j})
                break
            elif bos_type == "bullish" and cl < o: # dernière baissière → Demand OB
                obs.append({"direction": "bullish", "top": h, "bottom": l, "index": j})
                break
    return obs


def active_fvg_in_direction(df: pd.DataFrame, fvgs: list[dict], direction: str) -> Optional[dict]:
    """Retourne le FVG le plus récent dans la direction, encore actif (non mitiqué)."""
    price = df["close"].iloc[-1]
    for fvg in reversed(fvgs):
        if fvg["direction"] != direction:
            continue
        lo = min(fvg["top"], fvg["bottom"])
        hi = max(fvg["top"], fvg["bottom"])
        if lo <= price <= hi:
            return fvg
    return None


def htf_bias(df: pd.DataFrame) -> str:
    """Biais via EMA8 + structure HH/HL ou LH/LL."""
    if len(df) < 20:
        return "NEUTRAL"
    closes = df["close"].iloc[-20:].values
    ema    = np.convolve(closes, np.ones(8) / 8, mode="valid")
    highs  = df["high"].iloc[-20:].values
    trend_up = closes[-1] > ema[-1]
    last_hh  = highs[-1] < highs[-5:].max()
    if trend_up and not last_hh:
        return "BULLISH"
    if not trend_up and last_hh:
        return "BEARISH"
    return "NEUTRAL"


def next_liquidity_target(df_htf: pd.DataFrame, direction: str, price_now: float) -> float:
    """
    Prochaine liquidité institutionnelle :
    LONG  → prochain swing HIGH non cassé au-dessus du prix (BSL)
    SHORT → prochain swing LOW non cassé en-dessous du prix (SSL)
    """
    dec = 2 if price_now > 100 else 5
    window = df_htf.iloc[-40:]
    if direction == "LONG":
        cands = [
            window["high"].iloc[k]
            for k in range(1, len(window) - 1)
            if window["high"].iloc[k] > window["high"].iloc[k-1]
            and window["high"].iloc[k] > window["high"].iloc[k+1]
            and window["high"].iloc[k] > price_now
        ]
        return round(min(cands), dec) if cands else round(window["high"].max(), dec)
    else:
        cands = [
            window["low"].iloc[k]
            for k in range(1, len(window) - 1)
            if window["low"].iloc[k] < window["low"].iloc[k-1]
            and window["low"].iloc[k] < window["low"].iloc[k+1]
            and window["low"].iloc[k] < price_now
        ]
        return round(max(cands), dec) if cands else round(window["low"].min(), dec)


# ═════════════════════════════════════════════════════════════
#  SETUP 1 — SÉQUENCE SMC TRADER
#  BOS → Sweep(X) → MSS → FVG/OB
# ═════════════════════════════════════════════════════════════

@dataclass
class SmcTraderResult:
    detected:      bool
    direction:     str
    sweep_low:     float   # low de la bougie X → SL LONG
    sweep_high:    float   # high de la bougie X → SL SHORT
    mss_level:     float   # niveau du MSS confirmé
    entry_top:     float   # haut de la zone FVG/OB
    entry_bottom:  float   # bas de la zone FVG/OB
    tp_liquidity:  float   # cible : prochaine BSL/SSL
    score:         int
    reasons:       list


def detect_smc_trader(
    df_h1:  pd.DataFrame,   # H1  — BOS biais
    df_30m: pd.DataFrame,   # 30M — MSS
    df_15m: pd.DataFrame,   # 15M — FVG/OB entrée
    direction: str,         # "LONG" | "SHORT"
) -> SmcTraderResult:
    """
    Détecte la séquence complète Smc Trader :
    ① BOS H1 → ② Sweep (X) → ③ MSS 30M → ④ FVG/OB 15M

    SL  : sous le LOW de la bougie sweep pour LONG
           au-dessus du HIGH de la bougie sweep pour SHORT
    TP  : prochaine liquidité BSL (LONG) ou SSL (SHORT)
    """
    empty = SmcTraderResult(False, direction, 0, 0, 0, 0, 0, 0, 0, [])

    if len(df_h1) < 20 or len(df_30m) < 15 or len(df_15m) < 10:
        return empty

    atr_h1  = (df_h1["high"] - df_h1["low"]).rolling(14).mean().iloc[-1]
    atr_15m = (df_15m["high"] - df_15m["low"]).rolling(14).mean().iloc[-1]
    if pd.isna(atr_h1) or atr_h1 == 0:
        return empty

    price_now = df_15m["close"].iloc[-1]
    bos_type  = "bullish" if direction == "LONG" else "bearish"
    reasons   = []
    score     = 0

    # ── ① BOS H1 — biais confirmé ─────────────────────────────
    bos_h1 = detect_bos(df_h1, lookback=10)
    recent_bos = [b for b in bos_h1[-6:] if b["type"] == bos_type]
    if not recent_bos:
        return empty
    score += 15
    reasons.append(f"✅ BOS {bos_type.upper()} H1 confirmé → biais {direction}  (+15)")

    # ── ② SWEEP de liquidité — bougie X ──────────────────────
    # On cherche dans les 20 dernières bougies H1 un spike qui
    # dépasse un swing H/L précédent puis clôture de retour
    sweep_found = False
    sweep_idx   = -1
    sweep_low   = 0.0
    sweep_high  = 0.0

    for i in range(-20, -1):
        abs_i = len(df_h1) + i
        if abs_i < 12:
            continue
        lookback = df_h1.iloc[abs_i - 12: abs_i]
        if len(lookback) < 5:
            continue
        h  = df_h1["high"].iloc[i]
        l  = df_h1["low"].iloc[i]
        cl = df_h1["close"].iloc[i]

        if direction == "LONG":
            prev_low = lookback["low"].min()
            # Spike sous le swing low → clôture au-dessus
            if l < prev_low - atr_h1 * SWEEP_ATR_RATIO and cl > prev_low:
                sweep_found = True
                sweep_idx   = abs_i
                sweep_low   = l   # ← ancre du SL
                sweep_high  = h
                break
        else:
            prev_high = lookback["high"].max()
            # Spike au-dessus du swing high → clôture en-dessous
            if h > prev_high + atr_h1 * SWEEP_ATR_RATIO and cl < prev_high:
                sweep_found = True
                sweep_idx   = abs_i
                sweep_low   = l
                sweep_high  = h   # ← ancre du SL
                break

    if not sweep_found:
        return empty

    score += 25
    sweep_type = "SSL sweep (bas)" if direction == "LONG" else "BSL sweep (haut)"
    sl_anchor  = sweep_low if direction == "LONG" else sweep_high
    reasons.append(
        f"🔥 {sweep_type} — bougie X @ {round(sl_anchor, 2 if price_now > 100 else 5)}"
        f"  → SL anchor  (+25)"
    )

    # ── ③ MSS — Market Structure Shift (30M) ─────────────────
    # Après le sweep, on attend le premier BOS dans le BON sens sur 30M
    bos_30m = detect_bos(df_30m, lookback=8)
    mss_candidates = [b for b in bos_30m[-8:] if b["type"] == bos_type]
    if not mss_candidates:
        return empty

    mss = mss_candidates[-1]
    score += 20
    reasons.append(
        f"📐 MSS confirmé 30M — BOS {bos_type} @ {round(mss['level'], 2 if price_now > 100 else 5)}"
        f"  (+20)"
    )

    # ── ④ FVG ou OB 15M — zone d'entrée ──────────────────────
    fvgs_15m  = detect_fvg(df_15m)
    bos_15m   = detect_bos(df_15m, lookback=6)
    obs_15m   = detect_ob(df_15m, bos_15m)

    entry_top    = 0.0
    entry_bottom = 0.0
    zone_type    = ""

    # Cherche FVG actif
    fvg_active = active_fvg_in_direction(df_15m, fvgs_15m, bos_type)
    if fvg_active:
        entry_top    = max(fvg_active["top"], fvg_active["bottom"])
        entry_bottom = min(fvg_active["top"], fvg_active["bottom"])
        zone_type    = "FVG"
        score += 15
        reasons.append(
            f"📍 FVG 15M actif [{round(entry_bottom, 5)} — {round(entry_top, 5)}]  (+15)"
        )

    if not zone_type:
        # Cherche OB dans le bon sens
        ob_match = next((o for o in reversed(obs_15m) if o["direction"] == bos_type), None)
        if ob_match:
            entry_top    = ob_match["top"]
            entry_bottom = ob_match["bottom"]
            zone_type    = "OB"
            score += 12
            reasons.append(
                f"🧱 Order Block 15M [{round(entry_bottom, 5)} — {round(entry_top, 5)}]  (+12)"
            )

    if not zone_type:
        # Pas de FVG/OB → signal moins fort mais on continue
        entry_top    = price_now + atr_15m * 0.3
        entry_bottom = price_now - atr_15m * 0.3
        zone_type    = "MARCHE"
        score += 5
        reasons.append("⚠️ Entrée au marché (pas de FVG/OB identifié)  (+5)")

    # ── TP — prochaine liquidité BSL/SSL ──────────────────────
    tp_liq = next_liquidity_target(df_h1, direction, price_now)
    reasons.append(
        f"🎯 TP → Liquidité {'BSL' if direction=='LONG' else 'SSL'} "
        f"@ {round(tp_liq, 2 if price_now > 100 else 5)}"
    )

    return SmcTraderResult(
        detected=True,
        direction=direction,
        sweep_low=sweep_low,
        sweep_high=sweep_high,
        mss_level=mss["level"],
        entry_top=entry_top,
        entry_bottom=entry_bottom,
        tp_liquidity=tp_liq,
        score=score,
        reasons=reasons,
    )


# ═════════════════════════════════════════════════════════════
#  SETUP 2 — AMD H1
#  Accumulation → Manipulation → Distribution
# ═════════════════════════════════════════════════════════════

@dataclass
class AmdResult:
    detected:      bool
    direction:     str
    sweep_low:     float   # low de la manipulation → SL LONG
    sweep_high:    float   # high de la manipulation → SL SHORT
    range_high:    float
    range_low:     float
    entry_top:     float
    entry_bottom:  float
    tp_liquidity:  float
    confidence:    int
    score:         int
    reasons:       list


def detect_amd_h1(
    df_h1:  pd.DataFrame,
    df_15m: pd.DataFrame,
    direction: str,
) -> AmdResult:
    """
    Détecte le pattern AMD sur H1 :

    ACCUMULATION  = range comprimé (ATR faible) sur les 20-30 dernières bougies H1
    MANIPULATION  = spike hors du range (chasse les stops) puis retour dedans
                    → bougie "X" dont le low/high est l'ancre du SL
    DISTRIBUTION  = mouvement directionnel après la manipulation
                    → on entre sur FVG/OB 15M dans le sens institutionnel

    SL  : sous le low de la bougie manipulation pour LONG
           au-dessus du high pour SHORT
    TP  : prochaine liquidité BSL/SSL sur H1
    """
    empty = AmdResult(False, direction, 0, 0, 0, 0, 0, 0, 0, 0, 0, [])

    if len(df_h1) < AMD_LOOKBACK + 5 or len(df_15m) < 10:
        return empty

    atr_full = (df_h1["high"] - df_h1["low"]).rolling(14).mean()
    atr_now  = atr_full.iloc[-1]
    if pd.isna(atr_now) or atr_now == 0:
        return empty

    price_now = df_15m["close"].iloc[-1]
    reasons   = []
    score     = 0

    window        = df_h1.iloc[-AMD_LOOKBACK:]
    range_window  = window.iloc[:25]    # zone d'accumulation
    recent_window = window.iloc[25:]    # zone manipulation + distribution

    range_high = range_window["high"].quantile(0.80)
    range_low  = range_window["low"].quantile(0.20)
    range_size = range_high - range_low

    if range_size <= 0:
        return empty

    # ── Compression ATR (signature accumulation) ──────────────
    atr_range  = (range_window["high"] - range_window["low"]).mean()
    compressed = atr_range < atr_now * 0.85

    # ── Détection Sweep / Manipulation ────────────────────────
    sweep_found  = False
    sweep_candle = None

    for i in range(len(recent_window) - 1, max(len(recent_window) - 10, 0), -1):
        h  = recent_window["high"].iloc[i]
        l  = recent_window["low"].iloc[i]
        cl = recent_window["close"].iloc[i]

        if direction == "LONG":
            # Bull manipulation : spike sous range_low, clôture au-dessus
            if l < range_low - atr_now * 0.08 and cl > range_low:
                sweep_found  = True
                sweep_candle = {"low": l, "high": h, "close": cl}
                break
        else:
            # Bear manipulation : spike au-dessus range_high, clôture en-dessous
            if h > range_high + atr_now * 0.08 and cl < range_high:
                sweep_found  = True
                sweep_candle = {"low": l, "high": h, "close": cl}
                break

    if not sweep_found or sweep_candle is None:
        return empty

    # ── Scoring AMD ──────────────────────────────────────────
    score += 15
    reasons.append(f"📦 Accumulation H1 identifiée — range [{round(range_low,5)}–{round(range_high,5)}]  (+15)")

    if compressed:
        score += 10
        reasons.append("📊 ATR comprimé = accumulation institutionnelle authentique  (+10)")

    if range_size > atr_now * 1.5:
        score += 10
        reasons.append(f"📦 Range bien défini ({round(range_size, 5)})  (+10)")

    score += 25
    manip_type = "Bull (sweep bas)" if direction == "LONG" else "Bear (sweep haut)"
    sl_anchor  = sweep_candle["low"] if direction == "LONG" else sweep_candle["high"]
    reasons.append(
        f"🔥 Manipulation AMD {manip_type} @ {round(sl_anchor, 2 if price_now > 100 else 5)}"
        f"  → SL anchor  (+25)"
    )

    # ── Post-sweep : impulsion de distribution ? ──────────────
    last_o  = df_h1["open"].iloc[-1]
    last_cl = df_h1["close"].iloc[-1]
    impulse = abs(last_cl - last_o) > atr_now * 0.7
    if impulse:
        score += 10
        reasons.append("⚡ Impulsion de distribution détectée  (+10)")

    # ── Confirmation MSS 30M ──────────────────────────────────
    # (même logique que Smc Trader : on attend un BOS dans le bon sens)
    bos_type = "bullish" if direction == "LONG" else "bearish"
    bos_15m  = detect_bos(df_15m, lookback=6)
    recent_mss = [b for b in bos_15m[-5:] if b["type"] == bos_type]
    if recent_mss:
        score += 10
        reasons.append(f"📐 MSS 15M confirmé (BOS {bos_type})  (+10)")

    # ── Zone d'entrée FVG/OB 15M ─────────────────────────────
    fvgs_15m = detect_fvg(df_15m)
    ob_15m   = detect_ob(df_15m, bos_15m)

    entry_top    = 0.0
    entry_bottom = 0.0

    fvg_active = active_fvg_in_direction(df_15m, fvgs_15m, bos_type)
    if fvg_active:
        entry_top    = max(fvg_active["top"], fvg_active["bottom"])
        entry_bottom = min(fvg_active["top"], fvg_active["bottom"])
        score += 15
        reasons.append(
            f"📍 FVG 15M actif [{round(entry_bottom, 5)} — {round(entry_top, 5)}]  (+15)"
        )
    else:
        ob_match = next((o for o in reversed(ob_15m) if o["direction"] == bos_type), None)
        if ob_match:
            entry_top    = ob_match["top"]
            entry_bottom = ob_match["bottom"]
            score += 12
            reasons.append(
                f"🧱 OB 15M [{round(entry_bottom, 5)} — {round(entry_top, 5)}]  (+12)"
            )
        else:
            atr_15m = (df_15m["high"] - df_15m["low"]).rolling(14).mean().iloc[-1]
            entry_top    = price_now + atr_15m * 0.3
            entry_bottom = price_now - atr_15m * 0.3
            score += 5
            reasons.append("⚠️ Entrée au marché (pas de FVG/OB)  (+5)")

    # ── TP — prochaine liquidité BSL/SSL ─────────────────────
    tp_liq = next_liquidity_target(df_h1, direction, price_now)
    reasons.append(
        f"🎯 TP → Liquidité {'BSL' if direction=='LONG' else 'SSL'} "
        f"@ {round(tp_liq, 2 if price_now > 100 else 5)}"
    )

    return AmdResult(
        detected=True,
        direction=direction,
        sweep_low=sweep_candle["low"],
        sweep_high=sweep_candle["high"],
        range_high=range_high,
        range_low=range_low,
        entry_top=entry_top,
        entry_bottom=entry_bottom,
        tp_liquidity=tp_liq,
        confidence=min(score, 100),
        score=min(score, 100),
        reasons=reasons,
    )


# ═════════════════════════════════════════════════════════════
#  CALCUL ENTRY / SL / TP
# ═════════════════════════════════════════════════════════════

def compute_levels(
    price_now: float,
    direction: str,
    sweep_low: float,
    sweep_high: float,
    entry_top: float,
    entry_bottom: float,
    tp_liquidity: float,
    symbol: str,
    df_fallback: pd.DataFrame,
) -> tuple[float, float, float, float]:
    """
    Calcule entry / SL / TP / RR pour les 2 setups.

    SL MÉTHODE SMC TRADER :
      LONG  → sous le LOW de la bougie sweep (X) - buffer
      SHORT → au-dessus du HIGH de la bougie sweep (X) + buffer

    TP → prochaine liquidité BSL/SSL
    """
    atr = (df_fallback["high"] - df_fallback["low"]).rolling(14).mean().iloc[-1]
    spread = get_spread(symbol)
    dec = 2 if price_now > 100 else 5
    buf = max(atr * 0.25, spread * 2.0)

    # ── ENTRÉE ────────────────────────────────────────────────
    if entry_top > 0 and entry_bottom > 0:
        entry = round((entry_top + entry_bottom) / 2, dec)
    else:
        entry = round(price_now, dec)

    # ── SL — SOUS/AU-DESSUS DE LA BOUGIE X ──────────────────
    if direction == "LONG":
        sl = round(sweep_low - buf, dec)
    else:
        sl = round(sweep_high + buf, dec)

    risk = abs(entry - sl)
    if risk <= 0:
        return entry, sl, entry, 0.0

    # ── TP — LIQUIDITÉ BSL/SSL ────────────────────────────────
    tp = tp_liquidity
    if direction == "LONG" and (tp <= entry or tp <= entry + risk):
        # fallback : ATR × 4
        tp = round(entry + atr * 4, dec)
    elif direction == "SHORT" and (tp >= entry or tp >= entry - risk):
        tp = round(entry - atr * 4, dec)
    tp = round(tp, dec)

    # ── R:R net ───────────────────────────────────────────────
    gain = (tp - entry - spread) if direction == "LONG" else (entry - tp - spread)
    rr   = round(gain / risk, 2) if gain > 0 and risk > 0 else 0.0
    return entry, sl, tp, rr


# ═════════════════════════════════════════════════════════════
#  MOTEUR PRINCIPAL — analyse un symbole
# ═════════════════════════════════════════════════════════════

def analyse(symbol: str, htf: str = HTF, mtf: str = MTF, ltf: str = LTF,
            silent: bool = False) -> Optional[Signal]:

    if not silent:
        print(f"\n{c('═'*60, 'cyan')}")
        print(f"  {c('SMC v5', 'yellow')}  {c(symbol, 'white')}  "
              f"{c(datetime.now(timezone.utc).strftime('%H:%M UTC'), 'cyan')}")
        print(f"  {c('H1 → 30M → 15M  |  SMC_TRADER + AMD', 'cyan')}")
        print(c("═" * 60, "cyan"))

    # ── Données ──────────────────────────────────────────────
    df_h1  = fetch(symbol, htf, period="15d")   # H1  = 15j
    df_30m = fetch(symbol, mtf, period="7d")    # 30M = 7j
    df_15m = fetch(symbol, ltf, period="4d")    # 15M = 4j

    if df_h1.empty or df_30m.empty or df_15m.empty:
        if not silent:
            print(c("  ✗ Données indisponibles.", "red"))
        return None

    # ── Filtre volatilité + session ───────────────────────────
    vol_ok, vol_reason = check_volatility(symbol, df_15m)
    if not vol_ok:
        if not silent:
            print(c(f"  ⛔ {vol_reason}", "yellow"))
        return None

    # ── Biais H1 ──────────────────────────────────────────────
    bias      = htf_bias(df_h1)
    direction = "SHORT" if bias == "BEARISH" else ("LONG" if bias == "BULLISH" else None)

    if not silent:
        col = "red" if bias == "BEARISH" else ("green" if bias == "BULLISH" else "yellow")
        print(f"\n  {'Biais H1':<28} {c(bias, col)}")

    if direction is None:
        if not silent:
            print(c("  ✗ Biais NEUTRAL — ignoré.", "yellow"))
        return None

    price_now = df_15m["close"].iloc[-1]

    # ═══════════════════════════════════════════════════════════
    #  SETUP 1 — SÉQUENCE SMC TRADER
    # ═══════════════════════════════════════════════════════════
    smc = detect_smc_trader(df_h1, df_30m, df_15m, direction)

    if not silent:
        if smc.detected:
            print(f"  {'★ Séquence Smc Trader':<28} {c('✓ COMPLÈTE', 'green')}  score={smc.score}")
            sl_ref = smc.sweep_low if direction == "LONG" else smc.sweep_high
            print(f"    └ Bougie X (SL anchor) : {c(str(round(sl_ref, 5)), 'red')}")
            print(f"    └ MSS @ {round(smc.mss_level, 5)}")
            print(f"    └ TP liquidité @ {c(str(round(smc.tp_liquidity, 2 if price_now > 100 else 5)), 'green')}")
        else:
            print(f"  {'★ Séquence Smc Trader':<28} {c('✗ Incomplète', 'yellow')}")

    # ═══════════════════════════════════════════════════════════
    #  SETUP 2 — AMD H1
    # ═══════════════════════════════════════════════════════════
    amd = detect_amd_h1(df_h1, df_15m, direction)

    if not silent:
        if amd.detected:
            print(f"  {'🔮 AMD H1':<28} {c('✓ DÉTECTÉ', 'green')}  score={amd.score}")
            sl_ref = amd.sweep_low if direction == "LONG" else amd.sweep_high
            print(f"    └ Manipulation (SL anchor) : {c(str(round(sl_ref, 5)), 'red')}")
        else:
            print(f"  {'🔮 AMD H1':<28} {c('✗ Non détecté', 'yellow')}")

    # ── Sélection du meilleur setup ───────────────────────────
    # Si les deux sont détectés, on prend celui avec le score le plus élevé
    # Si un seul, on le prend
    # Si aucun, on rejette
    if not smc.detected and not amd.detected:
        if not silent:
            print(c("\n  ✗ Aucun setup validé.", "yellow"))
        return None

    if smc.detected and amd.detected:
        use_smc = smc.score >= amd.score
    elif smc.detected:
        use_smc = True
    else:
        use_smc = False

    if use_smc:
        setup      = smc
        mode       = "SMC_TRADER"
        sweep_low  = smc.sweep_low
        sweep_high = smc.sweep_high
        entry_top  = smc.entry_top
        entry_bot  = smc.entry_bottom
        tp_liq     = smc.tp_liquidity
        raw_score  = smc.score
        reasons    = smc.reasons
    else:
        setup      = amd
        mode       = "AMD"
        sweep_low  = amd.sweep_low
        sweep_high = amd.sweep_high
        entry_top  = amd.entry_top
        entry_bot  = amd.entry_bottom
        tp_liq     = amd.tp_liquidity
        raw_score  = amd.score
        reasons    = amd.reasons

    # ── Score final ───────────────────────────────────────────
    score = min(raw_score, 100)

    if not silent:
        bar  = "█" * (score // 5) + "░" * (20 - score // 5)
        sc   = "green" if score >= SCORE_THRESHOLD else "red"
        mode_label = "★ SMC TRADER" if use_smc else "🔮 AMD"
        print(f"\n  Mode sélectionné : {c(mode_label, 'magenta')}")
        print(f"  Score  [{c(bar, sc)}]  {c(str(score)+'/100', sc)}")

    if score < SCORE_THRESHOLD:
        if not silent:
            print(c(f"\n  ✗ Score {score} < {SCORE_THRESHOLD} — insuffisant.", "yellow"))
        return None

    # ── Calcul Entry / SL / TP ────────────────────────────────
    entry, sl, tp, rr = compute_levels(
        price_now  = price_now,
        direction  = direction,
        sweep_low  = sweep_low,
        sweep_high = sweep_high,
        entry_top  = entry_top,
        entry_bottom = entry_bot,
        tp_liquidity = tp_liq,
        symbol     = symbol,
        df_fallback = df_15m,
    )

    if rr < MIN_RR:
        if not silent:
            print(c(f"\n  ✗ RR {rr} < {MIN_RR} — rejeté.", "yellow"))
        return None

    lot = compute_lot(symbol, entry, sl)
    dec = 2 if entry > 100 else 5

    if not silent:
        d_col  = "red" if direction == "SHORT" else "green"
        rr_col = "green" if rr >= 3 else "yellow"
        print(f"\n  {c('━'*55, 'cyan')}")
        print(f"  {c('⚡ SIGNAL v5', 'yellow')}  [{c(mode, 'magenta')}]  →  {c(direction, d_col)}")
        print(f"  {c('━'*55, 'cyan')}")
        print(f"  {'📍 Entrée':<22} {c(str(entry), 'white')}")
        sl_note = "sous bougie X" if direction == "LONG" else "au-dessus bougie X"
        print(f"  {'🔴 Stop Loss':<22} {c(str(sl), 'red')}  ({sl_note}  Δ={round(abs(entry-sl),dec)})")
        print(f"  {'🟢 Take Profit':<22} {c(str(tp), 'green')}  (liquidité BSL/SSL  Δ={round(abs(tp-entry),dec)})")
        print(f"  {'⚖  R : R':<22} {c('1:'+str(rr), rr_col)}")
        print(f"  {'💰 LOT':<22} {c(str(lot)+' lot', 'magenta')}")
        print(f"  {c('━'*55, 'cyan')}")
        print(f"  Confluence :")
        for r in reasons:
            print(f"    • {r}")
        print(f"  {c('━'*55, 'cyan')}\n")

    return Signal(
        symbol    = symbol,
        direction = direction,
        entry     = entry,
        sl        = sl,
        tp        = tp,
        rr        = rr,
        score     = score,
        timestamp = datetime.now(timezone.utc),
        htf_bias  = bias,
        lot       = lot,
        risk_usd  = RISK_USD,
        mode      = mode,
        reasons   = reasons,
    )


# ═════════════════════════════════════════════════════════════
#  WATCHLIST
# ═════════════════════════════════════════════════════════════

TIER_1_PRIORITY: list[tuple[str, str]] = [
    # GOLD & COMMODITÉS
    ("GC=F",    "Gold (XAU/USD)"),
    ("CL=F",    "Oil WTI"),
    ("BZ=F",    "Oil Brent"),
    # CRYPTO
    ("BTC-USD", "Bitcoin (BTC)"),
    # INDICES — Smc Trader trade ces marchés
    ("^GDAXI",  "GER30 (DAX)"),
    ("^DJI",    "US30 (Dow Jones)"),
    ("^NDX",    "NAS100 (Nasdaq)"),
    ("^GSPC",   "SPX500 (S&P 500)"),
]

TIER_2_FOREX: list[tuple[str, str]] = [
    # Smc Trader : EUR/USD · USD/JPY · USD/CAD
    ("EURUSD=X", "EUR/USD"),
    ("GBPUSD=X", "GBP/USD"),
    ("USDJPY=X", "USD/JPY"),
    ("USDCAD=X", "USD/CAD"),
    ("USDCHF=X", "USD/CHF"),
    ("AUDUSD=X", "AUD/USD"),
    ("NZDUSD=X", "NZD/USD"),
]

TIER_3_CROSSES: list[tuple[str, str]] = [
    ("EURJPY=X", "EUR/JPY"),
    ("GBPJPY=X", "GBP/JPY"),
    ("EURGBP=X", "EUR/GBP"),
    ("GBPAUD=X", "GBP/AUD"),
    ("EURAUD=X", "EUR/AUD"),
    ("AUDJPY=X", "AUD/JPY"),
    ("CADJPY=X", "CAD/JPY"),
    ("CHFJPY=X", "CHF/JPY"),
    ("EURCAD=X", "EUR/CAD"),
    ("GBPCAD=X", "GBP/CAD"),
    ("NZDJPY=X", "NZD/JPY"),
    ("GBPNZD=X", "GBP/NZD"),
    ("EURNZD=X", "EUR/NZD"),
]

CATEGORY_MAP: dict[str, list[tuple[str, str]]] = {
    "priority" : TIER_1_PRIORITY,
    "forex"    : TIER_2_FOREX,
    "crosses"  : TIER_3_CROSSES,
    "all"      : TIER_1_PRIORITY + TIER_2_FOREX + TIER_3_CROSSES,
}

def get_symbols(cat: str) -> list[tuple[str, str]]:
    return CATEGORY_MAP.get(cat, TIER_1_PRIORITY + TIER_2_FOREX)


# ═════════════════════════════════════════════════════════════
#  FLASK DASHBOARD
# ═════════════════════════════════════════════════════════════

flask_app = Flask(__name__)
_STATUS: dict = {
    "started_at": None, "last_scan": None, "cycle": 0,
    "symbols_count": 0, "last_signals": [], "scan_running": False,
}
_STATUS_LOCK = threading.Lock()


@flask_app.route("/")
def index():
    with _STATUS_LOCK:
        st = dict(_STATUS)

    signals_html = ""
    for s in reversed(st["last_signals"][-20:]):
        color    = "#e74c3c" if s["direction"] == "SHORT" else "#2ecc71"
        mode_col = "#f1c40f" if s.get("mode") == "SMC_TRADER" else "#9b59b6"
        mode_lbl = "★ SMC TRADER" if s.get("mode") == "SMC_TRADER" else "🔮 AMD"
        signals_html += (
            f"<tr>"
            f"<td>{s['ts']}</td>"
            f"<td><b>{s['market']}</b></td>"
            f"<td style='color:{color};font-weight:bold'>{s['direction']}</td>"
            f"<td><span style='background:{mode_col};color:#000;padding:2px 8px;"
            f"border-radius:4px;font-size:.8em;font-weight:bold'>{mode_lbl}</span></td>"
            f"<td>{s['entry']}</td>"
            f"<td style='color:#e74c3c'>{s['sl']}</td>"
            f"<td style='color:#2ecc71'>{s['tp']}</td>"
            f"<td>1:{s['rr']}</td>"
            f"<td>{s['score']}/100</td>"
            f"<td>{s['lot']} lot</td>"
            f"</tr>"
        )

    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta http-equiv="refresh" content="30">
  <title>SMC v5 — Smc Trader + AMD</title>
  <style>
    body  {{ font-family: monospace; background:#0d1117; color:#c9d1d9; margin:2em; }}
    h1    {{ color:#f1c40f; }}
    h2    {{ color:#8b949e; border-bottom:1px solid #30363d; padding-bottom:.3em; }}
    table {{ border-collapse:collapse; width:100%; }}
    th    {{ background:#161b22; color:#8b949e; padding:.5em 1em; text-align:left; }}
    td    {{ padding:.4em 1em; border-bottom:1px solid #21262d; }}
    .badge{{ display:inline-block; padding:.2em .6em; border-radius:4px; font-size:.85em; font-weight:bold; }}
    .live {{ background:#2ecc71; color:#000; }}
    .idle {{ background:#f39c12; color:#000; }}
    .box  {{ background:#161b22; border:1px solid #30363d; border-radius:8px;
              padding:1em 1.5em; margin-bottom:1.5em; }}
  </style>
</head>
<body>
  <h1>★ SMC Signal Engine v5</h1>
  <div class="box">
    <b>2 SETUPS UNIQUEMENT :</b><br>
    <b style="color:#f1c40f">★ SMC TRADER</b> — BOS → Sweep(X) → MSS → FVG/OB<br>
    <b style="color:#9b59b6">🔮 AMD H1</b> — Accumulation → Manipulation → Distribution<br><br>
    <b>SL :</b> Sous/au-dessus de la bougie sweep (X) &nbsp;|&nbsp;
    <b>TP :</b> Prochaine liquidité BSL/SSL &nbsp;|&nbsp;
    <b>TF :</b> H1 → 30M → 15M
  </div>
  <p>
    Statut : <span class="badge {'live' if st['scan_running'] else 'idle'}">
      {'🟢 SCAN ACTIF' if st['scan_running'] else '🟡 EN ATTENTE'}
    </span>
    &nbsp;|&nbsp; Démarré : <b>{st['started_at'] or '—'}</b>
    &nbsp;|&nbsp; Cycle : <b>#{st['cycle']}</b>
    &nbsp;|&nbsp; Marchés : <b>{st['symbols_count']}</b>
    &nbsp;|&nbsp; Dernier scan : <b>{st['last_scan'] or '—'}</b>
  </p>
  <p style="color:#8b949e;font-size:.85em">⟳ Rafraîchissement toutes les 30s</p>
  <h2>📋 Derniers signaux</h2>
  {'<p style="color:#f39c12">Aucun signal validé pour le moment.</p>' if not st['last_signals'] else f"""
  <table>
    <tr>
      <th>Heure UTC</th><th>Marché</th><th>Direction</th><th>Setup</th>
      <th>Entrée</th><th>SL 🔴</th><th>TP 🟢</th><th>R:R</th><th>Score</th><th>Lot</th>
    </tr>{signals_html}
  </table>"""}
  <h2>⚙️ Configuration</h2>
  <table>
    <tr><th>Paramètre</th><th>Valeur</th></tr>
    <tr><td>Score minimum</td><td>{SCORE_THRESHOLD}/100</td></tr>
    <tr><td>RR minimum</td><td>1:{MIN_RR}</td></tr>
    <tr><td>Risque/trade</td><td>${RISK_USD}</td></tr>
    <tr><td>Timeframes</td><td>H1 → 30M → 15M</td></tr>
    <tr><td>Setup 1</td><td>★ SMC TRADER : BOS → Sweep(X) → MSS → FVG/OB</td></tr>
    <tr><td>Setup 2</td><td>🔮 AMD H1 : Accumulation → Manipulation → Distribution</td></tr>
    <tr><td>SL placement</td><td>Sous/Au-dessus de la bougie sweep (X)</td></tr>
    <tr><td>TP cible</td><td>Prochaine liquidité BSL/SSL</td></tr>
    <tr><td>Marchés</td><td>Gold · BTC · GER30 · US30 · NAS100 · Oil · Forex complet</td></tr>
    <tr><td>Intervalle scan</td><td>{SCAN_INTERVAL} secondes</td></tr>
  </table>
</body>
</html>"""
    return html


@flask_app.route("/status")
def status_json():
    with _STATUS_LOCK:
        return jsonify(_STATUS)


def start_flask(port: int = 10000):
    flask_app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)


def start_self_ping(port: int = 10000):
    url      = os.environ.get("RENDER_EXTERNAL_URL", f"http://localhost:{port}")
    ping_url = f"{url}/status"

    def _loop():
        time.sleep(30)
        while True:
            try:
                r = requests.get(ping_url, timeout=10)
                if r.status_code != 200:
                    log.warning(f"  ⚠ Self-ping HTTP {r.status_code}")
            except Exception as e:
                log.warning(f"  ⚠ Self-ping : {e}")
            time.sleep(240)

    threading.Thread(target=_loop, daemon=True, name="self-ping").start()
    log.info(f"  ✓ Self-ping → {ping_url}")


# ═════════════════════════════════════════════════════════════
#  BOUCLE PRINCIPALE LIVE
# ═════════════════════════════════════════════════════════════

def run_live(cat: str = "all", min_score: int = SCORE_THRESHOLD,
             min_rr: float = MIN_RR, interval: int = SCAN_INTERVAL):

    symbols  = get_symbols(cat)
    total    = len(symbols)
    cycle    = 0
    W        = 95
    err_count = 0

    with _STATUS_LOCK:
        _STATUS["started_at"]    = datetime.now(timezone.utc).strftime("%d/%m %H:%M UTC")
        _STATUS["symbols_count"] = total

    log.info(f"\n  ★ SMC v5 — Smc Trader + AMD H1")
    log.info(f"  TF : H1 → 30M → 15M  |  Score≥{min_score}  RR≥{min_rr}")
    log.info(f"  Marchés : {total}  |  Intervalle : {interval}s\n")

    try:
        requests.post(_tg_url("sendMessage"), json={
            "chat_id": TELEGRAM_GROUP_ID,
            "text": (
                "🟢 <b>SMC Signal Engine v5 — DÉMARRÉ</b>\n"
                "Setups : <b>★ SMC TRADER</b> + <b>🔮 AMD H1</b>\n"
                f"TF : H1 → 30M → 15M  |  {total} marchés\n"
                f"SL = bougie sweep X  |  TP = liquidité BSL/SSL"
            ),
            "parse_mode": "HTML",
        }, timeout=5)
    except Exception:
        pass

    while True:
        cycle += 1
        with _STATUS_LOCK:
            _STATUS["cycle"]        = cycle
            _STATUS["scan_running"] = True
            _STATUS["last_scan"]    = datetime.now(timezone.utc).strftime("%d/%m %H:%M UTC")

        correlation_guard_reset()

        try:
            ts_str = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
            print(f"\n{'╔' + '═'*W + '╗'}")
            print(c(f"║  SMC v5 — Smc Trader + AMD H1  ·  Cycle #{cycle:04d}  ·  {ts_str}{' '*(W-50-len(ts_str))}║", "yellow"))
            print(f"{'╠' + '═'*W + '╣'}")
            print(f"  {'#':<4} {'MARCHÉ':<18} {'PRIX':>12}  {'BIAIS':>6}  "
                  f"{'SMC_T':>6}  {'AMD':>5}  {'MODE':>12}  {'SCORE':>6}  {'R:R':>5}  STATUS")
            print(f"  {'─'*W}")

            signals_found = []

            for i, (sym, mkt) in enumerate(symbols, 1):
                prefix = f"  {i:>2}/{total}  {mkt:<18}"
                try:
                    px = df_px = fetch(sym, LTF, period="1d")
                    px_val = round(px["close"].iloc[-1], 2 if px["close"].iloc[-1] > 100 else 5) if not px.empty else "—"
                    px_s   = str(px_val)

                    sig = analyse(sym, HTF, MTF, LTF, silent=True)

                    if sig is None:
                        # Essaie d'afficher quand même le biais
                        df_h  = fetch(sym, HTF, period="10d")
                        bias_ = htf_bias(df_h) if not df_h.empty else "—"
                        b_col = "red" if "BEAR" in bias_ else ("green" if "BULL" in bias_ else "white")
                        print(f"\r{prefix}  {px_s:>12}  {c(bias_[:4], b_col):>6}  "
                              f"{'✗':>6}  {'✗':>5}  {'—':>12}  {'—':>6}  {'—':>5}  "
                              + c("En attente", "white"))
                        time.sleep(0.5)
                        continue

                    d_col  = "red" if sig.direction == "SHORT" else "green"
                    sc_col = "green" if sig.score >= min_score else "yellow"
                    rr_col = "green" if sig.rr >= 3 else "yellow"
                    smc_ok = "✓" if sig.mode == "SMC_TRADER" else "—"
                    amd_ok = "✓" if sig.mode == "AMD" else "—"

                    if sig.score >= min_score and sig.rr >= min_rr:
                        corr_ok, _ = correlation_guard(sym, sig.direction)
                        if corr_ok:
                            signals_found.append((mkt, sym, sig))
                            status = c(f"⚡ {sig.direction} [{sig.mode}]", d_col)
                        else:
                            status = c("🟠 Corrélé", "yellow")
                    else:
                        status = c(f"🟡 Proche ({sig.score})", "yellow")

                    print(f"\r{prefix}  {px_s:>12}  "
                          f"{c(sig.htf_bias[:4], d_col):>6}  "
                          f"{c(smc_ok, 'green'):>6}  {c(amd_ok, 'magenta'):>5}  "
                          f"{c(sig.mode, 'magenta'):>12}  "
                          f"{c(str(sig.score), sc_col):>6}  "
                          f"{c('1:'+str(sig.rr), rr_col):>5}  {status}")
                    time.sleep(1)

                except Exception as e:
                    print(f"\r{prefix}  {'—':>12}  {'—':>6}  "
                          f"{'—':>6}  {'—':>5}  {'—':>12}  {'—':>6}  {'—':>5}  "
                          + c(f"⚠ {str(e)[:40]}", "red"))

            # ── Max 2 meilleurs signaux par cycle ──────────────
            print(f"  {'─'*W}")
            if len(signals_found) > 2:
                signals_found = sorted(signals_found, key=lambda x: x[2].score, reverse=True)[:2]

            if signals_found:
                print(c(f"\n  ⚡ {len(signals_found)} signal(s) — Envoi Telegram…", "yellow"))

            for mkt, sym, sig in signals_found:
                if not check_daily_limit(sym):
                    log.info(f"  ⏭ {sym} — limite journalière atteinte")
                    continue
                increment_daily_count(sym)
                log.info(f"  ⚡ {sig.direction} {mkt}  [{sig.mode}]  score={sig.score}  RR=1:{sig.rr}")
                tg_notify(sig)

                with _STATUS_LOCK:
                    _STATUS["last_signals"].append({
                        "ts"       : datetime.now(timezone.utc).strftime("%d/%m %H:%M"),
                        "market"   : mkt,
                        "direction": sig.direction,
                        "entry"    : sig.entry,
                        "sl"       : sig.sl,
                        "tp"       : sig.tp,
                        "rr"       : sig.rr,
                        "score"    : sig.score,
                        "lot"      : sig.lot,
                        "mode"     : sig.mode,
                    })
                    _STATUS["last_signals"] = _STATUS["last_signals"][-50:]

            if not signals_found:
                print(c(f"  ℹ  Aucun signal valide (score≥{min_score} + RR≥{min_rr})", "white"))

            print(f"{'╚' + '═'*W + '╝'}")
            with _STATUS_LOCK:
                _STATUS["scan_running"] = False
            err_count = 0
            log.info(f"  ⏳ Prochain scan dans {interval}s\n")
            time.sleep(interval)

        except KeyboardInterrupt:
            log.info("\n  Session terminée.")
            try:
                requests.post(_tg_url("sendMessage"), json={
                    "chat_id": TELEGRAM_GROUP_ID,
                    "text": "🔴 <b>SMC Signal Engine v5 arrêté</b>",
                    "parse_mode": "HTML",
                }, timeout=5)
            except Exception:
                pass
            break

        except Exception as e:
            err_count += 1
            log.error(f"  ✗ Erreur critique : {e}")
            wait = min(60 * err_count, 300)
            log.info(f"  ⏳ Reprise dans {wait}s")
            time.sleep(wait)


# ─────────────────────────────────────────────────────────────
#  SCAN UNIQUE (test local)
# ─────────────────────────────────────────────────────────────

def scan_once(symbols: list[tuple[str, str]], min_score: int = SCORE_THRESHOLD,
              min_rr: float = MIN_RR):
    ts    = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    total = len(symbols)
    results = []

    print(f"\n{c('╔' + '═'*60 + '╗', 'cyan')}")
    print(f"{c('║', 'cyan')}  {c('SMC v5 — Smc Trader + AMD H1', 'yellow'):<59}{c('║', 'cyan')}")
    print(f"{c('║', 'cyan')}  H1 → 30M → 15M  |  score≥{min_score}  RR≥{min_rr}  |  {ts:<16}{c('║', 'cyan')}")
    print(f"{c('╚' + '═'*60 + '╝', 'cyan')}")

    for i, (sym, mkt) in enumerate(symbols, 1):
        print(f"  [{i:>2}/{total}]  {mkt:<18} {c(sym, 'cyan')} … ", end="", flush=True)
        try:
            sig = analyse(sym, HTF, MTF, LTF, silent=True)
            if sig and sig.score >= min_score and sig.rr >= min_rr:
                results.append((mkt, sig))
                d_col = "red" if sig.direction == "SHORT" else "green"
                print(c(f"⚡ {sig.direction} [{sig.mode}]  score={sig.score}  RR=1:{sig.rr}", d_col))
                tg_notify(sig)
            else:
                sc = f"score={sig.score}" if sig else "—"
                print(c(f"— ({sc})", "white"))
        except Exception as e:
            print(c(f"err: {e}", "red"))

    if results:
        print(f"\n{c('═'*65, 'yellow')}")
        print(c(f"  ⚡ {len(results)} signal(s)", "yellow"))
        for mkt, s in sorted(results, key=lambda x: -x[1].score):
            d = "red" if s.direction == "SHORT" else "green"
            print(f"  {mkt:<18} {c(s.direction, d)}  [{s.mode}]  "
                  f"score={s.score}  RR=1:{s.rr}  lot={s.lot}")
    else:
        print(c(f"\n  Aucun signal score≥{min_score} RR≥{min_rr}", "yellow"))
    return results


# ═════════════════════════════════════════════════════════════
#  MAIN
# ═════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="SMC v5 — Smc Trader (BOS→Sweep→MSS→FVG/OB) + AMD H1",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--symbol",    default=None,
                        help="Symbole unique (ex: GC=F, BTC-USD, EURUSD=X)")
    parser.add_argument("--cat",       default="all",
                        choices=["priority", "forex", "crosses", "all"],
                        help=(
                            "priority = Gold + BTC + Indices (défaut)\n"
                            "forex    = Forex majeures\n"
                            "crosses  = Forex croisées\n"
                            "all      = Tout"
                        ))
    parser.add_argument("--scan",      action="store_true",
                        help="Scan unique (test)")
    parser.add_argument("--min-score", type=int,   default=SCORE_THRESHOLD)
    parser.add_argument("--min-rr",    type=float, default=MIN_RR)
    parser.add_argument("--interval",  type=int,   default=SCAN_INTERVAL,
                        help=f"Intervalle scan en secondes (défaut: {SCAN_INTERVAL})")
    args = parser.parse_args()

    # Flask dashboard
    flask_port = int(os.environ.get("PORT", 10000))
    threading.Thread(target=start_flask, args=(flask_port,),
                     daemon=True, name="flask").start()
    time.sleep(2)
    log.info(f"  ✓ Flask dashboard port {flask_port}")

    # Self-ping anti-veille Render
    start_self_ping(flask_port)

    # Mode selon arguments
    if args.symbol:
        sig = analyse(args.symbol)
        if sig:
            tg_notify(sig)
    elif args.scan:
        symbols = get_symbols(args.cat)
        scan_once(symbols, args.min_score, args.min_rr)
    else:
        run_live(cat=args.cat, min_score=args.min_score,
                 min_rr=args.min_rr, interval=args.interval)

