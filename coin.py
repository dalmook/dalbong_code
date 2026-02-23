# -*- coding: utf-8 -*-
"""
Upbit Rotation Momentum Bot (FINAL)
==================================
✅ Final preset (Aggressive #1):
- interval=minute240 (4H)
- lookback=48
- topk=1
- rebalance_every=12
- ema_n=200
- min_mom=0.02

✅ Features
- Backtest + Live in one file
- LIVE mode controllable via code: LIVE_MODE = True/False
- Keys can be embedded in code (or ENV)
- Live uses last closed candle info (no lookahead), rebalances once per new bar
- Sell-first then Buy (live-style)
- Retries for API calls
- State file to prevent duplicate trades in same bar
- Skip when target is all cash

Install:
  pip install pyupbit pandas numpy

How to run (no args):
  - If LIVE_MODE=False -> runs backtest with defaults
  - If LIVE_MODE=True  -> runs live loop (paper if DRY_RUN=True)

How to run (with args override):
  python upbit_rotation_bot.py --mode backtest
  python upbit_rotation_bot.py --mode paper
  python upbit_rotation_bot.py --mode live

⚠️ Real trading:
  Set LIVE_MODE = True and DRY_RUN = False
  Fill ACCESS_KEY / SECRET_KEY (or ENV)
"""

from __future__ import annotations

import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

import time
import json
import math
import argparse
import logging
from logging.handlers import RotatingFileHandler
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any, TYPE_CHECKING
if TYPE_CHECKING:
    from pyupbit import Upbit as UpbitClient
else:
    UpbitClient = Any
import numpy as np
import pandas as pd

try:
    import pyupbit
except Exception:
    pyupbit = None


# =========================================================
# ✅ USER SETTINGS (EDIT HERE)
# =========================================================

# --- 1) KEYS (you can paste keys here) ---
ACCESS_KEY = "K1"  # e.g. "xxxx"
SECRET_KEY = "iu"  # e.g. "yyyy"
# (If empty, will try ENV: UPBIT_ACCESS_KEY / UPBIT_SECRET_KEY)

# --- 2) MODE TOGGLE (code-level) ---
LIVE_MODE = True   # True: live loop / False: backtest (default if no CLI args)
DRY_RUN  = False     # True: no real orders even in LIVE_MODE (PAPER). False: real orders.

# --- 3) FINAL PRESET (Aggressive #1) ---
INTERVAL = "minute240"
BARS     = 4000
TICKERS  = ["KRW-BTC", "KRW-ETH", "KRW-XRP"]

LOOKBACK        = 48
TOPK            = 1
REBALANCE_EVERY = 12
EMA_N           = 200
MIN_MOM         = 0.02

# --- 4) COST ASSUMPTIONS (for backtest / live planning) ---
FEE  = 0.0005
SLIP = 0.0015

# --- 5) LIVE RISK SETTINGS ---
SLEEP_SEC     = 60
MIN_ORDER_KRW = 5500.0      # Upbit min ~5000, keep buffer
RESERVE_KRW   = 200000.0    # keep cash buffer
MAX_TOTAL_KRW = None        # e.g. 1000000.0 to limit exposure; None = all-in


# =========================================================
# Logging
# =========================================================
def setup_logger(log_dir: str = "logs", name: str = "RotationBot") -> logging.Logger:
    os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        fh = RotatingFileHandler(
            os.path.join(log_dir, "rotation_bot.log"),
            maxBytes=2_000_000,
            backupCount=5,
            encoding="utf-8",
        )
        fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        logger.addHandler(sh)
    return logger


# =========================================================
# Utils: retry wrappers
# =========================================================
def safe_call(fn, *args, tries: int = 3, sleep: float = 0.3, logger: Optional[logging.Logger] = None, **kwargs):
    last = None
    for k in range(tries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            last = e
            if logger:
                logger.warning(f"safe_call retry {k+1}/{tries}: {fn.__name__} -> {e}")
            time.sleep(sleep * (1.5 ** k))
    raise last


# =========================================================
# Indicators / Stats
# =========================================================
def ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, adjust=False).mean()

def max_drawdown(equity: pd.Series) -> float:
    peak = equity.cummax()
    dd = (equity / peak) - 1.0
    return float(dd.min())

def infer_periods_per_year(interval: str) -> float:
    if interval.startswith("minute"):
        m = int(interval.replace("minute", ""))
        return (60 / m) * 24 * 365
    if interval == "day":
        return 365.0
    if interval == "week":
        return 52.0
    if interval == "month":
        return 12.0
    return 365.0

def sharpe_ratio(rets: pd.Series, periods_per_year: float) -> float:
    r = rets.dropna()
    if len(r) < 2:
        return 0.0
    mu = r.mean()
    sd = r.std()
    if sd == 0 or np.isnan(sd):
        return 0.0
    return float((mu / sd) * math.sqrt(periods_per_year))


# =========================================================
# Data fetch + cache
# =========================================================
def ensure_dir(p: str) -> None:
    os.makedirs(p, exist_ok=True)

def cache_path(cache_dir: str, ticker: str, interval: str, bars: int) -> str:
    safe = ticker.replace("/", "_").replace("-", "_")
    return os.path.join(cache_dir, f"{safe}_{interval}_{bars}.csv")

def fetch_ohlcv_upbit(ticker: str, interval: str, bars: int, cache_dir: str = "cache") -> pd.DataFrame:
    if pyupbit is None:
        raise RuntimeError("pyupbit 필요: pip install pyupbit")

    ensure_dir(cache_dir)
    cp = cache_path(cache_dir, ticker, interval, bars)

    if os.path.exists(cp):
        try:
            df = pd.read_csv(cp, parse_dates=["datetime"]).set_index("datetime").sort_index()
            df = df[~df.index.duplicated(keep="last")]


            # ✅ cache가 있어도 최신 캔들(최근 200개)을 붙여 갱신
            try:
                df_new = pyupbit.get_ohlcv(ticker, interval=interval, count=min(200, max(5, bars)))
                if df_new is not None and len(df_new) > 0:
                    df_new = df_new.rename(columns=str.lower)
                    df_new.index.name = "datetime"

                    df = pd.concat([df, df_new]).sort_index().drop_duplicates()
                    df = df[["open", "high", "low", "close", "volume"]].dropna()

                    # 갱신된 캐시 저장
                    df.reset_index().to_csv(cp, index=False)
            except Exception:
                # 최신 캔들 붙이기 실패해도, 기존 캐시로 계속 진행
                pass

            if len(df) >= int(bars * 0.95):
                return df.tail(bars)
        except Exception:
            pass



    remain = bars
    to = None
    chunks = []

    while remain > 0:
        cnt = min(200, remain)
        df = pyupbit.get_ohlcv(ticker, interval=interval, count=cnt, to=to)
        if df is None or len(df) == 0:
            break
        df = df.rename(columns=str.lower)
        df.index.name = "datetime"
        chunks.append(df)
        remain -= len(df)

        oldest = df.index.min()
        to = oldest
        if len(df) < cnt:
            break

    if not chunks:
        raise RuntimeError(f"데이터 수집 실패: {ticker} {interval}")

    out = pd.concat(chunks).sort_index()
    out = out[~out.index.duplicated(keep="last")]
    out = out[["open", "high", "low", "close", "volume"]].dropna()
    out.reset_index().to_csv(cp, index=False)
    return out.tail(bars)

def align_data(dfs: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
    idx = None
    for df in dfs.values():
        idx = df.index if idx is None else idx.intersection(df.index)
    return {k: v.loc[idx].copy() for k, v in dfs.items()}


# =========================================================
# Strategy: Rotation Momentum Top-K weights
# =========================================================
def risk_on_series_from_btc(btc_df: pd.DataFrame, idx: pd.Index, ema_n: int = 200) -> pd.Series:
    btc = btc_df.reindex(idx)
    btc_ema = ema(btc["close"], ema_n)
    return (btc["close"].shift(1) > btc_ema.shift(1)).fillna(False)

def weights_rotation_momentum(
    dfs: Dict[str, pd.DataFrame],
    lookback: int,
    topk: int,
    rebalance_every: int,
    risk_filter_btc: Optional[pd.DataFrame],
    ema_n: int,
    min_mom: float,
) -> pd.DataFrame:
    dfs = align_data(dfs)
    tickers = list(dfs.keys())
    idx = dfs[tickers[0]].index
    close = pd.DataFrame({t: dfs[t]["close"] for t in tickers}).reindex(idx)

    w = pd.DataFrame(0.0, index=idx, columns=tickers)

    risk_on = pd.Series(True, index=idx)
    if risk_filter_btc is not None:
        risk_on = risk_on_series_from_btc(risk_filter_btc, idx, ema_n=ema_n)

    warmup = lookback + ema_n + 5
    for i in range(len(idx)):
        if i < warmup:
            continue

        if (i % rebalance_every) != 0:
            w.iloc[i] = w.iloc[i - 1]
            continue

        if not bool(risk_on.iloc[i]):
            w.iloc[i] = 0.0
            continue

        mom = (close.iloc[i - 1] / close.iloc[i - 1 - lookback] - 1.0)
        mom = mom.replace([np.inf, -np.inf], np.nan).dropna()
        if len(mom) == 0:
            w.iloc[i] = 0.0
            continue

        if float(mom.max()) < float(min_mom):
            w.iloc[i] = 0.0
            continue

        winners = mom.sort_values(ascending=False).head(int(topk)).index.tolist()
        for t in tickers:
            w.iat[i, w.columns.get_loc(t)] = (1.0 / len(winners)) if t in winners else 0.0

    return w.ffill().fillna(0.0)


# =========================================================
# Backtest: portfolio weights (sell-first then buy)
# =========================================================
@dataclass
class BacktestResult:
    equity: pd.Series
    weights: pd.DataFrame
    total_return: float
    mdd: float
    sharpe: float
    approx_rebalances: int
    avg_turnover: float

def bt_portfolio_weights(
    dfs: Dict[str, pd.DataFrame],
    target_w: pd.DataFrame,
    fee: float,
    slip: float,
    init_cash: float = 1_000_000.0,
    trade_threshold: float = 0.0005,
    interval: str = "minute240",
) -> BacktestResult:
    dfs = align_data(dfs)
    tickers = list(dfs.keys())
    idx = dfs[tickers[0]].index

    close = pd.DataFrame({t: dfs[t]["close"] for t in tickers}).reindex(idx)
    open_ = pd.DataFrame({t: dfs[t]["open"] for t in tickers}).reindex(idx)

    w = target_w.reindex(idx).fillna(0.0)
    for t in tickers:
        if t not in w.columns:
            w[t] = 0.0
    w = w[tickers].clip(lower=0.0)
    s = w.sum(axis=1)
    w = w.div(s.where(s > 1.0, 1.0), axis=0)

    cash = float(init_cash)
    qty = {t: 0.0 for t in tickers}
    equity = np.zeros(len(idx), dtype=float)
    equity[0] = init_cash

    turnover = w.diff().abs().sum(axis=1).fillna(0.0)
    approx_rebalances = int((turnover > trade_threshold).sum())
    avg_turn = float(turnover.mean())

    cost_rate = fee + slip

    for i in range(1, len(idx)):
        px_open = open_.iloc[i]
        px_close = close.iloc[i]

        cur_val = cash + sum(qty[t] * float(px_open[t]) for t in tickers)
        th = cur_val * trade_threshold

        tw = w.iloc[i]
        tgt_val = (cur_val * tw).to_dict()

        # --- compute deltas at open
        cur_val_t = {t: qty[t] * float(px_open[t]) for t in tickers}
        dv = {t: float(tgt_val[t] - cur_val_t[t]) for t in tickers}

        # PASS 1) SELL first
        for t in tickers:
            p = float(px_open[t])
            if p <= 0 or np.isnan(p):
                continue
            if dv[t] >= -th:
                continue

            sell_value = min(cur_val_t[t], -dv[t])
            if sell_value < th:
                continue

            sell_qty = min(qty[t], sell_value / p)
            if sell_qty <= 0:
                continue

            proceeds = sell_qty * p
            cost = proceeds * cost_rate
            net = max(proceeds - cost, 0.0)

            qty[t] -= sell_qty
            cash += net

        # refresh after sells
        cur_val_t = {t: qty[t] * float(px_open[t]) for t in tickers}
        dv = {t: float(tgt_val[t] - cur_val_t[t]) for t in tickers}

        # PASS 2) BUY with available cash
        for t in tickers:
            p = float(px_open[t])
            if p <= 0 or np.isnan(p):
                continue
            if dv[t] <= th:
                continue

            spend = min(cash, dv[t])
            if spend < th:
                continue

            cost = spend * cost_rate
            net = max(spend - cost, 0.0)

            qty[t] += net / p
            cash -= spend

        equity[i] = cash + sum(qty[t] * float(px_close[t]) for t in tickers)

    equity_s = pd.Series(equity, index=idx, name="equity")
    rets = equity_s.pct_change()
    pp_year = infer_periods_per_year(interval)

    return BacktestResult(
        equity=equity_s,
        weights=w,
        total_return=float(equity_s.iloc[-1] / equity_s.iloc[0] - 1.0),
        mdd=float(max_drawdown(equity_s)),
        sharpe=float(sharpe_ratio(rets, pp_year)),
        approx_rebalances=approx_rebalances,
        avg_turnover=avg_turn,
    )


# =========================================================
# Live / Paper
# =========================================================
def coin_symbol(ticker: str) -> str:
    return ticker.split("-")[-1].strip()

def get_keys() -> Tuple[str, str]:
    ak = ACCESS_KEY or os.getenv("UPBIT_ACCESS_KEY", "")
    sk = SECRET_KEY or os.getenv("UPBIT_SECRET_KEY", "")
    if not ak or not sk:
        raise RuntimeError("Upbit KEY가 없습니다. ACCESS_KEY/SECRET_KEY 또는 ENV(UPBIT_ACCESS_KEY/UPBIT_SECRET_KEY) 설정하세요.")
    return ak, sk

def safe_get_current_price(tickers: List[str], logger: logging.Logger) -> Dict[str, float]:
    def _get():
        return pyupbit.get_current_price(tickers)
    px = safe_call(_get, tries=3, sleep=0.2, logger=logger)
    if isinstance(px, dict):
        return {k: float(v) for k, v in px.items() if v is not None}
    if len(tickers) == 1 and px is not None:
        return {tickers[0]: float(px)}
    return {}

@dataclass
class LiveConfig:
    dry_run: bool
    min_order_krw: float
    reserve_krw: float
    max_total_krw: Optional[float]
    fee: float
    slip: float

class RotationBot:
    def __init__(
        self,
        upbit: "UpbitClient",
        tickers: List[str],
        interval: str,
        bars: int,
        cache_dir: str,
        state_path: str,
        cfg: LiveConfig,
        logger: logging.Logger,
    ):
        self.upbit = upbit
        self.tickers = tickers
        self.interval = interval
        self.bars = bars
        self.cache_dir = cache_dir
        self.state_path = state_path
        self.cfg = cfg
        self.log = logger
        self.state = self._load_state()

    def _load_state(self) -> dict:
        if os.path.exists(self.state_path):
            try:
                with open(self.state_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"last_bar": None}

    def _save_state(self) -> None:
        os.makedirs(os.path.dirname(self.state_path) or ".", exist_ok=True)
        with open(self.state_path, "w", encoding="utf-8") as f:
            json.dump(self.state, f, ensure_ascii=False, indent=2)

    def _fetch_all(self) -> Dict[str, pd.DataFrame]:
        dfs = {}
        for t in self.tickers:
            df = safe_call(fetch_ohlcv_upbit, t, self.interval, self.bars, self.cache_dir, tries=3, sleep=0.3, logger=self.log)
            dfs[t] = df
        return align_data(dfs)

    def _balances(self) -> Tuple[float, Dict[str, float]]:
        def _get_bal():
            return self.upbit.get_balances()

        bals = safe_call(_get_bal, tries=3, sleep=0.25, logger=self.log)
        krw = 0.0
        qty = {t: 0.0 for t in self.tickers}
        for b in bals or []:
            cur = b.get("currency", "")
            if cur == "KRW":
                krw = float(b.get("balance", 0) or 0)
            else:
                for t in self.tickers:
                    if coin_symbol(t) == cur:
                        qty[t] = float(b.get("balance", 0) or 0)
        return krw, qty

    def _portfolio_value(self, krw: float, qty: Dict[str, float], prices: Dict[str, float]) -> float:
        val = krw
        for t, q in qty.items():
            p = prices.get(t)
            if p is None:
                continue
            val += q * float(p)
        return float(val)

    def _place_sell(self, ticker: str, vol: float) -> None:
        if vol <= 0:
            return
        if self.cfg.dry_run:
            self.log.info(f"[PAPER] SELL {ticker} vol={vol:.8f}")
            return

        def _sell():
            return self.upbit.sell_market_order(ticker, vol)
        r = safe_call(_sell, tries=3, sleep=0.4, logger=self.log)
        self.log.info(f"[LIVE] SELL {ticker} vol={vol:.8f} -> {r}")

    def _place_buy(self, ticker: str, krw_amount: float) -> None:
        if krw_amount < self.cfg.min_order_krw:
            return
        if self.cfg.dry_run:
            self.log.info(f"[PAPER] BUY {ticker} KRW={krw_amount:,.0f}")
            return

        def _buy():
            return self.upbit.buy_market_order(ticker, krw_amount)
        r = safe_call(_buy, tries=3, sleep=0.4, logger=self.log)
        self.log.info(f"[LIVE] BUY {ticker} KRW={krw_amount:,.0f} -> {r}")

    def compute_target_for_current_bar(self) -> Tuple[pd.Series, str, str]:
        """
        Live logic:
        - Use OHLCV including current (possibly forming) bar.
        - Compute weights at the current bar timestamp using info up to previous close (no lookahead).
        - bar_key uses current bar timestamp (stable within bar).
        """
        dfs = self._fetch_all()
        any_df = dfs[self.tickers[0]]
        if len(any_df) < (LOOKBACK + EMA_N + 10):
            raise RuntimeError("OHLCV length too short for warmup.")

        bar_ts = str(any_df.index[-1])        # current bar time
        last_closed_ts = str(any_df.index[-2])  # last closed bar time (for logs)

        btc_df = dfs.get("KRW-BTC")
        if btc_df is None:
            btc_df = dfs[self.tickers[0]]


        w = weights_rotation_momentum(
            dfs,
            lookback=LOOKBACK,
            topk=TOPK,
            rebalance_every=REBALANCE_EVERY,
            risk_filter_btc=btc_df,
            ema_n=EMA_N,
            min_mom=MIN_MOM,
        )

        tw = w.iloc[-1].copy()
        s = float(tw.sum())
        if s > 1.0:
            tw = tw / s

        return tw, bar_ts, last_closed_ts

    def rebalance_once(self) -> None:
        tw, bar_key, last_closed = self.compute_target_for_current_bar()

        if self.state.get("last_bar") == bar_key:
            self.log.info(f"Skip: already rebalanced for bar={bar_key}")
            return

        tw_dict = tw.to_dict()
        self.log.info(f"Rebalance bar={bar_key} (last_closed={last_closed}) target={tw_dict}")

        # all cash -> just liquidate (if any holdings), then stop
        if float(tw.sum()) <= 0.0:
            self.log.info("Target is 100% CASH. Will liquidate holdings (if any).")

        krw, qty = self._balances()
        prices = safe_get_current_price(self.tickers, self.log)
        total_val = self._portfolio_value(krw, qty, prices)

        deploy_val = total_val
        if self.cfg.max_total_krw is not None:
            deploy_val = min(deploy_val, float(self.cfg.max_total_krw))
        deploy_val = max(deploy_val - float(self.cfg.reserve_krw), 0.0)

        cur_val = {t: qty[t] * float(prices.get(t, 0.0)) for t in self.tickers}
        tgt_val = {t: float(tw.get(t, 0.0)) * deploy_val for t in self.tickers}
        dv = {t: tgt_val[t] - cur_val[t] for t in self.tickers}

        # =========================
        # SELL first
        # =========================
        for t in sorted(self.tickers, key=lambda x: dv[x]):  # most negative first
            if dv[t] >= -self.cfg.min_order_krw:
                continue
            p = float(prices.get(t, 0.0))
            if p <= 0:
                continue
            sell_value = min(cur_val[t], -dv[t])
            if sell_value < self.cfg.min_order_krw:
                continue
            sell_vol = (sell_value / p) * 0.995  # safety margin
            self._place_sell(t, sell_vol)
            time.sleep(0.15)

        # refresh after sells
        krw, qty = self._balances()
        prices = safe_get_current_price(self.tickers, self.log)
        total_val = self._portfolio_value(krw, qty, prices)

        deploy_val = total_val
        if self.cfg.max_total_krw is not None:
            deploy_val = min(deploy_val, float(self.cfg.max_total_krw))
        deploy_val = max(deploy_val - float(self.cfg.reserve_krw), 0.0)

        cur_val = {t: qty[t] * float(prices.get(t, 0.0)) for t in self.tickers}
        tgt_val = {t: float(tw.get(t, 0.0)) * deploy_val for t in self.tickers}
        dv = {t: tgt_val[t] - cur_val[t] for t in self.tickers}

        # =========================
        # BUY with available KRW
        # =========================
        available_krw = max(krw - float(self.cfg.reserve_krw), 0.0)
        for t in sorted(self.tickers, key=lambda x: dv[x], reverse=True):
            if dv[t] <= self.cfg.min_order_krw:
                continue
            spend = min(available_krw, dv[t])
            if spend < self.cfg.min_order_krw:
                continue
            self._place_buy(t, spend)
            available_krw -= spend
            time.sleep(0.15)

        self.state["last_bar"] = bar_key
        self._save_state()
        self.log.info("Rebalance done.")


# =========================================================
# CLI / Runner
# =========================================================
def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["backtest", "paper", "live"], default=None)

    ap.add_argument("--interval", default=INTERVAL)
    ap.add_argument("--bars", type=int, default=BARS)
    ap.add_argument("--tickers", default=",".join(TICKERS))
    ap.add_argument("--cache-dir", default=os.path.join(BASE_DIR, "cache"))
    ap.add_argument("--out-prefix", default="rot_final")

    ap.add_argument("--fee", type=float, default=FEE)
    ap.add_argument("--slip", type=float, default=SLIP)
    ap.add_argument("--init-cash", type=float, default=1_000_000.0)

    ap.add_argument("--sleep", type=int, default=SLEEP_SEC)
    ap.add_argument("--min-order-krw", type=float, default=MIN_ORDER_KRW)
    ap.add_argument("--reserve-krw", type=float, default=RESERVE_KRW)
    ap.add_argument("--max-total-krw", type=float, default=MAX_TOTAL_KRW)

    return ap.parse_args()

def run_backtest(args: argparse.Namespace, log: logging.Logger) -> None:
    tickers = [x.strip() for x in args.tickers.split(",") if x.strip()]
    dfs = {t: fetch_ohlcv_upbit(t, args.interval, args.bars, cache_dir=args.cache_dir) for t in tickers}
    dfs = align_data(dfs)

    # ✅ drop last forming candle to stabilize backtest
    dfs = {t: df.iloc[:-1].copy() for t, df in dfs.items()}
    dfs = align_data(dfs)

    btc_df = dfs.get("KRW-BTC")
    if btc_df is None:
        btc_df = dfs[tickers[0]]

    w = weights_rotation_momentum(
        dfs,
        lookback=LOOKBACK,
        topk=TOPK,
        rebalance_every=REBALANCE_EVERY,
        risk_filter_btc=btc_df,
        ema_n=EMA_N,
        min_mom=MIN_MOM,
    )

    res = bt_portfolio_weights(
        dfs,
        w,
        fee=args.fee,
        slip=args.slip,
        init_cash=args.init_cash,
        interval=args.interval,
    )

    rep = pd.DataFrame([{
        "strategy": "rotation_momentum_topk",
        "bars": len(res.equity),
        "total_return": res.total_return,
        "mdd": res.mdd,
        "sharpe": res.sharpe,
        "final_equity": float(res.equity.iloc[-1]),
        "approx_rebalances": res.approx_rebalances,
        "avg_turnover": res.avg_turnover,
    }])

    print("\n=== BACKTEST REPORT ===")
    print(rep.to_string(index=False))
    print("params:", {
        "interval": args.interval,
        "lookback": LOOKBACK,
        "topk": TOPK,
        "rebalance_every": REBALANCE_EVERY,
        "ema_n": EMA_N,
        "min_mom": MIN_MOM,
        "fee": args.fee,
        "slip": args.slip,
    })

    out_eq = f"{args.out_prefix}_equity.csv"
    out_w  = f"{args.out_prefix}_weights.csv"
    out_js = f"{args.out_prefix}_report.json"

    res.equity.to_frame().to_csv(out_eq)
    res.weights.to_csv(out_w)
    with open(out_js, "w", encoding="utf-8") as f:
        json.dump({
            "preset": "Aggressive#1",
            "params": {
                "interval": args.interval,
                "lookback": LOOKBACK,
                "topk": TOPK,
                "rebalance_every": REBALANCE_EVERY,
                "ema_n": EMA_N,
                "min_mom": MIN_MOM,
                "fee": args.fee,
                "slip": args.slip,
            },
            "result": rep.iloc[0].to_dict(),
        }, f, ensure_ascii=False, indent=2)

    log.info(f"Saved: {out_eq}, {out_w}, {out_js}")

def run_live_or_paper(args: argparse.Namespace, log: logging.Logger, dry_run: bool) -> None:
    if pyupbit is None:
        raise RuntimeError("pyupbit 필요: pip install pyupbit")

    ak, sk = get_keys()
    upbit = pyupbit.Upbit(ak, sk)

    tickers = [x.strip() for x in args.tickers.split(",") if x.strip()]
    bars_live = max(800, LOOKBACK + EMA_N + 50)


    cfg = LiveConfig(
        dry_run=dry_run,
        min_order_krw=float(args.min_order_krw),
        reserve_krw=float(args.reserve_krw),
        max_total_krw=None if args.max_total_krw is None else float(args.max_total_krw),
        fee=float(args.fee),
        slip=float(args.slip),
    )

    state_path = os.path.join(
    BASE_DIR,
    "state",
    f"rotation_state_{args.interval}_{'_'.join([t.replace('-','') for t in tickers])}.json"
    )

    bot = RotationBot(
        upbit=upbit,
        tickers=tickers,
        interval=args.interval,
        bars=bars_live,
        cache_dir=args.cache_dir,
        state_path=state_path,
        cfg=cfg,
        logger=log,
    )

    mode_name = "PAPER" if dry_run else "LIVE"
    log.info(f"{mode_name} loop start | interval={args.interval} tickers={tickers}")
    log.info(f"Preset: lookback={LOOKBACK} topk={TOPK} rebalance={REBALANCE_EVERY} ema={EMA_N} min_mom={MIN_MOM}")
    log.info(f"Risk: reserve_krw={cfg.reserve_krw} max_total_krw={cfg.max_total_krw} min_order_krw={cfg.min_order_krw}")

    while True:
        try:
            bot.rebalance_once()
        except Exception as e:
            log.exception(f"rebalance error: {e}")
        time.sleep(max(int(args.sleep), 10))

def main() -> None:
    log = setup_logger(log_dir=os.path.join(BASE_DIR, "logs"))

    args = parse_args()

    # Decide mode: CLI overrides, else code-level
    if args.mode is None:
        mode = "live" if LIVE_MODE else "backtest"
    else:
        mode = args.mode

    if mode == "backtest":
        run_backtest(args, log)
    elif mode == "paper":
        run_live_or_paper(args, log, dry_run=True)
    elif mode == "live":
        run_live_or_paper(args, log, dry_run=False)
    else:
        raise ValueError(mode)

if __name__ == "__main__":
    main()
