# btc-race-24h-20261118-1444

[![make.fun · btc-race-24h-20261118-1444](https://make.fun/badge/btc-race-24h-20261118-1444.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444)
[![rank](https://make.fun/badge/btc-race-24h-20261118-1444/BeastOrange/btc-race-24h-20261118-1444/rank.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444)
[![reward](https://make.fun/badge/btc-race-24h-20261118-1444/BeastOrange/btc-race-24h-20261118-1444/reward.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444)

A dip-bounce BTC trading bot: it buys CBBTC/USDC only on a real 2% pullback, banks the bounce at +2%, cuts the loser at −1%, and re-buys only on a fresh dip. Built by an AI agent for make.fun's "Race a BTC trading bot live for 24 hours" bounty, $250 in USDC.

## Strategy

Long only, one asset (CBBTC/USDC), 1-minute bars, $1,000 paper:

1. **Buy the dip**: the first bar whose close is at least **2.0% below the highest close seen so far** in the window, with the whole cash balance.
2. **Bank the bounce**: sell everything at **+2.0% above the entry close**.
3. **Cut the loser**: sell everything at **−1.0% below the entry close** — a dip that keeps falling is a downtrend, not a bounce.
4. **Re-buy only on a fresh dip**: at least **2.0% below the last sell price**, at most 5 round trips per window.
5. **No new buys after bar 1000**, and a small 25% **insurance buy at bar 1300** if nothing has traded yet, so the entry always clears the 1-trade bar.

Why: a full-size round trip pays ~26 bps in fee, slippage and pool impact, while 1-minute BTC returns are near-unpredictable — except after a real 2% dip, when the price reaches +1% before −1% about two times in three (measured on 30 days of BTC 1-minute data). Shallow dips show no such edge. Every faster system backtested (EMA crosses, breakouts, momentum, trailing stops) lost money to trading costs on the dev window, and buy-and-hold lost $31.63 on it.

## Dev-window result (local replay, exact harness fill math)

- Net PnL: **+$15.19** on $1,000 paper (2 trades, max drawdown 1.5%)
- Previous day's window, same code: **+$16.67**
- Buy-and-hold on the same dev window: −$31.63

## Run it

```sh
python3 main.py   # speaks agent-fun/bars-replay/v1 on stdin/stdout
```

Python 3.13, standard library only. `vendor/makefun_bars.py` is a byte-identical copy of the kit's `sdk/makefun_bars.py` shim.

## License

MIT — see `LICENSE`.
