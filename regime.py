import pandas as pd


def get_regime(core_prices):
    rows = []

    for ticker, group in core_prices.groupby("ticker"):
        group = group.sort_values("price_date").reset_index(drop=True)

        if len(group) < 253:
            continue

        latest_price = group.iloc[-1]["adj_close"]
        old_price = group.iloc[-253]["adj_close"]
        mom_252 = (latest_price / old_price) - 1

        rows.append({
            "ticker": ticker,
            "mom_252d": mom_252
        })

    regime_df = pd.DataFrame(rows)

    if regime_df.empty:
        return "UNKNOWN", None

    regime_df = regime_df.sort_values("mom_252d", ascending=False)
    top10_avg = regime_df.head(10)["mom_252d"].mean()

    if top10_avg > 1.00:
        return "STRONG", top10_avg

    if top10_avg > 0.30:
        return "NORMAL", top10_avg

    return "WEAK", top10_avg
