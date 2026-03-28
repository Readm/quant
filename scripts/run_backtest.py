"""scripts/run_backtest.py - 回测入口"""
import sys, argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from data.stock_loader  import load_daily as ls_stock
from data.crypto_loader import fetch_ohlcv as ls_crypto
from data.future_loader import load_future_daily as ls_fut
from config.settings import INITIAL_CASH, BACKTEST, RISK
from engine.strategies.day_strategy import DayStrategy
from engine.portfolio.portfolio_manager import PortfolioManager
from engine.risk.risk_engine import RiskEngine
from engine.signals.signal_composer import SignalComposer

def run_backtest(strategy, symbols, start, end, markets):
    print(f"回测: {start} -> {end}")
    pm = PortfolioManager(INITIAL_CASH, RISK["max_position_pct"])
    risk = RiskEngine(pm, {})
    composer = SignalComposer([strategy])
    for market, syms in zip(markets, symbols):
        for sym in syms:
            if market=="stocks":
                df = ls_stock(sym,start,end)
            elif market=="crypto":
                df = ls_crypto(sym.replace("USDT","/USDT"),"1d")
                df = df[df["date"].between(start,end)]
            elif market=="futures":
                df = ls_fut(sym,start.replace("-",""),end.replace("-",""))
            if df.empty: continue
            sig = strategy.on_daily_signal(sym,df)
            order = pm.compute_order(sym,sig,df["close"].iloc[-1],market)
            if order and risk.pre_check(order,df["close"].iloc[-1])["pass"]:
                pm.apply_filled_order(order,df["close"].iloc[-1])
    eq = pm.total_equity({})
    print(f"\n期末资产: ¥{eq:,.0f}  收益率: {(eq/INITIAL_CASH-1)*100:.2f}%")
    print(f"持仓: {pm.positions}")

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--start",default=BACKTEST["start"])
    p.add_argument("--end",  default=BACKTEST["end"])
    p.add_argument("--cash", type=float, default=INITIAL_CASH)
    args=p.parse_args()
    run_backtest(DayStrategy(),[["000001.SZ"],["BTCUSDT"],["IF"]],
                  args.start,args.end,["stocks","crypto","futures"])
