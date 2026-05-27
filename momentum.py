import pandas as pd


def calculate_momentum(prices, lookbacks, weights):
    rows = []

    for ticker, group in prices.groupby("ticker"):
        group = group.sort_values("price_date").reset_index(drop=True)

        if len(group) < max(lookbacks) + 1:
            continue

        latest_price = group.iloc[-1]["adj_close"]
        score = 0
        momentum_values = {}

        for lookback, weight in zip(lookbacks, weights):
            old_price = group.iloc[-lookback - 1]["adj_close"]
            momentum = (latest_price / old_price) - 1

            momentum_values[f"mom_{lookback}d"] = momentum
            score += momentum * weight

        rows.append({
            "ticker": ticker,
            "latest_date": group.iloc[-1]["price_date"].date(),
            "latest_price": latest_price,
            "score": score,
            **momentum_values
        })

    result_df = pd.DataFrame(rows)

    if not result_df.empty:
        result_df = result_df.sort_values("score", ascending=False)
        result_df["rank"] = range(1, len(result_df) + 1)

    return result_df
