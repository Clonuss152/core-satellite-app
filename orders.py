import pandas as pd

from utils import get_underlying_info


def generate_core_orders(
    core_target,
    core_rank,
    open_positions,
    df,
    core_size,
    core_sell_buffer
):

    core_orders = []

    current_core = []

    if not open_positions.empty:

        current_core = open_positions.loc[
            open_positions["system_type"] == "CORE",
            "underlying_ticker"
        ].tolist()

    core_target_tickers = core_target["ticker"].tolist()

    core_allowed_tickers = core_rank.head(
        core_size + core_sell_buffer
    )["ticker"].tolist()

    for ticker in current_core:

        meta = get_underlying_info(
            ticker,
            df
        )

        if ticker in core_target_tickers:
            action = "HOLD"
            reason = "Im Zielportfolio"

        elif ticker in core_allowed_tickers:
            action = "HOLD"
            reason = "Innerhalb Sell Buffer"

        else:
            action = "SELL"
            reason = "Außerhalb Sell Buffer"

        core_orders.append({

            "system_type": "CORE",
            "action": action,
            "ticker": ticker,

            "company_name": meta["company_name"],
            "isin": meta["isin"],
            "wkn": meta["wkn"],
            "exchange": meta["exchange"],
            "currency": meta["currency"],

            "reason": reason

        })

    sell_count = sum(
        1
        for order in core_orders
        if order["action"] == "SELL"
    )

    open_core_count = len(current_core)

    missing_slots = max(
        0,
        core_size - open_core_count
    )

    buy_slots = sell_count + missing_slots

    buy_candidates = []

    for _, row in core_target.iterrows():

        ticker = row["ticker"]

        if ticker not in current_core:

            buy_candidates.append(row)

    for row in buy_candidates[:buy_slots]:

        ticker = row["ticker"]

        meta = get_underlying_info(
            ticker,
            df
        )

        core_orders.append({

            "system_type": "CORE",
            "action": "BUY",
            "ticker": ticker,

            "company_name": meta["company_name"],
            "isin": meta["isin"],
            "wkn": meta["wkn"],
            "exchange": meta["exchange"],
            "currency": meta["currency"],

            "reason": "Neue Zielposition",

            "target_leverage": row["target_leverage"],
            "rank": row["rank"]

        })

    return pd.DataFrame(core_orders)


def generate_satellite_orders(
    sat_rank,
    open_positions,
    df
):

    orders = []

    sat_a_current = None
    sat_b_current = None

    if not open_positions.empty:

        a_pos = open_positions[
            open_positions["system_type"] == "SATELLITE_A"
        ]

        b_pos = open_positions[
            open_positions["system_type"] == "SATELLITE_B"
        ]

        if not a_pos.empty:
            sat_a_current = a_pos.iloc[0]["underlying_ticker"]

        if not b_pos.empty:
            sat_b_current = b_pos.iloc[0]["underlying_ticker"]

    rank_list = sat_rank.sort_values(
        "rank"
    )["ticker"].tolist()

    if len(rank_list) == 0:
        return pd.DataFrame()

    a_target = rank_list[0]

    b_target = None

    for ticker in rank_list:

        if ticker != a_target:
            b_target = ticker
            break

    #
    # SATELLITE A
    #

    if sat_a_current is not None:

        current_rank_row = sat_rank[
            sat_rank["ticker"] == sat_a_current
        ]

        current_rank = (
            int(current_rank_row.iloc[0]["rank"])
            if not current_rank_row.empty
            else 999
        )

        meta = get_underlying_info(
            sat_a_current,
            df
        )

        if current_rank <= 7:

            orders.append({
                "system_type": "SATELLITE_A",
                "action": "HOLD",
                "ticker": sat_a_current,
                "reason": "Innerhalb Sell Buffer",
                "target_leverage": 10.0,
                "rank": current_rank,
                **meta
            })

        else:

            orders.append({
                "system_type": "SATELLITE_A",
                "action": "SELL",
                "ticker": sat_a_current,
                "reason": "Rank > 7",
                "rank": current_rank,
                **meta
            })

            meta_new = get_underlying_info(
                a_target,
                df
            )

            orders.append({
                "system_type": "SATELLITE_A",
                "action": "BUY",
                "ticker": a_target,
                "reason": "Neue A Position",
                "target_leverage": 10.0,
                "rank": 1,
                **meta_new
            })

    else:

        meta = get_underlying_info(
            a_target,
            df
        )

        orders.append({
            "system_type": "SATELLITE_A",
            "action": "BUY",
            "ticker": a_target,
            "reason": "Keine offene A Position",
            "target_leverage": 10.0,
            "rank": 1,
            **meta
        })

    #
    # B FREIGEBEN FÜR A
    #

    if sat_b_current == a_target:

        meta = get_underlying_info(
            sat_b_current,
            df
        )

        orders.append({
            "system_type": "SATELLITE_B",
            "action": "SELL",
            "ticker": sat_b_current,
            "reason": "B freigemacht für A",
            **meta
        })

        sat_b_current = None

    #
    # SATELLITE B
    #

    if b_target is None:
        return pd.DataFrame(orders)

    if sat_b_current is not None:

        current_rank_row = sat_rank[
            sat_rank["ticker"] == sat_b_current
        ]

        current_rank = (
            int(current_rank_row.iloc[0]["rank"])
            if not current_rank_row.empty
            else 999
        )

        meta = get_underlying_info(
            sat_b_current,
            df
        )

        if (
            current_rank <= 7
            and sat_b_current != a_target
        ):

            orders.append({
                "system_type": "SATELLITE_B",
                "action": "HOLD",
                "ticker": sat_b_current,
                "reason": "Innerhalb Sell Buffer",
                "rank": current_rank,
                **meta
            })

        else:

            orders.append({
                "system_type": "SATELLITE_B",
                "action": "SELL",
                "ticker": sat_b_current,
                "reason": "Rotation",
                "rank": current_rank,
                **meta
            })

            meta_new = get_underlying_info(
                b_target,
                df
            )

            orders.append({
                "system_type": "SATELLITE_B",
                "action": "BUY",
                "ticker": b_target,
                "reason": "Neue B Position",
                "target_leverage": 7.0,
                "rank": 2,
                **meta_new
            })

    else:

        meta = get_underlying_info(
            b_target,
            df
        )

        orders.append({
            "system_type": "SATELLITE_B",
            "action": "BUY",
            "ticker": b_target,
            "reason": "Keine offene B Position",
            "target_leverage": 7.0,
            "rank": 2,
            **meta
        })

    return pd.DataFrame(orders)
