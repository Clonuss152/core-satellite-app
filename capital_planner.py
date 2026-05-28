import pandas as pd


def get_latest_broker_cash(cash_state_df):

    if cash_state_df.empty:
        return 0.0

    cash_state_df = cash_state_df.copy()

    cash_state_df["snapshot_date"] = pd.to_datetime(
        cash_state_df["snapshot_date"]
    )

    cash_state_df = cash_state_df.sort_values(
        "snapshot_date"
    )

    latest_cash = cash_state_df.iloc[-1][
        "broker_cash"
    ]

    if pd.isna(latest_cash):
        return 0.0

    return float(latest_cash)


def calculate_open_costs(trade_df):

    if trade_df.empty:
        return pd.DataFrame()

    df = trade_df.copy()

    if "gross_amount" not in df.columns:
        df["gross_amount"] = df["quantity"] * df["price"]

    grouped = df.groupby(
        [
            "system_type",
            "underlying_ticker",
            "turbo_wkn"
        ],
        dropna=False
    ).apply(
        lambda x: pd.Series(
            {
                "BUY_QTY": x.loc[
                    x["action"] == "BUY",
                    "quantity"
                ].sum(),
                "SELL_QTY": x.loc[
                    x["action"] == "SELL",
                    "quantity"
                ].sum(),
                "BUY_COST": x.loc[
                    x["action"] == "BUY",
                    "gross_amount"
                ].sum(),
                "SELL_VALUE": x.loc[
                    x["action"] == "SELL",
                    "gross_amount"
                ].sum(),
            }
        )
    ).reset_index()

    grouped["OPEN_QTY"] = (
        grouped["BUY_QTY"] - grouped["SELL_QTY"]
    )

    grouped = grouped[
        grouped["OPEN_QTY"] > 0
    ].copy()

    grouped["OPEN_COST"] = (
        grouped["BUY_COST"] - grouped["SELL_VALUE"]
    )

    grouped["OPEN_COST"] = grouped["OPEN_COST"].clip(
        lower=0
    )

    return grouped


def calculate_capital_plan(
    trade_df,
    cash_state_df,
    core_orders,
    sat_orders
):

    broker_cash = get_latest_broker_cash(
        cash_df
    )

    open_costs = calculate_open_costs(
        trade_df
    )

    total_open_cost = 0.0
    satellite_open_cost = 0.0

    if not open_costs.empty:

        total_open_cost = float(
            open_costs["OPEN_COST"].sum()
        )

        satellite_open_cost = float(
            open_costs.loc[
                open_costs["system_type"] == "SATELLITE",
                "OPEN_COST"
            ].sum()
        )

    system_capital = broker_cash + total_open_cost

    satellite_limit = system_capital * 0.05

    satellite_is_open = satellite_open_cost > 0

    if satellite_is_open:
        satellite_reserve = 0.0
    else:
        satellite_reserve = min(
            broker_cash,
            satellite_limit
        )

    core_available_cash = max(
        0.0,
        broker_cash - satellite_reserve
    )

    core_orders = core_orders.copy()
    sat_orders = sat_orders.copy()

    if not core_orders.empty:

        core_orders["suggested_amount"] = 0.0

        core_buy_count = len(
            core_orders[
                core_orders["action"] == "BUY"
            ]
        )

        if core_buy_count > 0:

            amount_per_core_buy = (
                core_available_cash / core_buy_count
            )

            core_orders.loc[
                core_orders["action"] == "BUY",
                "suggested_amount"
            ] = amount_per_core_buy

    if not sat_orders.empty:

        sat_orders["suggested_amount"] = 0.0

        sat_buy_count = len(
            sat_orders[
                sat_orders["action"] == "BUY"
            ]
        )

        if (
            sat_buy_count > 0
            and not satellite_is_open
        ):

            sat_orders.loc[
                sat_orders["action"] == "BUY",
                "suggested_amount"
            ] = satellite_reserve

    metrics = {
        "broker_cash": broker_cash,
        "system_capital": system_capital,
        "satellite_limit": satellite_limit,
        "satellite_open_cost": satellite_open_cost,
        "satellite_reserve": satellite_reserve,
        "core_available_cash": core_available_cash,
    }

    return metrics, core_orders, sat_orders
