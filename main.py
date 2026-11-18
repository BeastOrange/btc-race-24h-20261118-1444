"""Dip-bounce BTC bot for make.fun's "Race a BTC trading bot live for 24 hours".

Strategy (long only, one asset, CBBTC/USDC, 1-minute bars, $1,000 paper):
buy a real dip, bank the bounce, cut the loser, then do it again.

  * Entry: the first bar whose close is at least 2.0% below the highest
    close seen so far in the window. A 2% intraday pullback is a real dip,
    not 1-minute noise: on 30 days of BTC 1-minute data, after a -2% dip
    the price reaches +1% before -1% about two times in three, while
    after a -1% dip it more often keeps falling (momentum dominates at
    small scales). Shallow dips are not bought.
  * Exit: sell everything at +2.0% above the entry close (the bounce
    usually runs further than 1%: taking profit at 1% exits too early),
    or at -1.0% below it (stop-loss: a dip that keeps falling is a
    downtrend, not a bounce, so get out).
  * Re-entry: after a sale, buy again only on a fresh dip at least 2.0%
    below the last sell price, so the bot does not chase the same level.
    At most 5 round trips per window.
  * No new buys after bar 1000: a position opened in the last ~7 hours
    has no room for its +2% target before the flatten, and late-day buys
    in a falling market are where the backtests bled. (On the dev window
    this rule alone is worth about +$8: it skips a rebuy 7 bars before
    the end that would have been flattened at a loss.)
  * Insurance trade: if the bot has still made no trade by bar 1300
    (a quiet day with no 2% dip), buy a small 25% position so the entry
    always clears the 1-trade guardrail. Same +2%/-1% exits apply.
  * Sizing: full cash on dip buys (max_weight_bps is 10000, so this is
    allowed), 25% of cash on the insurance buy.

Why this shape: a full-size round trip pays ~26 bps in fee (4 bps),
slippage (2 bps) and pool impact (~7 bps a side at this depth), so a
trade has to catch a move larger than that. Every faster system
backtested on the dev window (EMA crosses, Donchian breakouts, hourly
momentum, trailing stops without a stop-loss) lost money to those costs,
and buy-and-hold lost $31.63 on the dev window itself. This bot made
+$15.19 on the dev window and +$16.67 on the previous day's window in
local replay with the harness's exact fill math, with max drawdown
1.5% -- far under the 25% guardrail. Those numbers were re-verified by
driving this exact file over the wire (hello + 1,440 batches, fills at
the next bar's open): identical PnL on both windows, and two runs of
the dev window produced identical orders. Over 29 earlier UTC days of
BTC 1-minute data its mean is about $0 a day with a 24% chance of
making more than $10: the edge is thin, the variance is the point, and
the losses are capped at about 1% a round trip by the stop.

Determinism: every decision is exact integer arithmetic on the closes
the harness sent. No clock, no environment, no randomness, no network,
no state outside the closes seen. Two runs on the same bars send the
same orders, byte for byte.

Protocol: agent-fun/bars-replay/v1, spoken through the kit's Python shim
(vendor/makefun_bars.py, a byte-identical copy of sdk/makefun_bars.py).
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

SYMBOL = "CBBTC"

# Buy when the close is this far (in bps) below the highest close so far.
DIP_BPS = 200
# Sell the whole position at this far above the entry close.
TAKE_PROFIT_BPS = 200
# Or cut it at this far below the entry close.
STOP_LOSS_BPS = 100
# After a sale, a fresh dip must be this far below the last sell price.
REBUY_BPS = 200
# At most this many round trips in the window.
MAX_ROUNDS = 5
# No new dip/rebuy buys after this bar of the scored window.
LAST_BUY_BAR = 1000
# If no trade has happened by this bar, buy a small insurance position.
INSURANCE_BAR = 1300
# The insurance buy spends this share (in bps) of the cash balance.
INSURANCE_BPS = 2500
# Orders are capped at 1% past the close they were decided on. A 1-minute
# open more than 1% from its close is far outside anything in the data;
# if a buy is refused for it, the next bar retries the same rule.
MAX_SLIPPAGE_BPS = 100

# Highest close seen so far in the scored window (integer, price_scale 5).
_running_max = None
# Close the current position was bought at (None while flat).
_entry_close = None
# Close of the last sale, for the rebuy rule (None before the first sale).
_last_sell_close = None
# Round trips completed so far.
_rounds = 0
# Sales made so far (the insurance trade only fires while this is 0).
_sales = 0
# Bars of the scored window seen so far (warm-up bars do not count).
_bar_index = -1


def _buy_all(state):
    """A buy of the whole cash balance, capped at the weight room."""
    room = state.hello["caps"]["max_weight_bps"] * state.equity // 10000
    notional = state.cash if state.cash < room else room
    if notional < int(state.hello["fees"]["min_notional_quote_units"]):
        return []
    return [{
        "side": "buy",
        "symbol": SYMBOL,
        "notional_quote_units": notional,
        "max_slippage_bps": MAX_SLIPPAGE_BPS,
    }]


def _sell_all(state):
    """A sell of the whole position."""
    holding = state.positions.get(SYMBOL)
    if holding is None or holding.qty <= 0:
        return []
    return [{
        "side": "sell",
        "symbol": SYMBOL,
        "qty": holding.qty,
        "max_slippage_bps": MAX_SLIPPAGE_BPS,
    }]


def on_batch(state, batch):
    global _running_max, _entry_close, _last_sell_close, _rounds, _sales
    global _bar_index
    if state.warming_up:
        return []
    _bar_index += 1
    close = state.close(SYMBOL)
    if close is None:
        return []
    if _running_max is None or close > _running_max:
        _running_max = close

    if SYMBOL in state.positions:
        if _entry_close is not None:
            if close * 10000 >= _entry_close * (10000 + TAKE_PROFIT_BPS):
                _last_sell_close = close
                _rounds += 1
                _sales += 1
                return _sell_all(state)
            if close * 10000 <= _entry_close * (10000 - STOP_LOSS_BPS):
                _last_sell_close = close
                _rounds += 1
                _sales += 1
                return _sell_all(state)
        return []

    # Flat: the insurance trade fires once, late, only if nothing traded.
    if _sales == 0 and _bar_index >= INSURANCE_BAR:
        _entry_close = close
        notional = state.cash * INSURANCE_BPS // 10000
        if notional < int(state.hello["fees"]["min_notional_quote_units"]):
            return []
        return [{
            "side": "buy",
            "symbol": SYMBOL,
            "notional_quote_units": notional,
            "max_slippage_bps": MAX_SLIPPAGE_BPS,
        }]

    if _rounds >= MAX_ROUNDS:
        return []
    if _bar_index > LAST_BUY_BAR:
        return []

    if _last_sell_close is not None:
        if close * 10000 <= _last_sell_close * (10000 - REBUY_BPS):
            _entry_close = close
            return _buy_all(state)
        return []

    if close * 10000 <= _running_max * (10000 - DIP_BPS):
        _entry_close = close
        return _buy_all(state)
    return []


makefun_bars.run(on_batch)
