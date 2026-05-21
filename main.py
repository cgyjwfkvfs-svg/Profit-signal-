"""
╔══════════════════════════════════════════════════════════════════════════╗
║         SMC SIGNAL ENGINE  v3  — Smart Money Concepts ELITE             ║
║                                                                          ║
║  NOUVEAUTÉS v3 :                                                         ║
║  ✦ AMD  Accumulation → Manipulation → Distribution  (H4)                ║
║  ✦ SEPTUPLE TRACTION H4  — 7 bougies momentum institutionnel            ║
║  ✦ SUPPLY & DEMAND ZONES  — zones institutionnelles vraies              ║
║  ✦ LIQUIDITY MAP AVANCÉE  — EQH/EQL · BSL/SSL · intra-range            ║
║  ✦ BTC UNIQUEMENT pour le crypto                                        ║
║  ✦ CONFIRMATION H4 → M15 → M5  (3 TF institutionnels)                  ║
║  ✦ BREAKER BLOCK amélioré                                               ║
║  ✦ BOUGIES D'ENTRÉE institutionnelles  (Displacement · OFS · Imb.)     ║
║                                                                          ║
║   FOREX  |  BTC  |  GOLD  |  INDICES                                    ║
╚══════════════════════════════════════════════════════════════════════════╝

Installation :
    pip install yfinance pandas numpy colorama flask requests

Usage :
    python smc_signals_v3.py                    # scan complet live
    python smc_signals_v3.py --cat forex        # forex seulement
    python smc_signals_v3.py --cat btc          # BTC seulement
    python smc_signals_v3.py --cat priority     # Gold + BTC
    python smc_signals_v3.py --symbol BTC-USD   # symbole unique
    python smc_signals_v3.py --scan             # scan unique (test)
    python smc_signals_v3.py --min-score 80     # filtre score
"""

import argparse
import threading
import time
import os
import requests
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf

# ── Flask — serveur HTTP pour Render ─────────────────────────
from flask import Flask, jsonify

flask_app = Flask(__name__)

_STATUS: dict = {
    "started_at"   : None,
    "last_scan"    : None,
    "cycle"        : 0,
    "symbols_count": 0,
    "last_signals" : [],
    "scan_running" : False,
}
_STATUS_LOCK = threading.Lock()


@flask_app.route("/")
def index():
    with _STATUS_LOCK:
        st = dict(_STATUS)

    signals_html = ""
    for s in reversed(st["last_signals"][-15:]):
        color    = "#e74c3c" if s["direction"] == "SHORT" else "#2ecc71"
        mode_col = {"AMD": "#9b59b6", "PRE-BOS": "#f39c12",
                    "SMC": "#58a6ff"}.get(s.get("mode", "SMC"), "#58a6ff")
        signals_html += (
            f"<tr>"
            f"<td>{s['ts']}</td>"
            f"<td><b>{s['market']}</b></td>"
            f"<td style='color:{color};font-weight:bold'>{s['direction']}</td>"
            f"<td><span style='background:{mode_col};color:#000;padding:2px 6px;"
            f"border-radius:4px;font-size:.8em;font-weight:bold'>{s.get('mode','SMC')}</span></td>"
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
  <title>SMC Signal Engine v3</title>
  <style>
    body  {{ font-family: monospace; background:#0d1117; color:#c9d1d9; margin:2em; }}
    h1    {{ color:#58a6ff; }}
    h2    {{ color:#8b949e; border-bottom:1px solid #30363d; padding-bottom:.3em; }}
    table {{ border-collapse:collapse; width:100%; }}
    th    {{ background:#161b22; color:#8b949e; padding:.5em 1em; text-align:left; }}
    td    {{ padding:.4em 1em; border-bottom:1px solid #21262d; }}
    .badge{{ display:inline-block; padding:.2em .6em; border-radius:4px; font-size:.85em; font-weight:bold; }}
    .live {{ background:#2ecc71; color:#000; }}
    .idle {{ background:#f39c12; color:#000; }}
  </style>
</head>
<body>
  <h1>⚡ SMC Signal Engine v3 — AMD · Supply/Demand · Septuple Traction</h1>
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
      <th>Heure UTC</th><th>Marché</th><th>Direction</th><th>Mode</th>
      <th>Entrée</th><th>SL 🔴</th><th>TP 🟢</th><th>R:R</th><th>Score</th><th>Lot</th>
    </tr>{signals_html}
  </table>"""}
  <h2>⚙️ Configuration</h2>
  <table>
    <tr><th>Paramètre</th><th>Valeur</th></tr>
    <tr><td>Score minimum</td><td>{SCORE_THRESHOLD}/100</td></tr>
    <tr><td>RR minimum</td><td>1:{MIN_RR}</td></tr>
    <tr><td>Risque/trade</td><td>${RISK_USD}</td></tr>
    <tr><td>Timeframes</td><td>H4 → M15 → M5</td></tr>
    <tr><td>Modes</td><td>SMC + AMD + Septuple Traction + Supply/Demand</td></tr>
    <tr><td>Intervalle scan</td><td>30 secondes</td></tr>
  </table>
</body>
</html>"""
    return html


@flask_app.route("/status")
def status_json():
    with _STATUS_LOCK:
        return jsonify(_STATUS)


def start_flask(port: int = 10000) -> None:
    flask_app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)


def start_self_ping(port: int = 10000) -> None:
    url = os.environ.get("RENDER_EXTERNAL_URL", f"http://localhost:{port}")
    ping_url = f"{url}/status"

    def _ping_loop():
        time.sleep(30)
        while True:
            try:
                r = requests.get(ping_url, timeout=10)
                if r.status_code != 200:
                    log.warning(f"  ⚠ Self-ping HTTP {r.status_code}")
            except Exception as e:
                log.warning(f"  ⚠ Self-ping échoué : {e}")
            time.sleep(240)

    t = threading.Thread(target=_ping_loop, daemon=True, name="self-ping")
    t.start()
    log.info(f"  ✓ Self-ping actif → {ping_url}")


try:
    from colorama import Fore, Style, init as colorama_init
    colorama_init(autoreset=True)
    COLOR = True
except ImportError:
    COLOR = False

# ═════════════════════════════════════════════════════════════
#  CONFIGURATION GLOBALE
# ═════════════════════════════════════════════════════════════
HTF             = "4h"    # ← H4 : biais institutionnel + AMD + Septuple Traction
MTF             = "15m"   # M15 : confirmation structure
LTF             = "5m"    # M5  : entrée précise

FVG_MIN_RATIO   = 0.0002
OB_LOOKBACK     = 5
LIQ_THRESHOLD   = 0.0004
SCORE_THRESHOLD = 80
MIN_RR          = 2.0
RISK_USD        = 25.0

# ── Septuple Traction : N bougies consécutives minimum ───────
SEPTUPLE_MIN_CANDLES = 5   # 5 suffisent en practice (7 = très rare)

# ── AMD Phase Detection ────────────────────────────────────
AMD_LOOKBACK = 50   # bougies H4 pour détecter les 3 phases

# ── Supply & Demand Zones ─────────────────────────────────
SD_MIN_IMPULSE_RATIO = 1.5  # corps bougie ≥ 1.5× ATR pour qualifier une zone S/D
SD_ZONE_BUFFER       = 0.15  # tolérance 15% de l'ATR pour "dans la zone"

# ─────────────────────────────────────────────────────────────
#  SESSIONS ACTIVES (UTC)
# ─────────────────────────────────────────────────────────────
SESSION_WINDOWS_UTC: list[tuple[int, int]] = [
    (7,  10),   # London open
    (13, 16),   # NY open + overlap
]


def is_session_active() -> bool:
    hour = datetime.now(timezone.utc).hour
    return any(start <= hour < end for start, end in SESSION_WINDOWS_UTC)


# ─────────────────────────────────────────────────────────────
#  ATR MINIMUM PAR INSTRUMENT
# ─────────────────────────────────────────────────────────────
ATR_MIN: dict[str, float] = {
    "EURUSD=X": 0.00060, "GBPUSD=X": 0.00080, "USDJPY=X": 0.080,
    "USDCHF=X": 0.00060, "AUDUSD=X": 0.00055, "NZDUSD=X": 0.00050,
    "USDCAD=X": 0.00060, "GBPJPY=X": 0.120,   "EURJPY=X": 0.090,
    "GBPAUD=X": 0.00110, "GBPCAD=X": 0.00110, "GBPNZD=X": 0.00130,
    "EURGBP=X": 0.00045, "EURAUD=X": 0.00090, "EURCAD=X": 0.00090,
    "AUDJPY=X": 0.070,   "CADJPY=X": 0.070,   "CHFJPY=X": 0.080,
    "NZDJPY=X": 0.065,
    "GC=F"    : 1.50,    "SI=F"    : 0.05,
    "CL=F"    : 0.30,    "BZ=F"    : 0.30,
    "BTC-USD" : 200.0,   "ETH-USD" : 10.0,
    "^GSPC"   : 8.0,     "^NDX"    : 30.0,    "^DJI"    : 80.0,
    "^GDAXI"  : 40.0,
}
ATR_MIN_DEFAULT = 0.00050
MAX_SPREAD_ATR_RATIO = 0.25


def check_volatility(symbol: str, df_ltf: pd.DataFrame) -> tuple[bool, str]:
    if df_ltf.empty or len(df_ltf) < 14:
        return False, "données insuffisantes"
    atr = (df_ltf["high"] - df_ltf["low"]).rolling(14).mean().iloc[-1]
    atr_min = ATR_MIN.get(symbol, ATR_MIN_DEFAULT)
    spread  = get_spread(symbol)
    if atr < atr_min * 0.7:
        return False, f"ATR trop faible ({round(atr, 5)} < {round(atr_min*0.7,5)})"
    ratio = spread / atr if atr > 0 else 1.0
    if ratio > MAX_SPREAD_ATR_RATIO:
        return False, f"spread/ATR={round(ratio*100,1)}% > {int(MAX_SPREAD_ATR_RATIO*100)}%"
    if not is_session_active():
        return False, "hors session (London/NY)"
    return True, ""


# ─────────────────────────────────────────────────────────────
#  SPREADS
# ─────────────────────────────────────────────────────────────
SPREAD_TABLE: dict[str, float] = {
    "EURUSD=X": 0.00008, "GBPUSD=X": 0.00010, "USDJPY=X": 0.009,
    "USDCHF=X": 0.00010, "AUDUSD=X": 0.00010, "NZDUSD=X": 0.00013,
    "USDCAD=X": 0.00012, "EURGBP=X": 0.00013, "EURJPY=X": 0.012,
    "EURCHF=X": 0.00018, "EURAUD=X": 0.00020, "EURCAD=X": 0.00020,
    "EURNZD=X": 0.00025, "GBPJPY=X": 0.018,   "GBPCHF=X": 0.00022,
    "GBPAUD=X": 0.00025, "GBPCAD=X": 0.00025, "GBPNZD=X": 0.00030,
    "AUDJPY=X": 0.012,   "CADJPY=X": 0.015,   "CHFJPY=X": 0.015,
    "NZDJPY=X": 0.015,   "AUDCAD=X": 0.00018, "AUDCHF=X": 0.00018,
    "AUDNZD=X": 0.00020, "NZDCAD=X": 0.00020, "NZDCHF=X": 0.00020,
    "CADCHF=X": 0.00018, "USDMXN=X": 0.003,   "USDZAR=X": 0.005,
    "USDTRY=X": 0.010,   "USDSEK=X": 0.004,   "USDNOK=X": 0.004,
    "USDSGD=X": 0.00020, "USDHKD=X": 0.00030,
    "GC=F"    : 0.30,    "SI=F"    : 0.015,
    "CL=F"    : 0.03,    "BZ=F"    : 0.04,    "NG=F"    : 0.003,
    "BTC-USD" : 15.0,    "ETH-USD" : 0.80,
    "^GSPC"   : 0.30,    "^NDX"    : 0.50,    "^DJI"    : 2.00,
    "^GDAXI"  : 1.00,    "^FCHI"   : 1.00,    "^FTSE"   : 1.00,
    "^N225"   : 5.00,    "^HSI"    : 5.00,
}


def get_spread(symbol: str) -> float:
    return SPREAD_TABLE.get(symbol, 0.00015)


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
    "GC=F"    : "GOLD", "SI=F"    : "GOLD",
    "CL=F"    : "OIL",  "BZ=F"    : "OIL",
    "BTC-USD" : "BTC",
    "^GSPC"   : "US_IDX", "^NDX"  : "US_IDX", "^DJI"  : "US_IDX",
    "^GDAXI"  : "EU_IDX", "^FCHI" : "EU_IDX",
}

_active_corr_groups: dict[str, float] = {}
CORR_TTL = 900


def correlation_guard_reset() -> None:
    _active_corr_groups.clear()


def correlation_guard(symbol: str, direction: str) -> tuple[bool, str]:
    group = _CORR_GROUPS.get(symbol)
    if group is None:
        return True, ""
    key    = f"{group}:{direction}"
    now_ts = time.time()
    if key in _active_corr_groups:
        if now_ts - _active_corr_groups[key] > CORR_TTL:
            del _active_corr_groups[key]
        else:
            return False, f"corrélation {group} {direction} active"
    _active_corr_groups[key] = now_ts
    return True, ""


# ─────────────────────────────────────────────────────────────
#  TELEGRAM
# ─────────────────────────────────────────────────────────────
TELEGRAM_TOKEN    = os.environ.get("TG_TOKEN", "8665812395:AAFO4BMTIrBCQJYVL8UytO028TcB1sDfgbI")
TELEGRAM_CHAT_ID  = None
TELEGRAM_GROUP_ID = "-1002335466840"

SIGNAL_COOLDOWN = 600
_signal_cache: dict[str, float] = {}
_setup_sent: dict[str, bool] = {}


def _setup_key(symbol: str, direction: str, score: int) -> str:
    bucket = (score // 5) * 5
    return f"{symbol}:{direction}:{bucket}"


def is_setup_already_sent(symbol: str, direction: str, score: int) -> bool:
    return _setup_sent.get(_setup_key(symbol, direction, score), False)


def mark_setup_sent(symbol: str, direction: str, score: int) -> None:
    _setup_sent[_setup_key(symbol, direction, score)] = True


def reset_setup(symbol: str) -> None:
    keys_to_del = [k for k in _setup_sent if k.startswith(f"{symbol}:")]
    for k in keys_to_del:
        del _setup_sent[k]


def _tg_url(method: str) -> str:
    return f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}"


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
            chat      = msg.get("chat", {})
            chat_type = chat.get("type", "")
            cid       = str(chat.get("id", ""))
            if chat_type in ("group", "supergroup") and not TELEGRAM_GROUP_ID:
                TELEGRAM_GROUP_ID = cid
            elif chat_type == "private" and not personal_id:
                personal_id = cid
        return personal_id
    except Exception:
        pass
    return None


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
        print(c(f"  [TG] Erreur : {e}", "red"))
        return False


def tg_format_signal(sig: "Signal", tier: str = "", mode: str = "SMC") -> str:
    """Formate le signal avec toutes les infos v3 (AMD, S/D, Septuple)."""
    dir_emoji  = "🔴 SHORT" if sig.direction == "SHORT" else "🟢 LONG"
    score_bar  = "█" * (sig.score // 10) + "░" * (10 - sig.score // 10)
    rr_bar     = "⭐" * min(int(sig.rr), 5)
    ts         = sig.timestamp.strftime("%d/%m/%Y %H:%M UTC")
    dec        = 2 if sig.entry > 100 else 5
    risk_d     = round(abs(sig.entry - sig.sl), dec)
    gain_d     = round(abs(sig.tp - sig.entry), dec)
    gain_usd   = round(RISK_USD * sig.rr, 2)
    spread_d   = round(get_spread(sig.symbol), dec)

    mode_badge = {
        "AMD"    : "🔮 AMD — Accumulation·Manipulation·Distribution",
        "SEPTUPLE": "⚡ SEPTUPLE TRACTION H4",
        "SD"     : "🏛️ SUPPLY & DEMAND ZONE",
        "SMC"    : "📊 SMC — Structure · FVG · OB",
        "PRE-BOS": "⚠️ PRE-BOS — Avant cassure",
    }.get(mode, "📊 SMC")

    msg = (
        f"<b>⚡ SMC SIGNAL ÉLITE v3</b>\n"
        f"<b>{mode_badge}</b>\n"
        f"{'─'*30}\n"
        f"<b>Marché    :</b>  <code>{sig.symbol}</code>\n"
        f"<b>Direction :</b>  <b>{dir_emoji}</b>\n"
        f"<b>Biais H4  :</b>  {sig.htf_bias}\n"
        f"<b>TF Entrée :</b>  H4 → M15 → M5\n"
        f"{'─'*30}\n"
        f"<b>📍 Entrée     :</b>  <code>{sig.entry}</code>\n"
        f"<b>🔴 Stop Loss  :</b>  <code>{sig.sl}</code>  <i>(risk {risk_d})</i>\n"
        f"<b>🟢 Take Profit:</b>  <code>{sig.tp}</code>  <i>(gain brut {gain_d})</i>\n"
        f"<b>📊 Spread     :</b>  <code>{spread_d}</code>\n"
        f"<b>⚖  R : R net  :</b>  <b>1 : {sig.rr}</b>  {rr_bar}\n"
        f"{'─'*30}\n"
        f"<b>💰 LOT SIZE   :</b>  <b><code>{sig.lot} lot</code></b>\n"
        f"<b>⚠  Risque     :</b>  <b>${sig.risk_usd}</b>  →  gain ≈ <b>${gain_usd}</b>\n"
        f"{'─'*30}\n"
        f"<b>Score :</b>  [{score_bar}]  {sig.score}/100\n"
        f"<b>Confluence :</b>\n"
    )
    for r in sig.reasons:
        msg += f"  • {r}\n"
    msg += f"{'─'*30}\n<i>🕐 {ts}</i>"
    return msg


def tg_notify(sig: "Signal", tier: str = "", mode: str = "SMC",
              chat_id: Optional[str] = None) -> None:
    global TELEGRAM_CHAT_ID, TELEGRAM_GROUP_ID

    if is_setup_already_sent(sig.symbol, sig.direction, sig.score):
        print(c(f"  [TG] ⏭ Setup déjà envoyé — {sig.symbol} {sig.direction}", "yellow"))
        return
    mark_setup_sent(sig.symbol, sig.direction, sig.score)

    cid = chat_id or TELEGRAM_CHAT_ID
    if not cid:
        cid = tg_get_chat_id()
        if cid:
            TELEGRAM_CHAT_ID = cid

    msg = tg_format_signal(sig, tier, mode)

    if cid:
        ok = tg_send(msg, cid)
        print(c(f"  [TG] {'✓ DM envoyé' if ok else '✗ Échec DM'}", "green" if ok else "red"))

    if not TELEGRAM_GROUP_ID:
        tg_get_chat_id()
    if TELEGRAM_GROUP_ID:
        ok_grp = tg_send(msg, TELEGRAM_GROUP_ID)
        print(c(f"  [TG] {'✓ Groupe' if ok_grp else '✗ Groupe échoué'}", "green" if ok_grp else "red"))


# ═════════════════════════════════════════════════════════════
#  DATA CLASSES
# ═════════════════════════════════════════════════════════════

@dataclass
class FVG:
    direction: str
    top:       float
    bottom:    float
    index:     int
    filled:    bool = False


@dataclass
class OrderBlock:
    direction: str
    top:       float
    bottom:    float
    index:     int
    mitigated: bool = False


@dataclass
class SupplyDemandZone:
    """Zone Supply ou Demand institutionnelle."""
    zone_type:  str    # "supply" | "demand"
    top:        float
    bottom:     float
    index:      int
    impulse_size: float  # taille de la bougie impulsive (force de la zone)
    tested:     bool = False


@dataclass
class AmdPhase:
    """
    Résultat de l'analyse de phase AMD.
    phase : "accumulation" | "manipulation" | "distribution" | "unknown"
    sub_phase : "bull_manipulation" | "bear_manipulation" | etc.
    """
    phase:       str
    sub_phase:   str
    direction:   str    # "LONG" | "SHORT" — direction attendue après AMD
    confidence:  int    # 0–100
    range_high:  float
    range_low:   float
    sweep_level: Optional[float] = None
    reasons:     list = field(default_factory=list)


@dataclass
class Signal:
    symbol:    str
    direction: str
    entry:     float
    sl:        float
    tp:        float
    rr:        float
    score:     int
    timestamp: datetime
    htf_bias:  str
    lot:       float = 0.0
    risk_usd:  float = RISK_USD
    mode:      str   = "SMC"   # "SMC" | "AMD" | "SEPTUPLE" | "SD" | "PRE-BOS"
    reasons:   list  = field(default_factory=list)


# ═════════════════════════════════════════════════════════════
#  HELPERS
# ═════════════════════════════════════════════════════════════

def c(text: str, color: str = "green") -> str:
    if not COLOR:
        return text
    colors = {
        "green": Fore.GREEN, "red": Fore.RED, "yellow": Fore.YELLOW,
        "cyan": Fore.CYAN,   "white": Fore.WHITE, "magenta": Fore.MAGENTA,
        "blue": Fore.BLUE,
    }
    return colors.get(color, "") + text + Style.RESET_ALL


def compute_lot(symbol: str, entry: float, sl: float,
                risk_usd: float = RISK_USD) -> float:
    sl_distance = abs(entry - sl)
    if sl_distance == 0:
        return 0.0
    sym = symbol.upper().replace("=X", "").replace("-", "").replace("^", "")

    if symbol in ("GC=F",):
        lot = risk_usd / (sl_distance * 100.0)
    elif symbol in ("SI=F",):
        lot = risk_usd / (sl_distance * 50.0)
    elif symbol in ("CL=F", "BZ=F"):
        lot = risk_usd / (sl_distance * 1000.0)
    elif symbol in ("NG=F", "HG=F", "PL=F", "PA=F"):
        lot = risk_usd / (sl_distance * 100.0)
    elif sym in ("BTCUSD", "ETHUSD") or symbol in ("BTC-USD", "ETH-USD"):
        return round(risk_usd / sl_distance, 6)
    elif sym in ("GSPC", "NDX", "DJI", "GDAXI", "FCHI", "FTSE", "N225", "HSI"):
        lot = risk_usd / (sl_distance * 10.0)
    elif sym.endswith("JPY"):
        sl_pips = sl_distance / 0.01
        pip_val = 1000.0 / entry
        lot = risk_usd / (sl_pips * pip_val)
    elif sym.startswith("USD"):
        sl_pips = sl_distance / 0.0001
        pip_val = 10.0 / entry
        lot = risk_usd / (sl_pips * pip_val)
    else:
        sl_pips = sl_distance / 0.0001
        lot = risk_usd / (sl_pips * 10.0)

    return max(0.01, round(lot, 2))


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
            err_str = str(e).lower()
            if ("rate" in err_str or "too many" in err_str or "429" in err_str) \
                    and attempt < retries:
                time.sleep(retry_delay * attempt)
                continue
            return pd.DataFrame()
    return pd.DataFrame()


def swing_highs(df: pd.DataFrame, n: int = 2) -> list[tuple[int, float]]:
    """Retourne les swing highs (index, valeur) dans les n dernières bougies."""
    result = []
    for i in range(1, len(df) - 1):
        if df["high"].iloc[i] > df["high"].iloc[i-1] and df["high"].iloc[i] > df["high"].iloc[i+1]:
            result.append((i, df["high"].iloc[i]))
    return result


def swing_lows(df: pd.DataFrame) -> list[tuple[int, float]]:
    """Retourne les swing lows (index, valeur)."""
    result = []
    for i in range(1, len(df) - 1):
        if df["low"].iloc[i] < df["low"].iloc[i-1] and df["low"].iloc[i] < df["low"].iloc[i+1]:
            result.append((i, df["low"].iloc[i]))
    return result


# ═════════════════════════════════════════════════════════════
#  ① AMD — ACCUMULATION · MANIPULATION · DISTRIBUTION
#
#  Logique institutionnelle (Wyckoff + SMC moderne) :
#
#  ACCUMULATION  = range comprimé (faible volatilité H4)
#                  Les institutions accumulent des positions long
#                  → Range high/low clairement défini
#
#  MANIPULATION  = faux mouvement qui chasse les stops
#                  • Bull Manipulation : spike sous le range low (BSL sweep)
#                    → institutions achètent les stops des bears
#                  • Bear Manipulation : spike au-dessus du range high
#                    → institutions vendent les stops des bulls
#
#  DISTRIBUTION  = mouvement directionnel APRÈS la manipulation
#                  → C'est là qu'on trade : dans le sens institutionnel
#
#  Signal AMD :
#    Accumulation identifiée + Manipulation validée (sweep) → Long/Short
#    dans la phase Distribution avec confluence H4 + M15
# ═════════════════════════════════════════════════════════════

def detect_amd_phase(df_h4: pd.DataFrame) -> AmdPhase:
    """
    Détecte la phase AMD courante sur H4.

    Algorithme :
    1. Identifie le range des 20 dernières bougies H4
    2. Vérifie si le range est "comprimé" (ATR faible = accumulation)
    3. Détecte le sweep (manipulation) : spike H/L hors range + retour dedans
    4. Si sweep détecté → phase Distribution confirmée
    5. Direction : bullish si sweep du range LOW (chasse bears), bearish si sweep du HIGH

    Score de confiance (0–100) :
      • Range bien défini (plusieurs tests) : +30
      • Sweep clair (clôture dans le range après spike) : +30
      • Volume/impulsion post-sweep : +20
      • Biais H4 aligné : +20
    """
    if len(df_h4) < AMD_LOOKBACK + 5:
        return AmdPhase("unknown", "", "LONG", 0, 0, 0)

    # Fenêtre d'analyse : 50 dernières bougies H4
    window    = df_h4.iloc[-AMD_LOOKBACK:]
    atr_full  = (df_h4["high"] - df_h4["low"]).rolling(14).mean()
    atr_now   = atr_full.iloc[-1]

    # ── 1. RANGE (Accumulation zone) ──────────────────────────
    # On cherche la zone de range : les 20 dernières bougies AVANT les 10 dernières
    # (les 10 dernières = zone récente où manipulation/distribution peut se produire)
    range_window  = window.iloc[:30]   # bougies "historiques" du range
    recent_window = window.iloc[30:]   # bougies récentes (manipulation + distribution)

    range_high = range_window["high"].quantile(0.80)   # 80e percentile des hauts
    range_low  = range_window["low"].quantile(0.20)    # 20e percentile des bas
    range_size = range_high - range_low

    if range_size <= 0:
        return AmdPhase("unknown", "", "LONG", 0, 0, 0)

    # ── 2. COMPRESSION ATR (signature accumulation) ───────────
    atr_range    = (range_window["high"] - range_window["low"]).mean()
    atr_recent   = (recent_window["high"] - recent_window["low"]).mean() if len(recent_window) > 0 else atr_range
    is_compressed = atr_range < atr_now * 0.85   # volatilité du range < ATR actuel

    # ── 3. SWEEP DÉTECTION (Manipulation) ─────────────────────
    # Un sweep = dernières bougies H4 qui piquent hors du range PUIS reviennent
    sweep_up   = False  # spike au-dessus du range high → bear manipulation
    sweep_down = False  # spike en-dessous du range low → bull manipulation
    sweep_level = None

    for i in range(len(recent_window) - 1, max(len(recent_window) - 8, 0), -1):
        h = recent_window["high"].iloc[i]
        l = recent_window["low"].iloc[i]
        cl = recent_window["close"].iloc[i]

        # Bull Manipulation : spike sous range_low + retour au-dessus
        if l < range_low - atr_now * 0.1 and cl > range_low:
            sweep_down  = True
            sweep_level = range_low
            break
        # Bear Manipulation : spike au-dessus range_high + retour en-dessous
        if h > range_high + atr_now * 0.1 and cl < range_high:
            sweep_up    = True
            sweep_level = range_high
            break

    # ── 4. PHASE et DIRECTION ──────────────────────────────────
    if not sweep_up and not sweep_down:
        # Pas encore de manipulation détectée → accumulation en cours
        phase     = "accumulation"
        sub_phase = "range_forming"
        direction = "LONG"  # neutre pour l'instant
        confidence = 30 if is_compressed else 15
        reasons = ["📦 Accumulation en cours — range comprimé" if is_compressed
                   else "📦 Range en formation — accumulation possible"]
        return AmdPhase(phase, sub_phase, direction, confidence,
                        range_high, range_low, None, reasons)

    # Manipulation détectée !
    phase     = "distribution"
    direction = "LONG" if sweep_down else "SHORT"
    sub_phase = "bull_manipulation_complete" if sweep_down else "bear_manipulation_complete"

    # ── 5. CONFIANCE (scoring AMD) ────────────────────────────
    confidence = 0
    reasons    = []

    # Range bien défini
    if range_size > atr_now * 2:
        confidence += 30
        reasons.append(f"📦 Range AMD bien défini ({round(range_size, 5)})  (+30)")

    # Sweep propre
    if sweep_up or sweep_down:
        confidence += 35
        sweep_type = "Bull (sweep du bas)" if sweep_down else "Bear (sweep du haut)"
        reasons.append(f"🔥 Manipulation {sweep_type} complète @ {round(sweep_level, 5)}  (+35)")

    # Compression ATR = accumulation authentique
    if is_compressed:
        confidence += 20
        reasons.append("📊 ATR comprimé = accumulation institutionnelle  (+20)")

    # Post-sweep : impulsion (distribution en cours ?)
    last_close  = df_h4["close"].iloc[-1]
    last_open   = df_h4["open"].iloc[-1]
    post_impulse = abs(last_close - last_open) > atr_now * 0.8
    if post_impulse:
        confidence += 15
        reasons.append("⚡ Impulsion post-sweep détectée  (+15)")

    confidence = min(confidence, 100)

    return AmdPhase(
        phase=phase, sub_phase=sub_phase, direction=direction,
        confidence=confidence, range_high=range_high, range_low=range_low,
        sweep_level=sweep_level, reasons=reasons
    )


# ═════════════════════════════════════════════════════════════
#  ② SEPTUPLE TRACTION H4
#
#  N bougies consécutives dans la même direction sur H4
#  = momentum institutionnel fort = "train en marche"
#
#  Les institutions utilisent les retracements dans ce trend
#  pour rentrer, PAS contre le mouvement.
#
#  Setup : Septuple Traction H4 + retracement M15 50–61.8%
#          + FVG M5 dans la zone → ENTRÉE
#
#  Score bonus : +25 si 5+ bougies, +35 si 7+ bougies
# ═════════════════════════════════════════════════════════════

def detect_septuple_traction(df_h4: pd.DataFrame) -> dict:
    """
    Détecte le momentum institutionnel H4 (Septuple Traction).

    Critères STRICTS (institutionnel) :
    • Corps ≥ 50% de la bougie (peu de mèches = conviction)
    • Bougies consécutives (pas d'interruption)
    • Direction uniforme (all bullish ou all bearish)
    • Momentum croissant (chaque bougie ≥ 80% de la précédente)

    Retourne dict {detected, direction, count, strength, first_open, last_close}
    """
    if len(df_h4) < 10:
        return {"detected": False, "count": 0}

    atr = (df_h4["high"] - df_h4["low"]).rolling(14).mean().iloc[-1]

    # Cherche depuis la dernière bougie clôturée vers l'arrière
    max_streak      = 0
    best_direction  = None
    best_first_open = None
    best_last_close = None

    # Teste les 20 dernières bougies
    search_end = min(len(df_h4) - 1, 20)  # dernière bougie en cours = exclue

    for start in range(1, search_end):
        direction = None
        count     = 0
        momentum_ok = True
        prev_body = None

        for i in range(start, search_end + 1):
            idx = -(i + 1)  # bougie clôturée (on évite la courante)
            if abs(idx) > len(df_h4):
                break

            o  = df_h4["open"].iloc[idx]
            h  = df_h4["high"].iloc[idx]
            l  = df_h4["low"].iloc[idx]
            cl = df_h4["close"].iloc[idx]

            body      = abs(cl - o)
            rng       = h - l
            is_bull   = cl > o
            body_ratio = body / rng if rng > 0 else 0

            # Corps minimum : 50% de la bougie
            if body_ratio < 0.50:
                break

            cur_direction = "LONG" if is_bull else "SHORT"

            if direction is None:
                direction = cur_direction
            elif cur_direction != direction:
                break

            # Momentum : corps ≥ 80% du précédent (pas de ralentissement brutal)
            if prev_body is not None and body < prev_body * 0.60:
                momentum_ok = False
                break

            count    += 1
            prev_body = body

            if count > max_streak:
                max_streak      = count
                best_direction  = direction
                best_first_open = df_h4["open"].iloc[-(start + count)]
                best_last_close = df_h4["close"].iloc[-(start + 1)]

        if count >= SEPTUPLE_MIN_CANDLES:
            break

    if max_streak < SEPTUPLE_MIN_CANDLES:
        return {"detected": False, "count": max_streak}

    # Force du mouvement
    strength = "EXTREME" if max_streak >= 7 else ("FORT" if max_streak >= 6 else "MODÉRÉ")

    return {
        "detected"   : True,
        "direction"  : best_direction,
        "count"      : max_streak,
        "strength"   : strength,
        "first_open" : best_first_open,
        "last_close" : best_last_close,
    }


# ═════════════════════════════════════════════════════════════
#  ③ SUPPLY & DEMAND ZONES
#
#  Une vraie zone Supply/Demand institutionnelle n'est PAS
#  simplement un Order Block. Elle est créée par :
#
#  DEMAND ZONE = base d'un mouvement haussier impulsif
#    → Dernière consolidation AVANT la grande bougie haussière
#    → Prix revient tester cette zone → acheteurs institutionnels
#
#  SUPPLY ZONE = base d'un mouvement baissier impulsif
#    → Dernière consolidation AVANT la grande bougie baissière
#    → Prix revient tester cette zone → vendeurs institutionnels
#
#  Critères de qualité :
#    • Taille de la bougie impulsive ≥ ATR × 1.5
#    • La zone n'a pas encore été "mitigée" (prix n'est pas revenu)
#    • Fresh zone (testée 0 fois) > Tested once > Tested twice (trop faible)
# ═════════════════════════════════════════════════════════════

def detect_supply_demand_zones(df: pd.DataFrame, direction: str) -> list[SupplyDemandZone]:
    """
    Détecte les zones Supply (bearish) et Demand (bullish) institutionnelles.

    Algorithme :
    1. Cherche les bougies impulsives (corps ≥ ATR × 1.5)
    2. La zone = corps de la DERNIÈRE PETITE bougie avant l'impulsion
       (c'est là que les institutions ont placé leurs ordres)
    3. Vérifie que la zone n'est pas mitigée (prix n'y est pas revenu)
    4. Retourne les zones actives dans le sens du biais
    """
    if len(df) < 20:
        return []

    atr = (df["high"] - df["low"]).rolling(14).mean()
    zones: list[SupplyDemandZone] = []
    zone_type = "supply" if direction == "SHORT" else "demand"

    for i in range(2, len(df) - 2):
        o  = df["open"].iloc[i]
        cl = df["close"].iloc[i]
        body = abs(cl - o)
        atr_i = atr.iloc[i]

        if atr_i <= 0 or np.isnan(atr_i):
            continue

        # Bougie impulsive ?
        if body < atr_i * SD_MIN_IMPULSE_RATIO:
            continue

        is_bull_impulse = cl > o
        # Direction correcte ?
        if direction == "LONG"  and not is_bull_impulse:
            continue
        if direction == "SHORT" and is_bull_impulse:
            continue

        # Zone = corps de la bougie JUSTE AVANT l'impulsion (base institutionnelle)
        base_idx = i - 1
        if base_idx < 0:
            continue

        base_o  = df["open"].iloc[base_idx]
        base_cl = df["close"].iloc[base_idx]
        base_h  = df["high"].iloc[base_idx]
        base_l  = df["low"].iloc[base_idx]

        zone_top    = max(base_o, base_cl, base_h)
        zone_bottom = min(base_o, base_cl, base_l)

        # La zone ne doit pas être mitigée (prix n'est pas REVENU dedans après l'impulsion)
        mitigated = False
        for j in range(i + 1, len(df)):
            close_j = df["close"].iloc[j]
            if zone_bottom <= close_j <= zone_top:
                mitigated = True
                break

        if not mitigated:
            zones.append(SupplyDemandZone(
                zone_type=zone_type,
                top=zone_top,
                bottom=zone_bottom,
                index=base_idx,
                impulse_size=body / atr_i,   # ratio force de l'impulsion
                tested=False
            ))

    # Tri par proximité au prix actuel
    current_price = df["close"].iloc[-1]
    zones.sort(key=lambda z: abs(current_price - (z.top + z.bottom) / 2))

    return zones[:5]   # retourne les 5 zones les plus proches


def price_in_sd_zone(price: float, zones: list[SupplyDemandZone],
                     atr: float) -> Optional[SupplyDemandZone]:
    """
    Retourne la première zone S/D dans laquelle le prix se trouve.
    Tolérance : ±15% de l'ATR autour de la zone.
    """
    buf = atr * SD_ZONE_BUFFER
    for zone in zones:
        if (zone.bottom - buf) <= price <= (zone.top + buf):
            return zone
    return None


# ═════════════════════════════════════════════════════════════
#  ④ LIQUIDITY MAP AVANCÉE
#
#  Les institutions traquent les liquidités RÉELLES, pas juste
#  les swing highs/lows. On identifie :
#
#  BSL (Buy Side Liquidity)  = stops des SHORTS au-dessus des highs
#  SSL (Sell Side Liquidity) = stops des LONGS en-dessous des lows
#
#  Equal Highs (EQH) = double top = pool de liquidité visé par les institutions
#  Equal Lows  (EQL) = double bottom = idem en sens inverse
#
#  Liquidity Void = zone de déséquilibre (FVG = liquidity void)
#
#  Intraday Liquidity = high/low du jour précédent (PDH/PDL)
#                       = première cible intraday des institutions
# ═════════════════════════════════════════════════════════════

@dataclass
class LiquidityMap:
    bsl_levels:  list[float]   # Buy Side Liquidity (above highs)
    ssl_levels:  list[float]   # Sell Side Liquidity (below lows)
    eqh_levels:  list[float]   # Equal Highs
    eql_levels:  list[float]   # Equal Lows
    pdh:         Optional[float]  # Previous Day High
    pdl:         Optional[float]  # Previous Day Low
    swept_bsl:   bool          # BSL récemment sweepée (signal SHORT)
    swept_ssl:   bool          # SSL récemment sweepée (signal LONG)
    nearest_bsl: Optional[float]
    nearest_ssl: Optional[float]


def build_liquidity_map(df_h4: pd.DataFrame, df_ltf: pd.DataFrame) -> LiquidityMap:
    """
    Construit la carte complète de liquidité sur H4 + LTF.

    BSL/SSL : 5 derniers swing H/L H4 significatifs
    EQH/EQL : niveaux proches à ±0.02% (institutionnellement = "même niveau")
    PDH/PDL  : high/low de la session précédente H4 (4 bougies = 1 jour environ)
    Swept    : spike + retour dans la dernière bougie LTF
    """
    # ── SWING HIGHS / LOWS H4 ─────────────────────────────────
    shs = swing_highs(df_h4)
    sls = swing_lows(df_h4)

    bsl_levels = [v for _, v in shs[-8:]]
    ssl_levels = [v for _, v in sls[-8:]]

    # ── EQUAL HIGHS / LOWS (EQH/EQL) ──────────────────────────
    # Deux niveaux sont "égaux" si leur écart est < 0.025%
    eqh_levels = []
    eql_levels = []
    tolerance  = 0.00025   # 2.5 pips sur forex

    for i, h1 in enumerate(bsl_levels):
        for h2 in bsl_levels[i+1:]:
            if abs(h1 - h2) / max(h1, 0.0001) < tolerance:
                eqh_levels.append((h1 + h2) / 2)

    for i, l1 in enumerate(ssl_levels):
        for l2 in ssl_levels[i+1:]:
            if abs(l1 - l2) / max(l1, 0.0001) < tolerance:
                eql_levels.append((l1 + l2) / 2)

    # ── PDH / PDL (Previous Day High/Low) ─────────────────────
    # H4 : 6 bougies ≈ 24h. On prend les 6 bougies précédentes.
    pdh, pdl = None, None
    if len(df_h4) >= 12:
        pd_window = df_h4.iloc[-12:-6]
        pdh = pd_window["high"].max()
        pdl = pd_window["low"].min()

    # ── SWEPT BSL/SSL ? ───────────────────────────────────────
    price    = df_ltf["close"].iloc[-1]
    last_h   = df_ltf["high"].iloc[-2]   # dernière bougie clôturée
    last_l   = df_ltf["low"].iloc[-2]
    last_c   = df_ltf["close"].iloc[-2]
    atr      = (df_ltf["high"] - df_ltf["low"]).rolling(14).mean().iloc[-1]

    swept_bsl = False
    swept_ssl = False

    for level in bsl_levels[-5:]:
        if last_h > level + atr * 0.05 and last_c < level:
            swept_bsl = True
            break

    for level in ssl_levels[-5:]:
        if last_l < level - atr * 0.05 and last_c > level:
            swept_ssl = True
            break

    # ── NEAREST BSL/SSL ───────────────────────────────────────
    above_bsl = [l for l in bsl_levels if l > price]
    below_ssl = [l for l in ssl_levels if l < price]
    nearest_bsl = min(above_bsl) if above_bsl else None
    nearest_ssl = max(below_ssl) if below_ssl else None

    return LiquidityMap(
        bsl_levels=bsl_levels, ssl_levels=ssl_levels,
        eqh_levels=eqh_levels, eql_levels=eql_levels,
        pdh=pdh, pdl=pdl,
        swept_bsl=swept_bsl, swept_ssl=swept_ssl,
        nearest_bsl=nearest_bsl, nearest_ssl=nearest_ssl,
    )


# ═════════════════════════════════════════════════════════════
#  ⑤ BOUGIES D'ENTRÉE INSTITUTIONNELLES
#
#  Les grandes institutions n'entrent PAS sur n'importe quelle bougie.
#  Les setups d'entrée qui donnent le meilleur timing :
#
#  1. DISPLACEMENT CANDLE
#     Corps ≥ ATR × 2 + clôture dans le sens du trade
#     = bougie de "déplacement institutionnel" qui efface le désordre
#
#  2. ORDER FLOW SHIFT (OFS)
#     Série de 3 bougies : bear → bull → close above bear high (LONG)
#     = renversement micro-structure = premier signal d'intent
#
#  3. IMBALANCE CANDLE (FVG micro)
#     Gap entre bougie[i-2].low et bougie[i].high > 0 (bullish)
#     = déséquilibre = les institutions ont acheté agressivement
#
#  4. REJECTION WICK
#     Mèche ≥ corps × 3 dans le sens opposé = rejet institutionnel
#     Seule une mèche AVEC volume = authentique (pas de fakeout)
#
#  5. ENGULFING INSTITUTIONNEL
#     Close > open + close > prev_high (bullish engulfing fort)
#     = absorbe TOUT le mouvement précédent = conviction totale
# ═════════════════════════════════════════════════════════════

@dataclass
class EntryCandle:
    candle_type: str    # "displacement" | "ofs" | "imbalance" | "rejection" | "engulfing"
    quality:     str    # "premium" | "standard"
    score_bonus: int
    index:       int


def detect_institutional_entry_candles(df: pd.DataFrame,
                                        direction: str) -> list[EntryCandle]:
    """
    Détecte les bougies d'entrée institutionnelles sur les 5 dernières bougies
    CLÔTURÉES (on évite la bougie courante = données incomplètes).

    Retourne toutes les bougies valides détectées (peut en avoir plusieurs).
    """
    if len(df) < 6:
        return []

    atr     = (df["high"] - df["low"]).rolling(14).mean().iloc[-1]
    entries = []

    for i in range(-2, -6, -1):   # [-2, -3, -4, -5] = 4 dernières clôturées
        if abs(i) > len(df) - 1:
            break

        o   = df["open"].iloc[i]
        h   = df["high"].iloc[i]
        l   = df["low"].iloc[i]
        cl  = df["close"].iloc[i]
        body        = abs(cl - o)
        full_range  = h - l
        upper_wick  = h - max(o, cl)
        lower_wick  = min(o, cl) - l
        is_bull     = cl > o

        # ── 1. DISPLACEMENT ───────────────────────────────────
        if body >= atr * 1.8:
            if (direction == "LONG" and is_bull) or (direction == "SHORT" and not is_bull):
                quality = "premium" if body >= atr * 2.5 else "standard"
                entries.append(EntryCandle("displacement", quality, 20 if quality == "premium" else 15, i))
                continue

        # ── 2. ORDER FLOW SHIFT ───────────────────────────────
        if abs(i) < len(df) - 2:
            prev_o  = df["open"].iloc[i - 1]
            prev_cl = df["close"].iloc[i - 1]
            if direction == "LONG":
                # Bear → Bull → close above prev_high
                prev_is_bear = prev_cl < prev_o
                if prev_is_bear and is_bull and cl > df["high"].iloc[i - 1]:
                    entries.append(EntryCandle("ofs", "premium", 18, i))
                    continue
            elif direction == "SHORT":
                prev_is_bull = prev_cl > prev_o
                if prev_is_bull and not is_bull and cl < df["low"].iloc[i - 1]:
                    entries.append(EntryCandle("ofs", "premium", 18, i))
                    continue

        # ── 3. IMBALANCE (Micro-FVG) ──────────────────────────
        if abs(i) >= 2 and abs(i) < len(df) - 2:
            if direction == "LONG":
                prev2_low = df["low"].iloc[i - 2]
                if h > prev2_low and (h - prev2_low) / max(h, 0.0001) > 0.0001:
                    entries.append(EntryCandle("imbalance", "standard", 12, i))
                    continue
            elif direction == "SHORT":
                prev2_high = df["high"].iloc[i - 2]
                if l < prev2_high and (prev2_high - l) / max(l, 0.0001) > 0.0001:
                    entries.append(EntryCandle("imbalance", "standard", 12, i))
                    continue

        # ── 4. REJECTION WICK ─────────────────────────────────
        if body > 0:
            if direction == "LONG" and lower_wick >= body * 2.5 and is_bull:
                quality = "premium" if lower_wick >= body * 4 else "standard"
                entries.append(EntryCandle("rejection", quality, 15 if quality == "premium" else 10, i))
                continue
            elif direction == "SHORT" and upper_wick >= body * 2.5 and not is_bull:
                quality = "premium" if upper_wick >= body * 4 else "standard"
                entries.append(EntryCandle("rejection", quality, 15 if quality == "premium" else 10, i))
                continue

        # ── 5. ENGULFING INSTITUTIONNEL ───────────────────────
        if abs(i) < len(df) - 1:
            prev_h = df["high"].iloc[i - 1]
            prev_l = df["low"].iloc[i - 1]
            if direction == "LONG" and is_bull and cl > prev_h:
                entries.append(EntryCandle("engulfing", "premium", 20, i))
            elif direction == "SHORT" and not is_bull and cl < prev_l:
                entries.append(EntryCandle("engulfing", "premium", 20, i))

    return entries


# ═════════════════════════════════════════════════════════════
#  DÉTECTEURS CLASSIQUES (BOS, FVG, OB, Breaker, Liquidité)
#  — Conservés et améliorés depuis v2
# ═════════════════════════════════════════════════════════════

def htf_bias(df: pd.DataFrame) -> str:
    """Biais H4 via EMA + HH/LL (20 bougies)."""
    if len(df) < 20:
        return "NEUTRAL"
    highs  = df["high"].iloc[-20:].values
    lows   = df["low"].iloc[-20:].values
    closes = df["close"].iloc[-20:].values
    ema    = np.convolve(closes, np.ones(8) / 8, mode="valid")
    trend_up  = closes[-1] > ema[-1]
    last_hh   = highs[-1] < highs[-5:].max()
    if not trend_up and last_hh:
        return "BEARISH"
    elif trend_up and not last_hh:
        return "BULLISH"
    return "NEUTRAL"


def detect_bos(df: pd.DataFrame) -> list[dict]:
    bos_list = []
    lookback = 10
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


def detect_fvg(df: pd.DataFrame) -> list[FVG]:
    fvgs = []
    for i in range(2, len(df)):
        mid_price = df["close"].iloc[i]
        top    = df["high"].iloc[i - 2]
        bottom = df["low"].iloc[i]
        if bottom > top and (bottom - top) / mid_price > FVG_MIN_RATIO:
            fvgs.append(FVG("bearish", bottom, top, i))
        top    = df["high"].iloc[i]
        bottom = df["low"].iloc[i - 2]
        if top > bottom and (top - bottom) / mid_price > FVG_MIN_RATIO:
            fvgs.append(FVG("bullish", top, bottom, i))
    return fvgs


def detect_order_blocks(df: pd.DataFrame, bos_list: list[dict]) -> list[OrderBlock]:
    obs = []
    for bos in bos_list[-5:]:
        idx = bos["index"]
        if idx < OB_LOOKBACK:
            continue
        if bos["type"] == "bearish":
            for j in range(idx - 1, idx - OB_LOOKBACK - 1, -1):
                if df["close"].iloc[j] > df["open"].iloc[j]:
                    obs.append(OrderBlock("bearish", df["high"].iloc[j], df["low"].iloc[j], j))
                    break
        elif bos["type"] == "bullish":
            for j in range(idx - 1, idx - OB_LOOKBACK - 1, -1):
                if df["close"].iloc[j] < df["open"].iloc[j]:
                    obs.append(OrderBlock("bullish", df["high"].iloc[j], df["low"].iloc[j], j))
                    break
    return obs


def detect_breaker_blocks(df: pd.DataFrame, bos_list: list[dict]) -> list[dict]:
    """Breaker Block = OB mitiqué qui flippe de direction (amélioré v3)."""
    breakers = []
    for bos in bos_list[-6:]:
        idx = bos["index"]
        if idx < OB_LOOKBACK + 2 or idx + 3 >= len(df):
            continue
        for j in range(idx - 1, max(idx - OB_LOOKBACK - 1, 0), -1):
            is_bull = df["close"].iloc[j] > df["open"].iloc[j]
            ob_hi   = df["high"].iloc[j]
            ob_lo   = df["low"].iloc[j]
            if bos["type"] == "bearish" and is_bull:
                post_high = df["high"].iloc[idx: min(idx + 15, len(df))].max()
                if ob_lo <= post_high <= ob_hi * 1.001:
                    breakers.append({"direction": "bearish", "top": ob_hi,
                                      "bottom": ob_lo, "index": j})
                    break
            elif bos["type"] == "bullish" and not is_bull:
                post_low = df["low"].iloc[idx: min(idx + 15, len(df))].min()
                if ob_lo * 0.999 <= post_low <= ob_hi:
                    breakers.append({"direction": "bullish", "top": ob_hi,
                                      "bottom": ob_lo, "index": j})
                    break
    return breakers


def detect_liquidity_sweep(df: pd.DataFrame) -> dict:
    result  = {"bullish_sweep": False, "bearish_sweep": False, "level": None}
    window  = df.iloc[-30:]
    swing_high = window["high"].max()
    swing_low  = window["low"].min()
    last_high  = df["high"].iloc[-1]
    last_low   = df["low"].iloc[-1]
    last_close = df["close"].iloc[-1]
    if last_high > swing_high * (1 + LIQ_THRESHOLD) and last_close < swing_high:
        result["bearish_sweep"] = True
        result["level"]         = swing_high
    if last_low < swing_low * (1 - LIQ_THRESHOLD) and last_close > swing_low:
        result["bullish_sweep"] = True
        result["level"]         = swing_low
    return result


def active_fvg(df: pd.DataFrame, fvgs: list[FVG], direction: str) -> Optional[FVG]:
    price = df["close"].iloc[-1]
    for fvg in reversed(fvgs):
        if fvg.direction != direction:
            continue
        lo, hi = min(fvg.top, fvg.bottom), max(fvg.top, fvg.bottom)
        if lo <= price <= hi:
            return fvg
    return None


def is_fvg_unmitigated(df: pd.DataFrame, fvg: FVG) -> bool:
    if fvg.index + 1 >= len(df):
        return True
    lo = min(fvg.top, fvg.bottom)
    hi = max(fvg.top, fvg.bottom)
    for i in range(fvg.index + 1, len(df)):
        if lo <= df["close"].iloc[i] <= hi:
            return False
    return True


def detect_confirmation_candle(df: pd.DataFrame, direction: str) -> bool:
    if len(df) < 4:
        return False
    for i in range(-2, -5, -1):
        o  = df["open"].iloc[i]
        h  = df["high"].iloc[i]
        l  = df["low"].iloc[i]
        cl = df["close"].iloc[i]
        body       = abs(cl - o)
        if body == 0:
            continue
        upper_wick = h - max(o, cl)
        lower_wick = min(o, cl) - l
        if direction == "LONG":
            if cl > o and i > -3:
                prev_o = df["open"].iloc[i - 1]
                prev_c = df["close"].iloc[i - 1]
                if prev_c < prev_o and cl > prev_o and o < prev_c:
                    return True
            if lower_wick >= body * 2 and cl > o:
                return True
        elif direction == "SHORT":
            if cl < o and i > -3:
                prev_o = df["open"].iloc[i - 1]
                prev_c = df["close"].iloc[i - 1]
                if prev_c > prev_o and cl < prev_o and o > prev_c:
                    return True
            if upper_wick >= body * 2 and cl < o:
                return True
    return False


# ═════════════════════════════════════════════════════════════
#  MOTEUR DE SCORE v3
#  Architecture :
#    Base H4 (biais + AMD + Septuple)        → 0–45 pts
#    Structure M15 (BOS + OB + Liquidité)    → 0–30 pts
#    Entrée M5 (FVG + S/D Zone + Bougie)     → 0–25 pts
#    Total max = 100 pts
# ═════════════════════════════════════════════════════════════

def compute_score_v3(
    # H4
    bias_aligned:       bool = False,
    amd_detected:       bool = False,
    amd_confidence:     int  = 0,
    septuple_detected:  bool = False,
    septuple_count:     int  = 0,
    # M15
    mtf_bos:            bool = False,
    mtf_ob:             bool = False,
    liquidity_taken:    bool = False,
    breaker_block:      bool = False,
    bsl_ssl_swept:      bool = False,   # BSL ou SSL sweepée (liquidity map)
    eqh_eql_present:    bool = False,   # Equal Highs/Lows = pool de liquidité
    # M5 Entry
    ltf_fvg:            bool = False,
    fvg_unmitigated:    bool = False,
    sd_zone_active:     bool = False,   # Supply/Demand zone active
    entry_candle_score: int  = 0,       # bonus des bougies institutionnelles
    older_block_htf:    bool = False,   # OB H4 actif
) -> tuple[int, list[str]]:
    score   = 0
    reasons = []

    # ── H4 BASE (45 pts max) ──────────────────────────────────
    if bias_aligned:
        score += 15
        reasons.append("✅ Biais H4 aligné  (+15)")

    if amd_detected:
        amd_pts = min(20, int(amd_confidence * 0.20))
        score  += amd_pts
        reasons.append(f"🔮 AMD confirmé (confiance {amd_confidence}%)  (+{amd_pts})")

    if septuple_detected:
        sep_pts = 10 if septuple_count >= 7 else (8 if septuple_count >= 6 else 6)
        score  += sep_pts
        reasons.append(f"⚡ Septuple Traction H4 ({septuple_count} bougies)  (+{sep_pts})")

    # ── M15 STRUCTURE (30 pts max) ────────────────────────────
    if mtf_bos:
        score += 10
        reasons.append("✅ BOS M15 confirmé  (+10)")

    if mtf_ob:
        score += 7
        reasons.append("✅ Order Block M15 validé  (+7)")

    if liquidity_taken:
        score += 8
        reasons.append("✅ Liquidité M15 prise (stop hunt)  (+8)")

    if breaker_block:
        score += 5
        reasons.append("🔥 Breaker Block M15 détecté  (+5)")

    if bsl_ssl_swept:
        score += 8
        reasons.append("💧 BSL/SSL sweepée — pool de liquidité visé  (+8)")

    if eqh_eql_present:
        score += 4
        reasons.append("⚡ Equal High/Low (EQH/EQL) = liquidité institutionnelle  (+4)")

    # ── M5 ENTRÉE (25 pts max) ────────────────────────────────
    if sd_zone_active:
        score += 12
        reasons.append("🏛️ Prix dans zone Supply/Demand institutionnelle  (+12)")

    if ltf_fvg:
        score += 6
        reasons.append("📍 FVG M5 actif — zone de valeur  (+6)")

    if fvg_unmitigated:
        score += 3
        reasons.append("✅ FVG valid non mitiqué  (+3)")

    if older_block_htf:
        score += 5
        reasons.append("🏛️ Older Block H4 actif — confluence HTF  (+5)")

    # Bonus bougies institutionnelles (max 20 pts plafonné)
    if entry_candle_score > 0:
        ec_pts = min(entry_candle_score, 20)
        score += ec_pts
        reasons.append(f"🕯️ Bougie d'entrée institutionnelle  (+{ec_pts})")

    return min(score, 100), reasons


# ─────────────────────────────────────────────────────────────
#  CALCUL NIVEAUX — ENTRY / SL / TP
# ─────────────────────────────────────────────────────────────

def compute_sl_tp_v3(
    df_m5:     pd.DataFrame,
    df_m15:    pd.DataFrame,
    direction: str,
    ob:        Optional[OrderBlock],
    fvg:       Optional[FVG],
    sd_zone:   Optional[SupplyDemandZone],
    liq_map:   Optional[LiquidityMap],
    symbol:    str = "",
) -> tuple[float, float, float, float]:
    """
    Entry / SL / TP v3 — utilise les zones institutionnelles réelles.

    ENTRÉE (priorité décroissante) :
      1. Milieu de la zone Supply/Demand
      2. Milieu du FVG M5
      3. Close M5 courant

    STOP LOSS :
      LONG  : sous le bas de la Demand Zone / OB / FVG  + buffer ATR×0.4
      SHORT : au-dessus du haut de la Supply Zone / OB / FVG  + buffer ATR×0.4

    TAKE PROFIT :
      Priorité 1 : BSL/SSL nearest (liquidité institutionnelle réelle)
      Priorité 2 : PDH/PDL (previous day high/low)
      Priorité 3 : prochain swing H/L non cassé
      Priorité 4 : entry ± ATR × 4 (fallback)
    """
    atr    = (df_m5["high"] - df_m5["low"]).rolling(14).mean().iloc[-1]
    close  = df_m5["close"].iloc[-1]
    spread = get_spread(symbol) if symbol else 0.0
    dec    = 2 if close > 100 else 5
    buf    = max(atr * 0.45, spread * 3.0)

    # ── 1. ENTRÉE ─────────────────────────────────────────────
    if sd_zone is not None:
        entry = round((sd_zone.top + sd_zone.bottom) / 2, dec)
    elif fvg is not None:
        entry = round((max(fvg.top, fvg.bottom) + min(fvg.top, fvg.bottom)) / 2, dec)
    else:
        entry = round(close, dec)

    # ── 2. STOP LOSS ──────────────────────────────────────────
    if direction == "LONG":
        if sd_zone:
            sl = round(sd_zone.bottom - buf, dec)
        elif ob:
            sl = round(ob.bottom - buf, dec)
        elif fvg:
            sl = round(min(fvg.top, fvg.bottom) - buf, dec)
        else:
            sl = round(entry - atr * 1.8, dec)
    else:  # SHORT
        if sd_zone:
            sl = round(sd_zone.top + buf, dec)
        elif ob:
            sl = round(ob.top + buf, dec)
        elif fvg:
            sl = round(max(fvg.top, fvg.bottom) + buf, dec)
        else:
            sl = round(entry + atr * 1.8, dec)

    risk = abs(entry - sl)
    if risk <= 0:
        return entry, sl, entry, 0.0

    # ── 3. TAKE PROFIT — liquidité institutionnelle réelle ────
    tp = None

    if liq_map is not None:
        if direction == "LONG" and liq_map.nearest_bsl and liq_map.nearest_bsl > entry + risk:
            tp = round(liq_map.nearest_bsl, dec)
        elif direction == "SHORT" and liq_map.nearest_ssl and liq_map.nearest_ssl < entry - risk:
            tp = round(liq_map.nearest_ssl, dec)

        # PDH/PDL comme TP si plus favorable
        if direction == "LONG" and liq_map.pdh and liq_map.pdh > entry + risk:
            if tp is None or liq_map.pdh < tp:  # plus proche = plus conservateur
                tp = round(liq_map.pdh, dec)
        elif direction == "SHORT" and liq_map.pdl and liq_map.pdl < entry - risk:
            if tp is None or liq_map.pdl > tp:
                tp = round(liq_map.pdl, dec)

    # Fallback : swing H/L sur M15
    if tp is None:
        window50 = df_m15.iloc[-50:]
        if direction == "LONG":
            cands = sorted([
                window50["high"].iloc[i]
                for i in range(len(window50) - 2, 0, -1)
                if window50["high"].iloc[i] > window50["high"].iloc[i-1]
                   and window50["high"].iloc[i] > window50["high"].iloc[i+1]
                   and window50["high"].iloc[i] > entry + risk
            ], reverse=True)
            tp_nat = cands[-1] if cands else entry + atr * 5
            tp = round(max(tp_nat, entry + atr * 4), dec)
        else:
            cands = sorted([
                window50["low"].iloc[i]
                for i in range(len(window50) - 2, 0, -1)
                if window50["low"].iloc[i] < window50["low"].iloc[i-1]
                   and window50["low"].iloc[i] < window50["low"].iloc[i+1]
                   and window50["low"].iloc[i] < entry - risk
            ])
            tp_nat = cands[0] if cands else entry - atr * 5
            tp = round(min(tp_nat, entry - atr * 4), dec)

    # ── 4. RR net ─────────────────────────────────────────────
    if direction == "LONG":
        gain_net = (tp - entry) - spread
    else:
        gain_net = (entry - tp) - spread

    rr_net = round(gain_net / risk, 2) if gain_net > 0 and risk > 0 else 0.0
    return entry, sl, tp, rr_net


# ═════════════════════════════════════════════════════════════
#  MOTEUR PRINCIPAL v3 — H4 → M15 → M5
# ═════════════════════════════════════════════════════════════

def analyse(symbol: str, htf: str = HTF, ltf: str = LTF,
            silent: bool = False) -> Optional[Signal]:
    mtf = MTF

    if not silent:
        print(f"\n{c('═'*65, 'cyan')}")
        print(f"  {c('SMC ENGINE v3', 'yellow')}  —  {c(symbol, 'white')}  "
              f"{c(datetime.now(timezone.utc).strftime('%H:%M UTC'), 'cyan')}")
        print(f"  {c('H4 → M15 → M5  |  AMD + Septuple + Supply/Demand', 'cyan')}")
        print(c("═" * 65, "cyan"))

    # ── Téléchargement H4 / M15 / M5 ────────────────────────
    df_htf = fetch(symbol, htf, period="30d")   # H4 = 30j pour AMD
    df_mtf = fetch(symbol, mtf, period="5d")
    df_ltf = fetch(symbol, ltf, period="2d")

    if df_htf.empty or df_mtf.empty or df_ltf.empty:
        if not silent:
            print(c("  ✗ Données indisponibles.", "red"))
        return None

    # ── Filtre volatilité ────────────────────────────────────
    vol_ok, vol_reason = check_volatility(symbol, df_ltf)
    if not vol_ok:
        if not silent:
            print(c(f"  ⛔ Skip : {vol_reason}", "yellow"))
        return None

    # ─────────────────────────────────────────────────────────
    #  H4 : Biais + AMD + Septuple Traction
    # ─────────────────────────────────────────────────────────
    bias      = htf_bias(df_htf)
    direction = "SHORT" if bias == "BEARISH" else ("LONG" if bias == "BULLISH" else None)

    if not silent:
        col = "red" if bias == "BEARISH" else ("green" if bias == "BULLISH" else "yellow")
        print(f"\n  {'📊 Biais H4':<28} {c(bias, col)}")

    if direction is None:
        if not silent:
            print(c("  ✗ Biais NEUTRAL — ignoré.", "yellow"))
        return None

    # ── AMD ───────────────────────────────────────────────────
    amd = detect_amd_phase(df_htf)
    amd_ok    = (amd.phase == "distribution" and amd.direction == direction
                 and amd.confidence >= 60)
    amd_conf  = amd.confidence if amd_ok else 0

    if not silent:
        amd_col = "green" if amd_ok else "yellow"
        print(f"  {'🔮 AMD Phase':<28} {c(amd.phase.upper(), amd_col)}"
              f"  {c(amd.sub_phase, 'white') if amd.sub_phase else ''}"
              f"  conf={amd.confidence}%")

    # ── Septuple Traction ─────────────────────────────────────
    sept = detect_septuple_traction(df_htf)
    sept_ok    = sept["detected"] and sept.get("direction") == direction
    sept_count = sept.get("count", 0)

    if not silent:
        sept_col = "green" if sept_ok else "white"
        if sept_ok:
            sept_strength = sept.get("strength", "")
            print(f"  {'⚡ Septuple Traction H4':<28} {c(str(sept_count) + ' bougies — ' + sept_strength, sept_col)}")
        else:
            print(f"  {'⚡ Septuple Traction H4':<28} {c('Non détecté', 'white')}")

    # ── Liquidity Map ─────────────────────────────────────────
    liq_map = build_liquidity_map(df_htf, df_ltf)
    bsl_ssl_swept = (liq_map.swept_bsl and direction == "SHORT") or \
                    (liq_map.swept_ssl and direction == "LONG")
    eqh_eql_ok = bool(liq_map.eqh_levels or liq_map.eql_levels)

    if not silent:
        print(f"  {'💧 BSL/SSL Sweepée':<28} {c('✓', 'green') if bsl_ssl_swept else c('✗', 'red')}")
        print(f"  {'⚡ EQH/EQL présent':<28} {c('✓', 'green') if eqh_eql_ok else c('✗', 'red')}")

    # ─────────────────────────────────────────────────────────
    #  M15 : Structure, BOS, OB, Breaker
    # ─────────────────────────────────────────────────────────
    bos_mtf    = detect_bos(df_mtf)
    obs_mtf    = detect_order_blocks(df_mtf, bos_mtf)
    liq_mtf    = detect_liquidity_sweep(df_mtf)
    bkr_mtf    = detect_breaker_blocks(df_mtf, bos_mtf)

    last_bos_mtf  = bos_mtf[-1] if bos_mtf else None
    mtf_bos_ok    = last_bos_mtf is not None and last_bos_mtf["type"] == bias.lower()
    mtf_ob_ok     = any(o.direction == bias.lower() for o in obs_mtf)
    liq_taken     = liq_mtf["bearish_sweep"] if direction == "SHORT" else liq_mtf["bullish_sweep"]
    breaker_ok    = any(b["direction"] == bias.lower() for b in bkr_mtf)

    ob_mtf_match = next((o for o in reversed(obs_mtf) if o.direction == bias.lower()), None)

    if not silent:
        def tick(v): return c("✓", "green") if v else c("✗", "red")
        print(f"\n  {'BOS M15':<28} {tick(mtf_bos_ok)}")
        print(f"  {'OB M15':<28} {tick(mtf_ob_ok)}")
        print(f"  {'Liquidité prise M15':<28} {tick(liq_taken)}")
        print(f"  {'Breaker Block M15':<28} {tick(breaker_ok)}")

    # ─────────────────────────────────────────────────────────
    #  M5 : FVG, OB, Supply/Demand Zones, Bougies institutionnelles
    # ─────────────────────────────────────────────────────────
    bos_ltf  = detect_bos(df_ltf)
    fvgs_ltf = detect_fvg(df_ltf)
    obs_ltf  = detect_order_blocks(df_ltf, bos_ltf)

    fvg_active    = active_fvg(df_ltf, fvgs_ltf, bias.lower())
    ltf_fvg_ok    = fvg_active is not None
    fvg_unmit_ok  = is_fvg_unmitigated(df_ltf, fvg_active) if fvg_active else False
    ob_ltf_match  = next((o for o in reversed(obs_ltf) if o.direction == bias.lower()), None)

    # Supply & Demand Zones M5
    sd_zones   = detect_supply_demand_zones(df_ltf, direction)
    price_now  = df_ltf["close"].iloc[-1]
    atr_m5     = (df_ltf["high"] - df_ltf["low"]).rolling(14).mean().iloc[-1]
    sd_active  = price_in_sd_zone(price_now, sd_zones, atr_m5)
    sd_ok      = sd_active is not None

    # Older Block H4
    bos_htf    = detect_bos(df_htf)
    obs_htf    = detect_order_blocks(df_htf, bos_htf)
    older_block = any(
        o.direction == bias.lower() and
        min(o.top, o.bottom) <= price_now <= max(o.top, o.bottom)
        for o in obs_htf
    )

    # Bougies d'entrée institutionnelles
    entry_candles = detect_institutional_entry_candles(df_ltf, direction)
    ec_total_score = sum(ec.score_bonus for ec in entry_candles[:3])  # top 3 seulement

    if not silent:
        print(f"\n  {'FVG M5 actif':<28} {tick(ltf_fvg_ok)}")
        print(f"  {'FVG non mitiqué':<28} {tick(fvg_unmit_ok)}")
        print(f"  {'Supply/Demand Zone':<28} {tick(sd_ok)}"
              + (f"  ratio_force={round(sd_active.impulse_size, 1)}×ATR" if sd_ok else ""))
        print(f"  {'Older Block H4':<28} {tick(older_block)}")
        if entry_candles:
            ec_names = " + ".join(f"{ec.candle_type}({ec.quality})" for ec in entry_candles[:3])
            print(f"  {'Bougies institutionnelles':<28} {c(ec_names, 'green')}  (+{ec_total_score})")
        else:
            print(f"  {'Bougies institutionnelles':<28} {c('Aucune détectée', 'white')}")

    # ─────────────────────────────────────────────────────────
    #  SCORING v3
    # ─────────────────────────────────────────────────────────
    score, reasons = compute_score_v3(
        bias_aligned      = True,
        amd_detected      = amd_ok,
        amd_confidence    = amd_conf,
        septuple_detected = sept_ok,
        septuple_count    = sept_count,
        mtf_bos           = mtf_bos_ok,
        mtf_ob            = mtf_ob_ok,
        liquidity_taken   = liq_taken,
        breaker_block     = breaker_ok,
        bsl_ssl_swept     = bsl_ssl_swept,
        eqh_eql_present   = eqh_eql_ok,
        ltf_fvg           = ltf_fvg_ok,
        fvg_unmitigated   = fvg_unmit_ok,
        sd_zone_active    = sd_ok,
        entry_candle_score= ec_total_score,
        older_block_htf   = older_block,
    )

    # Ajout des raisons AMD
    if amd_ok:
        reasons = amd.reasons + reasons

    # ─────────────────────────────────────────────────────────
    #  FILTRE ZONE D'ENTRÉE — au moins UNE zone valide
    # ─────────────────────────────────────────────────────────
    in_sd    = sd_ok
    in_fvg   = ltf_fvg_ok
    in_ob_m15 = False
    if ob_mtf_match:
        ob_lo = min(ob_mtf_match.top, ob_mtf_match.bottom)
        ob_hi = max(ob_mtf_match.top, ob_mtf_match.bottom)
        tol   = (ob_hi - ob_lo) * 0.10
        in_ob_m15 = (ob_lo - tol) <= price_now <= (ob_hi + tol)

    # Fibonacci 50–78.6% sur M15
    in_fib = False
    if len(df_mtf) >= 20:
        mw = df_mtf.iloc[-50:]
        sh = mw["high"].max()
        sl_v = mw["low"].min()
        if direction == "SHORT":
            f50 = sh - (sh - sl_v) * 0.500
            f786 = sh - (sh - sl_v) * 0.214
            in_fib = f50 <= price_now <= f786
        else:
            f50  = sl_v + (sh - sl_v) * 0.500
            f786 = sl_v + (sh - sl_v) * 0.786
            in_fib = f50 <= price_now <= f786

    price_in_zone = in_sd or in_fvg or in_ob_m15 or in_fib

    if not silent:
        print(f"\n  {c('── Filtre Zone d\'Entrée ──', 'cyan')}")
        print(f"  {'S/D Zone':<28} {tick(in_sd)}")
        print(f"  {'FVG M5':<28} {tick(in_fvg)}")
        print(f"  {'OB M15':<28} {tick(in_ob_m15)}")
        print(f"  {'Fibonacci 50–78.6%':<28} {tick(in_fib)}")
        zone_col = "green" if price_in_zone else "red"
        print(f"  {'→ Zone valide':<28} {c('OUI ✓' if price_in_zone else 'NON ✗ — rejeté', zone_col)}")

    if not price_in_zone:
        if not silent:
            print(c("\n  ✗ Prix hors zone structurelle — signal rejeté.", "red"))
        return None

    # Bonus multi-zone
    zone_count = sum([in_sd, in_fvg, in_ob_m15, in_fib])
    if zone_count >= 2:
        score = min(score + 5, 100)
        reasons.append(f"📐 Confluence {zone_count} zones  (+5)")

    # Affichage score
    if not silent:
        bar_filled = int(score / 5)
        bar = "█" * bar_filled + "░" * (20 - bar_filled)
        sc  = "green" if score >= 80 else ("yellow" if score >= 60 else "red")
        print(f"\n  Score  [{c(bar, sc)}]  {c(str(score) + '/100', sc)}")

    if score < SCORE_THRESHOLD:
        if not silent:
            print(c(f"\n  ✗ Score {score} < {SCORE_THRESHOLD} — insuffisant.", "yellow"))
        return None

    # ─────────────────────────────────────────────────────────
    #  NIVEAUX — Entry / SL / TP
    # ─────────────────────────────────────────────────────────
    ob_for_sl = ob_ltf_match or ob_mtf_match

    entry, sl, tp, rr = compute_sl_tp_v3(
        df_m5     = df_ltf,
        df_m15    = df_mtf,
        direction = direction,
        ob        = ob_for_sl,
        fvg       = fvg_active,
        sd_zone   = sd_active,
        liq_map   = liq_map,
        symbol    = symbol,
    )

    if rr < MIN_RR:
        if not silent:
            print(c(f"\n  ✗ RR {rr} < {MIN_RR} — rejeté.", "yellow"))
        return None

    # Détermine le mode du signal (pour Telegram + dashboard)
    if amd_ok and amd_conf >= 75:
        mode = "AMD"
    elif sept_ok and sept_count >= 5:
        mode = "SEPTUPLE"
    elif sd_ok:
        mode = "SD"
    else:
        mode = "SMC"

    lot = compute_lot(symbol, entry, sl)

    signal = Signal(
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

    if not silent:
        dec    = 2 if entry > 100 else 5
        d_col  = "red" if direction == "SHORT" else "green"
        rr_col = "green" if rr >= 3 else "yellow"
        sc_col = "green" if score >= 80 else "yellow"
        print(f"\n  {c('━'*60, 'cyan')}")
        print(f"  {c('⚡ SIGNAL ÉLITE v3', 'yellow')}  [{c(mode, 'magenta')}]  →  {c(direction, d_col)}")
        print(f"  {c('━'*60, 'cyan')}")
        print(f"  {'Symbole':<22} {c(signal.symbol, 'white')}")
        print(f"  {'Direction':<22} {c(signal.direction, d_col)}")
        print(f"  {'Mode':<22} {c(mode, 'magenta')}")
        print(f"  {'─'*45}")
        print(f"  {'📍 Entrée':<22} {c(str(signal.entry), 'white')}")
        print(f"  {'🔴 Stop Loss':<22} {c(str(signal.sl), 'red')}   risk={round(abs(entry-sl),dec)}")
        print(f"  {'🟢 Take Profit':<22} {c(str(signal.tp), 'green')}   gain={round(abs(tp-entry),dec)}")
        print(f"  {'⚖  R : R':<22} {c('1:'+str(rr), rr_col)}")
        print(f"  {'Score':<22} {c(str(score)+'/100', sc_col)}")
        print(f"  {'💰 LOT':<22} {c(str(lot)+' lot', 'magenta')}")
        print(f"  {'─'*45}")
        print(f"  Confluence :")
        for r in reasons:
            print(f"    • {r}")
        print(f"  {c('━'*60, 'cyan')}\n")

    return signal


# ═════════════════════════════════════════════════════════════
#  WATCHLIST v3 — BTC UNIQUEMENT pour crypto
# ═════════════════════════════════════════════════════════════

TIER_1_PRIORITY: list[tuple[str, str]] = [
    ("GC=F",    "Gold"),
    ("SI=F",    "Silver"),
    ("CL=F",    "Oil WTI"),
    ("BZ=F",    "Oil Brent"),
    ("BTC-USD", "Bitcoin"),    # ← BTC UNIQUEMENT (pas ETH, pas autres crypto)
]

TIER_2_FOREX: list[tuple[str, str]] = [
    ("EURUSD=X", "EUR/USD"),
    ("GBPUSD=X", "GBP/USD"),
    ("USDJPY=X", "USD/JPY"),
    ("USDCHF=X", "USD/CHF"),
    ("AUDUSD=X", "AUD/USD"),
    ("NZDUSD=X", "NZD/USD"),
    ("USDCAD=X", "USD/CAD"),
]

TIER_3_EXTRA: list[tuple[str, str]] = [
    ("EURGBP=X", "EUR/GBP"), ("EURJPY=X", "EUR/JPY"), ("GBPJPY=X", "GBP/JPY"),
    ("EURAUD=X", "EUR/AUD"), ("GBPAUD=X", "GBP/AUD"), ("AUDJPY=X", "AUD/JPY"),
    ("CADJPY=X", "CAD/JPY"), ("CHFJPY=X", "CHF/JPY"), ("EURCAD=X", "EUR/CAD"),
    ("GBPCAD=X", "GBP/CAD"), ("NZDJPY=X", "NZD/JPY"), ("GBPCHF=X", "GBP/CHF"),
    ("EURCHF=X", "EUR/CHF"), ("EURNZD=X", "EUR/NZD"), ("GBPNZD=X", "GBP/NZD"),
    ("AUDCAD=X", "AUD/CAD"), ("AUDNZD=X", "AUD/NZD"), ("AUDCHF=X", "AUD/CHF"),
    ("NZDCAD=X", "NZD/CAD"), ("NZDCHF=X", "NZD/CHF"), ("CADCHF=X", "CAD/CHF"),
    ("USDMXN=X", "USD/MXN"), ("USDZAR=X", "USD/ZAR"), ("USDTRY=X", "USD/TRY"),
    ("USDSEK=X", "USD/SEK"), ("USDNOK=X", "USD/NOK"), ("USDSGD=X", "USD/SGD"),
    ("NG=F",     "Gaz Naturel"), ("HG=F",   "Cuivre"),
    ("^GSPC",    "S&P 500"), ("^NDX",   "Nasdaq 100"), ("^DJI",   "Dow Jones"),
    ("^GDAXI",   "DAX"),     ("^FCHI",  "CAC 40"),     ("^FTSE",  "FTSE 100"),
]

CATEGORY_MAP: dict[str, list[tuple[str, str]]] = {
    "priority"  : TIER_1_PRIORITY,
    "btc"       : [("BTC-USD", "Bitcoin")],
    "forex"     : TIER_2_FOREX,
    "forex_all" : TIER_2_FOREX + [s for s in TIER_3_EXTRA if "=X" in s[0]],
    "all"       : TIER_1_PRIORITY + TIER_2_FOREX + TIER_3_EXTRA,
}


def get_symbols(cat: str) -> list[tuple[str, str]]:
    return CATEGORY_MAP.get(cat, TIER_1_PRIORITY + TIER_2_FOREX + TIER_3_EXTRA)


# ─────────────────────────────────────────────────────────────
#  AFFICHAGE WATCHLIST
# ─────────────────────────────────────────────────────────────

def print_market_list(symbols: list[tuple[str, str]]) -> None:
    tier1_set = {s[0] for s in TIER_1_PRIORITY}
    tier2_set = {s[0] for s in TIER_2_FOREX}
    groups = [
        ("🥇  TIER 1  —  Gold / BTC / Commodités", []),
        ("🥈  TIER 2  —  Forex Majeures",           []),
        ("🥉  TIER 3  —  Croisées / Indices",        []),
    ]
    for sym, name in symbols:
        if sym in tier1_set:
            groups[0][1].append((sym, name))
        elif sym in tier2_set:
            groups[1][1].append((sym, name))
        else:
            groups[2][1].append((sym, name))

    W   = 72
    sep = "╔" + "═" * W + "╗"
    mid = "╠" + "═" * W + "╣"
    bot = "╚" + "═" * W + "╝"

    def row(text):
        return "║  " + text + " " * max(0, W - 2 - len(text)) + "║"

    print(f"\n{sep}")
    print(row(f"📋  SMC ENGINE v3  —  {len(symbols)} MARCHÉS  —  H4 · AMD · S/D"))
    print(row(f"   Score min : {SCORE_THRESHOLD}/100   |   RR min : 1:{MIN_RR}   |   Crypto : BTC only"))
    print(mid)

    grand_i = 1
    for tier_name, group in groups:
        if not group:
            continue
        print(row(f"{tier_name}  ({len(group)} marchés)"))
        print(row("─" * (W - 4)))
        for j in range(0, len(group), 2):
            sym1, name1 = group[j]
            col1 = f"{grand_i:>2}. {name1:<18}  {sym1:<13}"
            grand_i += 1
            col2 = ""
            if j + 1 < len(group):
                sym2, name2 = group[j + 1]
                col2 = f"{grand_i:>2}. {name2:<18}  {sym2}"
                grand_i += 1
            print(row(col1 + col2))
        print(row(""))
    print(bot + "\n")


# ─────────────────────────────────────────────────────────────
#  LOGGING + SESSIONS
# ─────────────────────────────────────────────────────────────

import logging, sys


def setup_logging() -> logging.Logger:
    logger = logging.getLogger("smc_v3")
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    fh = logging.FileHandler("smc_v3.log", encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(ch)
    logger.addHandler(fh)
    return logger


log = setup_logging()

SESSIONS = {"London": (7, 16), "New York": (12, 21)}

MAX_SIGNALS_PER_DAY = 3
_daily_count: dict[str, int] = {}
_daily_date:  str = ""
_last_bias:   dict[str, str] = {}


def is_active_session() -> tuple[bool, str]:
    now_h = datetime.now(timezone.utc).hour
    active = [name for name, (s, e) in SESSIONS.items() if s <= now_h < e]
    return (True, " + ".join(active)) if active else (False, "Hors session")


def check_daily_limit(symbol: str) -> bool:
    global _daily_count, _daily_date
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if today != _daily_date:
        _daily_date  = today
        _daily_count = {}
    return _daily_count.get(symbol, 0) < MAX_SIGNALS_PER_DAY


def increment_daily_count(symbol: str) -> None:
    _daily_count[symbol] = _daily_count.get(symbol, 0) + 1


def startup_check() -> bool:
    log.info("=" * 65)
    log.info("  SMC SIGNAL ENGINE v3  —  AMD · Septuple · Supply/Demand")
    log.info(f"  HTF={HTF}  MTF={MTF}  LTF={LTF}")
    log.info(f"  Score min : {SCORE_THRESHOLD}/100   RR min : {MIN_RR}   Risque : ${RISK_USD}")
    log.info(f"  Crypto    : BTC-USD uniquement")
    log.info("=" * 65)

    try:
        r = requests.get(_tg_url("getMe"), timeout=10)
        if r.status_code == 200:
            bot_name = r.json()["result"]["username"]
            log.info(f"  ✓ Bot Telegram : @{bot_name}")
        else:
            log.error(f"  ✗ Telegram KO : {r.status_code}")
            return False
    except Exception as e:
        log.error(f"  ✗ Telegram : {e}")
        return False

    try:
        r2 = requests.get(_tg_url("getChat"),
                          params={"chat_id": TELEGRAM_GROUP_ID}, timeout=10)
        log.info("  ✓ Groupe Telegram OK" if r2.status_code == 200
                 else f"  ⚠ Groupe : {r2.text[:60]}")
    except Exception as e:
        log.warning(f"  ⚠ Groupe : {e}")

    yf_ok = False
    for attempt in range(1, 4):
        try:
            df = fetch("GC=F", "5m", period="1d")
            if not df.empty:
                log.info("  ✓ yfinance OK (Gold M5)")
                yf_ok = True
                break
        except Exception:
            pass
        time.sleep(20 * attempt)

    if not yf_ok:
        log.warning("  ⚠ yfinance indisponible — démarrage quand même.")

    log.info("  ✓ Démarrage scan live\n")
    return True


def _reasons_flags(reasons: list[str]) -> tuple[str, str, str, str, str]:
    has_amd  = any("AMD" in r or "Accumulation" in r or "Manipulation" in r for r in reasons)
    has_bos  = any("BOS" in r for r in reasons)
    has_sd   = any("Supply" in r or "Demand" in r or "S/D" in r for r in reasons)
    has_liq  = any("Liquidit" in r or "BSL" in r or "SSL" in r or "Hunt" in r for r in reasons)
    has_sept = any("Septuple" in r or "Traction" in r for r in reasons)
    return (
        c("A", "magenta") if has_amd  else c("·", "white"),
        c("B", "green")   if has_bos  else c("·", "white"),
        c("S", "yellow")  if has_sd   else c("·", "white"),
        c("L", "cyan")    if has_liq  else c("·", "white"),
        c("7", "red")     if has_sept else c("·", "white"),
    )


# ─────────────────────────────────────────────────────────────
#  BOUCLE LIVE PRINCIPALE
# ─────────────────────────────────────────────────────────────

def run_live(cat: str = "forex", min_score: int = SCORE_THRESHOLD,
             min_rr: float = MIN_RR, interval: int = 30) -> None:
    """
    Boucle principale VPS — scan continu toutes les {interval}s.
    Affiche un tableau de statut pour chaque marché :
      AMD(A) | BOS(B) | S/D(S) | Liquidité(L) | Septuple(7) | Score | RR | Statut
    """
    if not startup_check():
        log.error("  Startup check échoué — arrêt.")
        return

    symbols = get_symbols(cat)
    print_market_list(symbols)

    with _STATUS_LOCK:
        _STATUS["started_at"]    = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        _STATUS["symbols_count"] = len(symbols)
        _STATUS["scan_running"]  = True

    consecutive_errors = 0
    cycle_n = 0

    while True:
        try:
            cycle_n += 1
            now_utc  = datetime.now(timezone.utc)
            now_str  = now_utc.strftime("%Y-%m-%d %H:%M:%S UTC")

            if not is_session_active()[0]:
                if cycle_n % 10 == 1:
                    log.info(f"  💤 [{cycle_n}] {now_utc.strftime('%H:%M UTC')} — Hors session — actif ✓")
                with _STATUS_LOCK:
                    _STATUS["cycle"] = cycle_n
                    _STATUS["last_scan"] = now_str
                    _STATUS["scan_running"] = False
                time.sleep(interval)
                continue

            with _STATUS_LOCK:
                _STATUS["scan_running"] = True
                _STATUS["cycle"]        = cycle_n
                _STATUS["last_scan"]    = now_str

            log.info(f"  🔍 [{cycle_n}] {now_utc.strftime('%H:%M UTC')} — Scan {len(symbols)} paires")
            correlation_guard_reset()

            W = 95
            print(f"\n{'╔' + '═'*W + '╗'}")
            print(f"║  🔍  CYCLE #{cycle_n}  [{now_str}]  {len(symbols)} marchés  "
                  + " " * max(0, W - 4 - 8 - len(now_str) - len(str(len(symbols))) - 20) + "║")
            print(f"║  A=AMD · B=BOS · S=Supply/Demand · L=Liquidité · 7=Septuple  "
                  + " " * max(0, W - 66) + "║")
            print(f"{'╠' + '═'*W + '╣'}")
            print(f"  {'N°':<4} {'Tier':<4} {'Marché':<14} {'Symbole':<12}"
                  f"  {'Prix':>14}  {'Biais':>6}"
                  f"  A  B  S  L  7  {'Score':>6}  {'RR':>5}  Statut")
            print(f"  {'─'*93}")

            signals_found: list[tuple[str, str, Signal, str]] = []

            for i, (sym, mkt) in enumerate(symbols, 1):
                t1 = {s[0] for s in TIER_1_PRIORITY}
                t2 = {s[0] for s in TIER_2_FOREX}
                tier = c("T1🥇", "yellow") if sym in t1 else (
                       c("T2🥈", "cyan")   if sym in t2 else c("T3🥉", "white"))
                prefix = f"  {i:<4} {tier}  {mkt:<14} {c(sym, 'cyan'):<12}"

                print(prefix + "  … ", end="", flush=True)

                try:
                    sig = analyse(sym, silent=True)

                    if sig is not None:
                        new_bias = sig.htf_bias
                        if _last_bias.get(sym) and _last_bias[sym] != new_bias:
                            reset_setup(sym)
                        _last_bias[sym] = new_bias

                    if sig is None:
                        try:
                            df_peek = fetch(sym, LTF, period="1d")
                            px_s = str(round(df_peek["close"].iloc[-1],
                                             2 if df_peek["close"].iloc[-1] > 100 else 5)) \
                                   if not df_peek.empty else "—"
                            vol_ok, vol_reason = check_volatility(sym, df_peek) \
                                                  if not df_peek.empty else (True, "")
                            skip = f"⛔ {vol_reason}" if not vol_ok else "⚪ Pas de setup"
                        except Exception:
                            px_s = "—"
                            skip = "⚪ Pas de setup"
                        print(f"\r{prefix}  {px_s:>14}  {'—':>6}"
                              f"  ·  ·  ·  ·  ·  {'—':>6}  {'—':>5}  {skip}")
                    else:
                        px_s   = str(round(sig.entry, 2 if sig.entry > 100 else 5))
                        a_, b_, s_, l_, s7_ = _reasons_flags(sig.reasons)
                        sc_col = "green" if sig.score >= 80 else ("yellow" if sig.score >= 60 else "red")
                        rr_col = "green" if sig.rr >= 3 else "yellow"
                        d_col  = "red" if sig.direction == "SHORT" else "green"

                        if sig.score >= min_score and sig.rr >= min_rr:
                            corr_ok, corr_reason = correlation_guard(sym, sig.direction)
                            if not corr_ok:
                                status = c(f"🟠 Corrélé", "yellow")
                            else:
                                tier_lbl = next(
                                    (lbl for lbl, grp in [
                                        ("TIER 1 🥇  GOLD + BTC", TIER_1_PRIORITY),
                                        ("TIER 2 🥈  FOREX MAJEURES", TIER_2_FOREX),
                                        ("TIER 3 🥉  CROISÉES + EXTRA", TIER_3_EXTRA),
                                    ] if any(s == sym for s, _ in grp)),
                                    "TIER 2 🥈  FOREX MAJEURES"
                                )
                                signals_found.append((mkt, sym, sig, tier_lbl))
                                status = c(f"⚡ {sig.direction} [{sig.mode}]", d_col)
                        elif sig.score >= int(min_score * 0.75):
                            status = c(f"🟡 Proche ({sig.score})", "yellow")
                        else:
                            status = c(f"🔵 Attente ({sig.score})", "white")

                        print(f"\r{prefix}  {px_s:>14}  "
                              f"{c(sig.htf_bias[:4], d_col):>6}  "
                              f"{a_}  {b_}  {s_}  {l_}  {s7_}  "
                              f"{c(str(sig.score), sc_col):>6}  "
                              f"{c('1:'+str(sig.rr), rr_col):>5}  {status}")

                    time.sleep(1)

                except Exception as e:
                    print(f"\r{prefix}  {'—':>14}  {'—':>6}"
                          f"  ·  ·  ·  ·  ·  {'—':>6}  {'—':>5}  "
                          + c(f"⚠ {str(e)[:35]}", "red"))

            # ── Limite 2 meilleurs signaux / cycle ──────────
            print(f"  {'─'*93}")
            if len(signals_found) > 2:
                signals_found = sorted(signals_found, key=lambda x: x[2].score, reverse=True)[:2]

            if signals_found:
                print(c(f"\n  ⚡ {len(signals_found)} SIGNAL(S) — Envoi Telegram en cours…", "yellow"))

            for mkt, sym, sig, tier_lbl in signals_found:
                log.info(f"  ⚡ {sig.direction} {mkt}  mode={sig.mode}  score={sig.score}  "
                         f"RR=1:{sig.rr}  lot={sig.lot}")
                tg_notify(sig, tier=tier_lbl, mode=sig.mode)

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
                print(c(f"  ℹ️  Aucun signal valide (score≥{min_score} + RR≥{min_rr})", "white"))

            print(f"{'╚' + '═'*W + '╝'}")
            consecutive_errors = 0
            log.info(f"  ⏳ Prochain scan dans {interval}s\n")
            time.sleep(interval)

        except KeyboardInterrupt:
            log.info("\n  Session live terminée.")
            try:
                requests.post(_tg_url("sendMessage"), json={
                    "chat_id": TELEGRAM_GROUP_ID,
                    "text": "🔴 <b>SMC Signal Engine v3 arrêté</b>",
                    "parse_mode": "HTML",
                }, timeout=5)
            except Exception:
                pass
            break

        except Exception as e:
            consecutive_errors += 1
            log.error(f"  ✗ Erreur critique : {e}")
            wait = min(60 * consecutive_errors, 300)
            log.info(f"  ⏳ Reprise dans {wait}s (erreur #{consecutive_errors})")
            time.sleep(wait)


# ─────────────────────────────────────────────────────────────
#  SCAN UNIQUE (test local)
# ─────────────────────────────────────────────────────────────

def scan_watchlist(symbols: list[tuple[str, str]], htf: str, ltf: str,
                   min_score: int = SCORE_THRESHOLD, min_rr: float = MIN_RR):
    all_results = []
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    total = len(symbols)

    print(f"\n{c('╔' + '═'*66 + '╗', 'cyan')}")
    print(f"{c('║', 'cyan')}  {c('SMC v3 SCAN — AMD · Septuple · S/D · Liquidity Map', 'yellow'):<65}{c('║', 'cyan')}")
    print(f"{c('║', 'cyan')}  H4={htf}  LTF={ltf}  score≥{min_score}  RR≥{min_rr}   {ts:<27}{c('║', 'cyan')}")
    print(f"{c('╚' + '═'*66 + '╝', 'cyan')}")

    for i, (sym, mkt) in enumerate(symbols, 1):
        print(f"  [{i:>2}/{total}]  {mkt:<16} {c(sym, 'cyan')} … ", end="", flush=True)
        try:
            sig = analyse(sym, htf, ltf, silent=True)
            if sig and sig.score >= min_score and sig.rr >= min_rr:
                all_results.append((mkt, sig))
                d_color = "red" if sig.direction == "SHORT" else "green"
                print(c(f"⚡ {sig.direction} [{sig.mode}]  score={sig.score}  RR=1:{sig.rr}", d_color))
                tg_notify(sig, tier="TIER 1", mode=sig.mode)
            else:
                print(c("—", "white"))
        except Exception as e:
            print(c(f"err: {e}", "red"))

    if all_results:
        print(f"\n{c('═'*70, 'yellow')}")
        print(c(f"  ⚡ {len(all_results)} signal(s) validé(s)", "yellow"))
        for mkt, s in sorted(all_results, key=lambda x: -x[1].score):
            d = "red" if s.direction == "SHORT" else "green"
            print(f"  {mkt:<16} {c(s.direction, d)}  [{s.mode}]  "
                  f"score={s.score}  RR=1:{s.rr}  lot={s.lot}")
    else:
        print(c(f"\n  Aucun signal score≥{min_score} RR≥{min_rr}", "yellow"))

    return all_results


# ═════════════════════════════════════════════════════════════
#  MAIN
# ═════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="SMC Signal Engine v3 — AMD · Septuple Traction · Supply/Demand",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--symbol",    default=None,
                        help="Symbole unique  (ex: BTC-USD, GC=F, EURUSD=X)")
    parser.add_argument("--cat",       default="forex",
                        choices=["priority", "btc", "forex", "forex_all", "all"],
                        help=(
                            "priority  = Gold + BTC\n"
                            "btc       = BTC uniquement\n"
                            "forex     = Forex majeures (défaut)\n"
                            "forex_all = Forex complet\n"
                            "all       = Tout scanner"
                        ))
    parser.add_argument("--scan",      action="store_true",
                        help="Scan unique (test local)")
    parser.add_argument("--min-score", type=int,   default=SCORE_THRESHOLD)
    parser.add_argument("--min-rr",    type=float, default=MIN_RR)
    parser.add_argument("--interval",  type=int,   default=30,
                        help="Intervalle scan secondes (défaut: 30)")
    args = parser.parse_args()

    # ── Flask dashboard ───────────────────────────────────────
    flask_port = int(os.environ.get("PORT", 10000))
    threading.Thread(target=start_flask, args=(flask_port,),
                     daemon=True, name="flask").start()
    time.sleep(3)
    log.info(f"  ✓ Flask dashboard port {flask_port}")

    # ── Self-ping anti-veille Render ──────────────────────────
    start_self_ping(flask_port)

    # ── Mode selon arguments ──────────────────────────────────
    if args.symbol:
        sig = analyse(args.symbol)
        if sig:
            tg_notify(sig, tier="TIER 1", mode=sig.mode)

    elif args.scan:
        symbols = get_symbols(args.cat)
        scan_watchlist(symbols, HTF, LTF, args.min_score, args.min_rr)

    else:
        run_live(cat=args.cat, min_score=args.min_score,
                 min_rr=args.min_rr, interval=args.interval)

