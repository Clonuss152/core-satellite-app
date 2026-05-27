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

            "system": "CORE",
            "action": action,
            "ticker": ticker,

            "company_name": meta["company_name"],
            "isin": meta["isin"],
            "wkn": meta["wkn"],
            "exchange": meta["exchange"],
            "currency": meta["currency"],

            "reason": reason

        })

    for _, row in core_target.iterrows():

        ticker = row["ticker"]

        if ticker not in current_core:

            meta = get_underlying_info(
                ticker,
                df
            )

            core_orders.append({

                "system": "CORE",
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


def generate_sat_orders(
    sat_target,
    sat_rank,
    open_positions,
    df
):

    sat_orders = []

    current_sat = []

    if not open_positions.empty:

        current_sat = open_positions.loc[
            open_positions["system_type"] == "SATELLITE",
            "underlying_ticker"
        ].tolist()

    if sat_target.empty:
        return pd.DataFrame()

    sat_top = sat_target.iloc[0]["ticker"]

    if current_sat:

        current_sat_ticker = current_sat[0]

        current_rank_row = sat_rank[
            sat_rank["ticker"] == current_sat_ticker
        ]

        if not current_rank_row.empty:
            current_rank = int(
                current_rank_row.iloc[0]["rank"]
            )

        else:
            current_rank = 999

        meta_current = get_underlying_info(
            current_sat_ticker,
            df
        )

        if current_rank <= 4:

            sat_orders.append({

                "system": "SATELLITE",
                "action": "HOLD",
                "ticker": current_sat_ticker,

                "company_name": meta_current["company_name"],
                "isin": meta_current["isin"],
                "wkn": meta_current["wkn"],
                "exchange": meta_current["exchange"],
                "currency": meta_current["currency"],

                "reason": "Innerhalb SAT Sell Buffer",
                "rank": current_rank

            })

        else:

            sat_orders.append({

                "system": "SATELLITE",
                "action": "SELL",
                "ticker": current_sat_ticker,

                "company_name": meta_current["company_name"],
                "isin": meta_current["isin"],
                "wkn": meta_current["wkn"],
                "exchange": meta_current["exchange"],
                "currency": meta_current["currency"],

                "reason": "Rank > 4",
                "rank": current_rank

            })

            meta_new = get_underlying_info(
                sat_top,
                df
            )

            sat_orders.append({

                "system": "SATELLITE",
                "action": "BUY",
                "ticker": sat_top,

                "company_name": meta_new["company_name"],
                "isin": meta_new["isin"],
                "wkn": meta_new["wkn"],
                "exchange": meta_new["exchange"],
                "currency": meta_new["currency"],

                "reason": "Neue Top-1 Position",

                "target_leverage": 10.0,
                "rank": 1

            })

    else:

        meta = get_underlying_info(
            sat_top,
            df
        )

        sat_orders.append({

            "system": "SATELLITE",
            "action": "BUY",
            "ticker": sat_top,

            "company_name": meta["company_name"],
            "isin": meta["isin"],
            "wkn": meta["wkn"],
            "exchange": meta["exchange"],
            "currency": meta["currency"],

            "reason": "Keine offene SAT Position",

            "target_leverage": 10.0,
            "rank": 1

        })

    return pd.DataFrame(sat_orders)
