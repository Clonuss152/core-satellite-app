import pandas as pd


def calculate_trade_statistics(trade_df):

    empty_result = {
        "total_trades": 0,
        "winning_trades": 0,
        "losing_trades": 0,
        "win_rate": 0.0,

        "ko_trades": 0,
        "ko_rate": 0.0,
        "core_ko_trades": 0,
        "sat_ko_trades": 0,
        "ko_loss": 0.0,

        "total_profit": 0.0,
        "total_loss": 0.0,
        "net_result": 0.0,
        "average_win": 0.0,
        "average_loss": 0.0,

        "core_trades": 0,
        "core_winning_trades": 0,
        "core_losing_trades": 0,
        "core_net_result": 0.0,

        "sat_trades": 0,
        "sat_winning_trades": 0,
        "sat_losing_trades": 0,
        "sat_net_result": 0.0,

        "total_fees": 0.0,
        "total_taxes": 0.0,
        "total_cashflow_adjustment": 0.0,

        "profit_factor": 0.0,
        "largest_winner": 0.0,
        "largest_loser": 0.0,

        "core_win_rate": 0.0,
        "sat_win_rate": 0.0,

        "core_average_win": 0.0,
        "core_average_loss": 0.0,

        "sat_average_win": 0.0,
        "sat_average_loss": 0.0,
    }

    empty_closed = pd.DataFrame(
        columns=[
            "system_type",
            "underlying_ticker",
            "turbo_wkn",
            "exit_reason",
            "BUY_QTY",
            "SELL_QTY",
            "BUY_CASH",
            "SELL_CASH",
            "BUY_DATE",
            "SELL_DATE",
            "OPEN_QTY",
            "RESULT",
            "RESULT_PCT",
            "HOLD_DAYS",
        ]
    )

    if trade_df.empty:
        return empty_result, empty_closed

    df = trade_df.copy()

    for col in [
        "quantity",
        "price",
        "gross_amount",
        "net_cash_effect",
        "fees",
        "taxes",
        "cashflow_adjustment",
    ]:
        if col in df.columns:
            df[col] = pd.to_numeric(
                df[col],
                errors="coerce",
            ).fillna(0.0)

    if "net_cash_effect" not in df.columns:
        df["net_cash_effect"] = df["quantity"] * df["price"]

    if "fees" not in df.columns:
        df["fees"] = 0.0

    if "taxes" not in df.columns:
        df["taxes"] = 0.0

    if "cashflow_adjustment" not in df.columns:
        df["cashflow_adjustment"] = 0.0

    if "exit_reason" not in df.columns:
        df["exit_reason"] = None

    grouped = df.groupby(
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

                "BUY_CASH": x.loc[
                    x["action"] == "BUY",
                    "net_cash_effect",
                ].abs().sum(),

                "SELL_CASH": x.loc[
                    x["action"] == "SELL",
                    "net_cash_effect",
                ].abs().sum(),

                "BUY_DATE": pd.to_datetime(
                    x.loc[
                        x["action"] == "BUY",
                        "trade_date",
                    ]
                ).min(),

                "SELL_DATE": pd.to_datetime(
                    x.loc[
                        x["action"] == "SELL",
                        "trade_date",
                    ]
                ).max(),

                "exit_reason": (
                    x.loc[
                        x["action"] == "SELL",
                        "exit_reason",
                    ]
                    .dropna()
                    .iloc[-1]
                    if not x.loc[
                        x["action"] == "SELL",
                        "exit_reason",
                    ].dropna().empty
                    else None
                ),
            }
        )
    ).reset_index()

    grouped["OPEN_QTY"] = (
        grouped["BUY_QTY"] - grouped["SELL_QTY"]
    )

    closed_positions = grouped[
        (grouped["BUY_QTY"] > 0)
        & (grouped["OPEN_QTY"] <= 0)
    ].copy()

    if closed_positions.empty:
        result = empty_result.copy()
        result["total_fees"] = float(df["fees"].sum())
        result["total_taxes"] = float(df["taxes"].sum())
        result["total_cashflow_adjustment"] = float(
            df["cashflow_adjustment"].sum()
        )
        return result, empty_closed

    closed_positions["RESULT"] = (
        closed_positions["SELL_CASH"]
        - closed_positions["BUY_CASH"]
    )

    closed_positions["RESULT_PCT"] = 0.0

    closed_positions.loc[
        closed_positions["BUY_CASH"] > 0,
        "RESULT_PCT",
    ] = (
        closed_positions["RESULT"]
        / closed_positions["BUY_CASH"]
    )

    closed_positions["HOLD_DAYS"] = (
        pd.to_datetime(closed_positions["SELL_DATE"])
        - pd.to_datetime(closed_positions["BUY_DATE"])
    ).dt.days

    winners = closed_positions[
        closed_positions["RESULT"] > 0
    ]

    losers = closed_positions[
        closed_positions["RESULT"] < 0
    ]

    ko_closed = closed_positions[
        closed_positions["exit_reason"] == "KO"
    ]

    core_closed = closed_positions[
        closed_positions["system_type"] == "CORE"
    ]

    sat_closed = closed_positions[
        closed_positions["system_type"] == "SATELLITE"
    ]

    core_winners = core_closed[
        core_closed["RESULT"] > 0
    ]

    core_losers = core_closed[
        core_closed["RESULT"] < 0
    ]

    sat_winners = sat_closed[
        sat_closed["RESULT"] > 0
    ]

    sat_losers = sat_closed[
        sat_closed["RESULT"] < 0
    ]

    core_ko = core_closed[
        core_closed["exit_reason"] == "KO"
    ]

    sat_ko = sat_closed[
        sat_closed["exit_reason"] == "KO"
    ]

    total_trades = len(closed_positions)
    winning_trades = len(winners)
    losing_trades = len(losers)

    gross_profit = float(
        winners["RESULT"].sum()
    )

    gross_loss = abs(
        float(
            losers["RESULT"].sum()
        )
    )

    profit_factor = (
        gross_profit / gross_loss
        if gross_loss > 0
        else 0.0
    )

    largest_winner = (
        float(winners["RESULT"].max())
        if not winners.empty
        else 0.0
    )

    largest_loser = (
        float(losers["RESULT"].min())
        if not losers.empty
        else 0.0
    )

    core_win_rate = (
        len(core_winners) / len(core_closed)
        if len(core_closed) > 0
        else 0.0
    )

    sat_win_rate = (
        len(sat_winners) / len(sat_closed)
        if len(sat_closed) > 0
        else 0.0
    )

    ko_trades = len(ko_closed)

    result = {
        "total_trades": total_trades,
        "winning_trades": winning_trades,
        "losing_trades": losing_trades,
        "win_rate": (
            winning_trades / total_trades
            if total_trades > 0
            else 0.0
        ),

        "ko_trades": ko_trades,
        "ko_rate": (
            ko_trades / total_trades
            if total_trades > 0
            else 0.0
        ),
        "core_ko_trades": len(core_ko),
        "sat_ko_trades": len(sat_ko),
        "ko_loss": float(ko_closed["RESULT"].sum())
        if not ko_closed.empty
        else 0.0,

        "total_profit": float(winners["RESULT"].sum()),
        "total_loss": float(losers["RESULT"].sum()),
        "net_result": float(closed_positions["RESULT"].sum()),

        "average_win": (
            float(winners["RESULT"].mean())
            if not winners.empty
            else 0.0
        ),

        "average_loss": (
            float(losers["RESULT"].mean())
            if not losers.empty
            else 0.0
        ),

        "core_trades": len(core_closed),
        "core_winning_trades": len(core_winners),
        "core_losing_trades": len(core_losers),
        "core_net_result": float(core_closed["RESULT"].sum()),

        "sat_trades": len(sat_closed),
        "sat_winning_trades": len(sat_winners),
        "sat_losing_trades": len(sat_losers),
        "sat_net_result": float(sat_closed["RESULT"].sum()),

        "total_fees": float(df["fees"].sum()),
        "total_taxes": float(df["taxes"].sum()),
        "total_cashflow_adjustment": float(
            df["cashflow_adjustment"].sum()
        ),

        "profit_factor": profit_factor,
        "largest_winner": largest_winner,
        "largest_loser": largest_loser,

        "core_win_rate": core_win_rate,
        "sat_win_rate": sat_win_rate,

        "core_average_win": (
            float(core_winners["RESULT"].mean())
            if not core_winners.empty
            else 0.0
        ),

        "core_average_loss": (
            float(core_losers["RESULT"].mean())
            if not core_losers.empty
            else 0.0
        ),

        "sat_average_win": (
            float(sat_winners["RESULT"].mean())
            if not sat_winners.empty
            else 0.0
        ),

        "sat_average_loss": (
            float(sat_losers["RESULT"].mean())
            if not sat_losers.empty
            else 0.0
        ),
    }

    return result, closed_positions
