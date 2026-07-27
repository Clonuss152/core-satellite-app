import pandas as pd

from config import (
    CORE_TARGET_WEIGHT,
    SATELLITE_A_WEIGHT,
    SATELLITE_B_WEIGHT,
)


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

def get_latest_cash_update_date(cash_state_df):

    if cash_state_df.empty:
        return None

    cash_state_df = cash_state_df.copy()

    if "snapshot_date" not in cash_state_df.columns:
        return None

    cash_state_df["snapshot_date"] = pd.to_datetime(
        cash_state_df["snapshot_date"]
    )

    cash_state_df = cash_state_df.sort_values(
        "snapshot_date"
    )

    latest_date = cash_state_df.iloc[-1]["snapshot_date"]

    if pd.isna(latest_date):
        return None

    return latest_date.date()

def get_latest_sell_trade_date(trade_df):

    if trade_df.empty:
        return None

    if "action" not in trade_df.columns:
        return None

    if "trade_date" not in trade_df.columns:
        return None

    sell_trades = trade_df[
        trade_df["action"] == "SELL"
    ].copy()

    if sell_trades.empty:
        return None

    sell_trades["trade_date"] = pd.to_datetime(
        sell_trades["trade_date"]
    )

    sell_trades = sell_trades.sort_values(
        "trade_date"
    )

    latest_sell_date = sell_trades.iloc[-1]["trade_date"]

    if pd.isna(latest_sell_date):
        return None

    return latest_sell_date.date()

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
                "turbo_isin": x.iloc[-1].get(
                    "turbo_isin",
                    ""
                ),
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


def calculate_open_live_values(
    open_costs,
    live_values_df,
    required_live_value_date,
):

    result = {
        "total_open_live_value": 0.0,
        "core_open_live_value": 0.0,
        "satellite_a_open_live_value": 0.0,
        "satellite_b_open_live_value": 0.0,
        "live_values_complete": True,
        "missing_live_values": [],
        "stale_live_values": [],
    }

    if open_costs.empty:
        return result

    if live_values_df is None or live_values_df.empty:

        result["live_values_complete"] = False

        for _, pos in open_costs.iterrows():
            result["missing_live_values"].append(
                f"{pos['system_type']} | {pos['underlying_ticker']}"
            )

        return result

    live_values = live_values_df.copy()

    live_values["valuation_date"] = pd.to_datetime(
        live_values["valuation_date"]
    ).dt.date

    required_date = pd.to_datetime(
        required_live_value_date
    ).date()

    for _, pos in open_costs.iterrows():

        match = live_values[
            (live_values["system_type"] == pos["system_type"])
            &
            (
                live_values["underlying_ticker"]
                == pos["underlying_ticker"]
            )
        ].copy()

        label = (
            f"{pos['system_type']} | "
            f"{pos['underlying_ticker']}"
        )

        if match.empty:

            result["live_values_complete"] = False
            result["missing_live_values"].append(label)
            continue

        exact_match = match[
            match["valuation_date"] == required_date
        ].copy()

        if exact_match.empty:

            latest = match.sort_values(
                "valuation_date",
                ascending=False
            ).iloc[0]

            result["live_values_complete"] = False
            result["stale_live_values"].append(
                f"{label} ({latest['valuation_date']})"
            )
            continue

        if "created_at" in exact_match.columns:
            exact_match = exact_match.sort_values(
                "created_at",
                ascending=False
            )

        live_value = exact_match.iloc[0].get(
            "live_position_value",
            0.0
        )

        if pd.isna(live_value):
            live_value = 0.0

        live_value = float(live_value)

        result["total_open_live_value"] += live_value

        if pos["system_type"] == "CORE":
            result["core_open_live_value"] += live_value

        elif pos["system_type"] == "SATELLITE_A":
            result["satellite_a_open_live_value"] += live_value

        elif pos["system_type"] == "SATELLITE_B":
            result["satellite_b_open_live_value"] += live_value

    return result


def calculate_capital_plan(
    trade_df,
    cash_state_df,
    core_orders,
    sat_orders,
    live_values_df=None,
    required_live_value_date=None,
    sell_orders_present=False,
):

    broker_cash = get_latest_broker_cash(
        cash_state_df
    )

    latest_cash_update_date = get_latest_cash_update_date(
        cash_state_df
    )

    latest_sell_trade_date = get_latest_sell_trade_date(
        trade_df
    )

    cash_updated_after_latest_sell = True

    if (
        latest_sell_trade_date is not None
        and latest_cash_update_date is not None
        and latest_cash_update_date < latest_sell_trade_date
    ):
        cash_updated_after_latest_sell = False

    if (
        latest_sell_trade_date is not None
        and latest_cash_update_date is None
    ):
        cash_updated_after_latest_sell = False

    open_costs = calculate_open_costs(
        trade_df
    )

    total_open_cost = 0.0
    satellite_a_open_cost = 0.0
    satellite_b_open_cost = 0.0

    if not open_costs.empty:

        total_open_cost = float(
            open_costs["OPEN_COST"].sum()
        )

        satellite_a_open_cost = float(
            open_costs.loc[
                open_costs["system_type"] == "SATELLITE_A",
                "OPEN_COST"
            ].sum()
        )

        satellite_b_open_cost = float(
            open_costs.loc[
                open_costs["system_type"] == "SATELLITE_B",
                "OPEN_COST"
            ].sum()
        )

    satellite_open_cost = (
        satellite_a_open_cost
        + satellite_b_open_cost
    )

    use_live_values = (
        live_values_df is not None
        and required_live_value_date is not None
    )

    live_value_result = {
        "total_open_live_value": 0.0,
        "core_open_live_value": 0.0,
        "satellite_a_open_live_value": 0.0,
        "satellite_b_open_live_value": 0.0,
        "live_values_complete": False,
        "missing_live_values": [],
        "stale_live_values": [],
    }

    if use_live_values:
        live_value_result = calculate_open_live_values(
            open_costs=open_costs,
            live_values_df=live_values_df,
            required_live_value_date=required_live_value_date,
        )

        if live_value_result["live_values_complete"]:
            system_capital = (
                broker_cash
                + live_value_result["total_open_live_value"]
            )

            capital_basis = "MANUAL_LIVE_VALUES"

        else:
            system_capital = broker_cash + total_open_cost
            capital_basis = "OPEN_COSTS_FALLBACK_LIVE_VALUES_INCOMPLETE"

    else:
        system_capital = broker_cash + total_open_cost
        capital_basis = "OPEN_COSTS"

    satellite_a_open_value = (
        live_value_result["satellite_a_open_live_value"]
        if use_live_values
        else satellite_a_open_cost
    )

    satellite_b_open_value = (
        live_value_result["satellite_b_open_live_value"]
        if use_live_values
        else satellite_b_open_cost
    )

    satellite_open_value = (
        satellite_a_open_value
        + satellite_b_open_value
    )

    satellite_a_target_capital = (
        system_capital * SATELLITE_A_WEIGHT
    )

    satellite_b_target_capital = (
        system_capital * SATELLITE_B_WEIGHT
    )

    satellite_target_capital = (
        satellite_a_target_capital
        + satellite_b_target_capital
    )

    satellite_a_is_open = satellite_a_open_cost > 0
    satellite_b_is_open = satellite_b_open_cost > 0

    satellite_a_reserve = (
        0.0
        if satellite_a_is_open
        else min(
            broker_cash,
            satellite_a_target_capital
        )
    )

    cash_after_a_reserve = max(
        0.0,
        broker_cash - satellite_a_reserve
    )

    satellite_b_reserve = (
        0.0
        if satellite_b_is_open
        else min(
            cash_after_a_reserve,
            satellite_b_target_capital
        )
    )

    satellite_reserve = (
        satellite_a_reserve
        + satellite_b_reserve
    )

    core_available_cash = max(
        0.0,
        broker_cash - satellite_reserve
    )

    buy_orders_enabled = True

    if (
        use_live_values
        and not live_value_result["live_values_complete"]
    ):
        buy_orders_enabled = False

    core_orders = core_orders.copy()
    sat_orders = sat_orders.copy()

    if not core_orders.empty:

        core_orders["suggested_amount"] = 0.0

        core_target_capital = (
            system_capital
            * CORE_TARGET_WEIGHT
        )

        core_buy_orders = core_orders[
            core_orders["action"] == "BUY"
        ].copy()

        core_portfolio_size = (
            len(core_buy_orders)
            + len(
                core_orders[
                    core_orders["action"] == "HOLD"
                ]
            )
        )

        if core_portfolio_size > 0:
            core_slot_target = (
                core_target_capital
                / core_portfolio_size
            )
        else:
            core_slot_target = 0.0

        remaining_core_cash = core_available_cash

        if (
            not core_buy_orders.empty
            and buy_orders_enabled
        ):

            core_buy_orders = (
                core_buy_orders
                .sort_values("rank")
            )

            for idx, _ in core_buy_orders.iterrows():

                planned_amount = min(
                    core_slot_target,
                    remaining_core_cash,
                )

                core_orders.loc[
                    idx,
                    "suggested_amount",
                ] = planned_amount

                remaining_core_cash = max(
                    0.0,
                    remaining_core_cash
                    - planned_amount,
                )

    if not sat_orders.empty:

        sat_orders["suggested_amount"] = 0.0

        a_buy_mask = (
            (sat_orders["system_type"] == "SATELLITE_A")
            & (sat_orders["action"] == "BUY")
        )

        b_buy_mask = (
            (sat_orders["system_type"] == "SATELLITE_B")
            & (sat_orders["action"] == "BUY")
        )

        if (
            a_buy_mask.any()
            and buy_orders_enabled
        ):
            sat_orders.loc[
                a_buy_mask,
                "suggested_amount"
            ] = satellite_a_reserve

        if (
            b_buy_mask.any()
            and buy_orders_enabled
        ):
            sat_orders.loc[
                b_buy_mask,
                "suggested_amount"
            ] = satellite_b_reserve

    satellite_a_gap = (
        satellite_a_open_value
        - satellite_a_target_capital
    )

    satellite_b_gap = (
        satellite_b_open_value
        - satellite_b_target_capital
    )

    satellite_gap = (
        satellite_open_value
        - satellite_target_capital
    )

    buy_block_reason = None

    if not live_value_result["live_values_complete"]:
        buy_block_reason = "LIVE_VALUES_STALE"

    elif sell_orders_present:
        buy_block_reason = "SELL_ORDERS_PENDING"

    elif not cash_updated_after_latest_sell:
        buy_block_reason = "CASH_UPDATE_REQUIRED"

    elif broker_cash <= 0:
        buy_block_reason = "INSUFFICIENT_BROKER_CASH"

    metrics = {
        "broker_cash": broker_cash,
        "system_capital": system_capital,
        "capital_basis": capital_basis,

        "core_target_weight": CORE_TARGET_WEIGHT,

        "total_open_cost": total_open_cost,
        "total_open_live_value": live_value_result[
            "total_open_live_value"
        ],

        "core_open_live_value": live_value_result[
            "core_open_live_value"
        ],

        "satellite_target_capital": satellite_target_capital,
        "satellite_limit": satellite_target_capital,

        "satellite_open_cost": satellite_open_cost,
        "satellite_open_live_value": satellite_open_value,

        "satellite_gap": satellite_gap,
        "satellite_reserve": satellite_reserve,

        "satellite_a_target_capital": satellite_a_target_capital,
        "satellite_a_open_cost": satellite_a_open_cost,
        "satellite_a_open_live_value": satellite_a_open_value,
        "satellite_a_gap": satellite_a_gap,
        "satellite_a_reserve": satellite_a_reserve,
        "satellite_a_is_open": satellite_a_is_open,

        "satellite_b_target_capital": satellite_b_target_capital,
        "satellite_b_open_cost": satellite_b_open_cost,
        "satellite_b_open_live_value": satellite_b_open_value,
        "satellite_b_gap": satellite_b_gap,
        "satellite_b_reserve": satellite_b_reserve,
        "satellite_b_is_open": satellite_b_is_open,

        "core_available_cash": core_available_cash,
        "satellite_is_open": (
            satellite_a_is_open
            or satellite_b_is_open
        ),

        "live_values_complete": live_value_result[
            "live_values_complete"
        ],
        "missing_live_values": live_value_result[
            "missing_live_values"
        ],
        "stale_live_values": live_value_result[
            "stale_live_values"
        ],
        "required_live_value_date": (
            str(required_live_value_date)
            if required_live_value_date is not None
            else None
        ),
        "buy_orders_enabled": buy_orders_enabled,
        "buy_block_reason": buy_block_reason,
        "latest_cash_update_date": (
            str(latest_cash_update_date)
            if latest_cash_update_date is not None
            else None
        ),
        "latest_sell_trade_date": (
            str(latest_sell_trade_date)
            if latest_sell_trade_date is not None
            else None
        ),
        "cash_updated_after_latest_sell": cash_updated_after_latest_sell,
    }

    return metrics, core_orders, sat_orders
