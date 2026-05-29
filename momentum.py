import pandas as pd


def calculate_momentum(prices, lookbacks, weights):
    rows = []

    for ticker, group in prices.groupby("ticker"):
        group = group.sort_values("price_date").reset_index(drop=True)

        if len(group) < max(lookbacks) + 1:
            continue

        latest_price = group.iloc[-1]["adj_close"]
        momentum_values = {}

        for lookback in lookbacks:
            old_price = group.iloc[-lookback - 1]["adj_close"]
            momentum = (latest_price / old_price) - 1

            momentum_values[f"mom_{lookback}d"] = momentum

        rows.append(
            {
                "ticker": ticker,
                "latest_date": group.iloc[-1]["price_date"].date(),
                "latest_price": latest_price,
                **momentum_values,
            }
        )

    result_df = pd.DataFrame(rows)

    if result_df.empty:
        return result_df

    score = pd.Series(
        0.0,
        index=result_df.index,
    )

    for lookback, weight in zip(lookbacks, weights):
        momentum_col = f"mom_{lookback}d"
        rank_col = f"rank_{lookback}d"

        result_df[rank_col] = result_df[momentum_col].rank(
            ascending=False,
            method="min",
        )

        score += result_df[rank_col] * weight

    result_df["score"] = score

    result_df = result_df.sort_values(
        "score",
        ascending=True,
    )

    result_df["rank"] = range(
        1,
        len(result_df) + 1,
    )
    print(result_df[
        [
            "ticker",
            "score",
            "rank"
        ]
    ].head(10))
    return result_df
