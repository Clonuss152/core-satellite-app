import pandas as pd


def calculate_open_positions_from_trades(trade_df):

    if trade_df.empty:
        return pd.DataFrame()

    grouped = trade_df.groupby(
        [
            "system_type",
            "underlying_ticker",
            "turbo_wkn",
        ],
        dropna=False,
    ).apply(
        lambda x: pd.Series(
            {
                "BUY_QTY": x.loc[
                    x["action"] == "BUY",
                    "quantity",
                ].sum(),
                "SELL_QTY": x.loc[
                    x["action"] == "SELL",
                    "quantity",
                ].sum(),
                "turbo_isin": x.iloc[-1].get(
                    "turbo_isin",
                    "",
                ),
            }
        )
    ).reset_index()

    grouped["OPEN_QTY"] = (
        grouped["BUY_QTY"]
        - grouped["SELL_QTY"]
    )

    return grouped[
        grouped["OPEN_QTY"] > 0
    ].copy()


def check_live_value_status(
    open_positions_df,
    live_values_df,
    required_date,
):

    result = {
        "complete": True,
        "buy_orders_enabled": True,
        "missing": [],
        "stale": [],
        "required_date": str(required_date),
    }

    if open_positions_df.empty:
        return result

    if live_values_df is None or live_values_df.empty:
        result["complete"] = False
        result["buy_orders_enabled"] = False

        for _, pos in open_positions_df.iterrows():
            result["missing"].append(
                f"{pos['system_type']} | {pos['underlying_ticker']}"
            )

        return result

    live_values = live_values_df.copy()

    live_values["valuation_date"] = pd.to_datetime(
        live_values["valuation_date"]
    ).dt.date

    required_date = pd.to_datetime(
        required_date
    ).date()

    for _, pos in open_positions_df.iterrows():

        label = (
            f"{pos['system_type']} | "
            f"{pos['underlying_ticker']}"
        )

        match = live_values[
            (live_values["system_type"] == pos["system_type"])
            &
            (
                live_values["underlying_ticker"]
                == pos["underlying_ticker"]
            )
        ]

        if match.empty:
            result["complete"] = False
            result["buy_orders_enabled"] = False
            result["missing"].append(label)
            continue

        exact_match = match[
            match["valuation_date"] == required_date
        ]

        if exact_match.empty:
            latest = match.sort_values(
                "valuation_date",
                ascending=False,
            ).iloc[0]

            result["complete"] = False
            result["buy_orders_enabled"] = False
            result["stale"].append(
                f"{label} ({latest['valuation_date']})"
            )

    return result
