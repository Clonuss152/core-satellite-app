from datetime import date

import pandas as pd
import yfinance as yf

from supabase import create_client

from config import (
    CORE_LOOKBACKS,
    SAT_LOOKBACKS,
    STRONG_CORE_WEIGHTS,
    NORMAL_CORE_WEIGHTS,
    WEAK_CORE_WEIGHTS,
    SAT_WEIGHTS
)

from momentum import calculate_momentum
from regime import get_regime

from orders import (
    generate_core_orders,
    generate_sat_orders
)

from snapshot import (
    save_regime_snapshot,
    save_momentum_snapshot,
    save_order_snapshot
)


def run_daily_update():

    print("=== DAILY UPDATE START ===")

    # ===================================================
    # SUPABASE
    # ===================================================

    from streamlit import secrets

    SUPABASE_URL = secrets["SUPABASE_URL"]
    SUPABASE_KEY = secrets["SUPABASE_KEY"]

    supabase = create_client(
        SUPABASE_URL,
        SUPABASE_KEY
    )

    print("Supabase verbunden.")

    # ===================================================
    # UNDERLYINGS LADEN
    # ===================================================

    underlying_result = supabase.table(
        "underlyings"
    ).select("*").execute()

    underlying_df = pd.DataFrame(
        underlying_result.data
    )

    print(
        f"{len(underlying_df)} Underlyings geladen."
    )

    # ===================================================
    # TRADES LADEN
    # ===================================================

    trade_result = supabase.table(
        "trades"
    ).select("*").execute()

    trade_df = pd.DataFrame(
        trade_result.data
    )

    print(
        f"{len(trade_df)} Trades geladen."
    )

    # ===================================================
    # KURSDATEN UPDATE
    # ===================================================

    tickers = underlying_df[
        "ticker"
    ].dropna().unique()

    total_rows = 0
    failed_tickers = []

    for ticker in tickers:

        try:

            print(f"Lade Daten für {ticker}")

            data = yf.download(
                ticker,
                period="5y",
                auto_adjust=True,
                progress=False,
                group_by="column"
            )

            if data.empty:
                failed_tickers.append(ticker)
                continue

            if isinstance(
                data.columns,
                pd.MultiIndex
            ):
                data.columns = data.columns.get_level_values(0)

            data = data.reset_index()

            date_column = data.columns[0]

            required_columns = [
                "Open",
                "High",
                "Low",
                "Close",
                "Volume"
            ]

            if not all(
                col in data.columns
                for col in required_columns
            ):
                failed_tickers.append(ticker)
                continue

            records = []

            for _, row in data.iterrows():

                records.append({

                    "ticker": ticker,

                    "price_date": str(
                        pd.to_datetime(
                            row[date_column]
                        ).date()
                    ),

                    "open": float(row["Open"]),
                    "high": float(row["High"]),
                    "low": float(row["Low"]),
                    "close": float(row["Close"]),

                    "adj_close": float(
                        row["Close"]
                    ),

                    "volume": float(
                        row["Volume"]
                    )

                })

            if records:

                supabase.table(
                    "price_history"
                ).upsert(
                    records,
                    on_conflict="ticker,price_date"
                ).execute()

                total_rows += len(records)

        except Exception as e:

            failed_tickers.append(ticker)

            print(
                f"Fehler bei {ticker}: {e}"
            )

    print(
        f"{total_rows} Kursdaten verarbeitet."
    )

    print(
        f"Fehlgeschlagene Ticker: {failed_tickers}"
    )
    # ===================================================
    # PRICE HISTORY LADEN
    # ===================================================

    all_price_rows = []

    chunk_size = 1000
    start = 0

    while True:

        chunk = (
            supabase.table("price_history")
            .select("*")
            .range(
                start,
                start + chunk_size - 1
            )
            .execute()
        )

        if not chunk.data:
            break

        all_price_rows.extend(
            chunk.data
        )

        if len(chunk.data) < chunk_size:
            break

        start += chunk_size

    price_df = pd.DataFrame(
        all_price_rows
    )

    print(
        f"{len(price_df)} Preiszeilen geladen."
    )

    # ===================================================
    # GEMEINSAMER KALENDER
    # ===================================================

    price_df["price_date"] = pd.to_datetime(
        price_df["price_date"]
    )

    price_df["adj_close"] = pd.to_numeric(
        price_df["adj_close"]
    )

    price_df = price_df.sort_values(
        ["ticker", "price_date"]
    )

    pivot_close = price_df.pivot(
        index="price_date",
        columns="ticker",
        values="adj_close"
    )

    pivot_close = pivot_close.sort_index()

    # WICHTIG:
    # gemeinsamer Kalender + ffill
    pivot_close = pivot_close.ffill()

    price_df = pivot_close.reset_index().melt(
        id_vars="price_date",
        var_name="ticker",
        value_name="adj_close"
    )

    price_df = price_df.dropna()

    print(
        "Gemeinsamer Kalender erstellt."
    )

    # ===================================================
    # CORE / SAT FILTER
    # ===================================================

    core_tickers = underlying_df.loc[
        underlying_df["strategy_role"].isin(
            ["CORE", "BOTH"]
        ),
        "ticker"
    ].tolist()

    sat_tickers = underlying_df.loc[
        underlying_df["strategy_role"].isin(
            ["SATELLITE", "BOTH"]
        ),
        "ticker"
    ].tolist()

    core_prices = price_df[
        price_df["ticker"].isin(
            core_tickers
        )
    ]

    sat_prices = price_df[
        price_df["ticker"].isin(
            sat_tickers
        )
    ]

    print(
        f"{len(core_prices)} CORE Preiszeilen."
    )

    print(
        f"{len(sat_prices)} SAT Preiszeilen."
    )

    # ===================================================
    # REGIME
    # ===================================================

    regime, top10_mom = get_regime(
        core_prices
    )

    print(
        f"Regime: {regime}"
    )

    print(
        f"Top10 Momentum: {top10_mom}"
    )

    # ===================================================
    # REGIME PARAMETER
    # ===================================================

    if regime == "STRONG":

        core_weights = STRONG_CORE_WEIGHTS

        core_size = 3

        core_leverage = [
            2.0,
            1.7,
            1.3
        ]

        core_sell_buffer = 2

    elif regime == "NORMAL":

        core_weights = NORMAL_CORE_WEIGHTS

        core_size = 5

        core_leverage = [
            1.8,
            1.5,
            1.3,
            1.1,
            1.0
        ]

        core_sell_buffer = 7

    else:

        core_weights = WEAK_CORE_WEIGHTS

        core_size = 7

        core_leverage = [
            1.3,
            1.2,
            1.1,
            1.0,
            1.0,
            1.0,
            1.0
        ]

        core_sell_buffer = 1

    # ===================================================
    # MOMENTUM
    # ===================================================

    core_rank = calculate_momentum(
        core_prices,
        CORE_LOOKBACKS,
        core_weights
    )

    sat_rank = calculate_momentum(
        sat_prices,
        SAT_LOOKBACKS,
        SAT_WEIGHTS
    )

    print(
        f"{len(core_rank)} CORE Rankings."
    )

    print(
        f"{len(sat_rank)} SAT Rankings."
    )

    # ===================================================
    # ZIELPORTFOLIO
    # ===================================================

    core_target = core_rank.head(
        core_size
    ).copy()

    core_target[
        "target_position"
    ] = range(
        1,
        len(core_target) + 1
    )

    core_target[
        "target_leverage"
    ] = core_leverage[
        :len(core_target)
    ]

    core_target[
        "sell_buffer"
    ] = core_sell_buffer

    sat_target = sat_rank.head(1).copy()

    sat_target[
        "target_position"
    ] = 1

    sat_target[
        "target_leverage"
    ] = 10.0

    sat_target[
        "sell_buffer"
    ] = 3

    # ===================================================
    # OFFENE POSITIONEN
    # ===================================================

    open_positions = pd.DataFrame()

    if not trade_df.empty:

        grouped = trade_df.groupby(

            [
                "system_type",
                "underlying_ticker",
                "turbo_wkn"
            ],

            dropna=False

        ).apply(

            lambda x: pd.Series({

                "BUY_QTY": x.loc[
                    x["action"] == "BUY",
                    "quantity"
                ].sum(),

                "SELL_QTY": x.loc[
                    x["action"] == "SELL",
                    "quantity"
                ].sum()

            })

        ).reset_index()

        grouped["OPEN_QTY"] = (
            grouped["BUY_QTY"]
            - grouped["SELL_QTY"]
        )

        open_positions = grouped[
            grouped["OPEN_QTY"] > 0
        ].copy()

    print(
        f"{len(open_positions)} offene Positionen."
    )

    # ===================================================
    # ORDER ENGINE
    # ===================================================

    core_orders = generate_core_orders(

        core_target=core_target,
        core_rank=core_rank,

        open_positions=open_positions,

        df=underlying_df,

        core_size=core_size,
        core_sell_buffer=core_sell_buffer

    )

    sat_orders = generate_sat_orders(

        sat_target=sat_target,
        sat_rank=sat_rank,

        open_positions=open_positions,

        df=underlying_df

    )

    print(
        f"{len(core_orders)} CORE Orders."
    )

    print(
        f"{len(sat_orders)} SAT Orders."
    )

    # ===================================================
    # SNAPSHOTS SPEICHERN
    # ===================================================

    save_regime_snapshot(
        supabase,
        regime,
        top10_mom
    )

    save_momentum_snapshot(
        supabase,
        "CORE",
        core_target,
        core_leverage,
        core_sell_buffer
    )

    save_momentum_snapshot(
        supabase,
        "SATELLITE",
        sat_target,
        [10.0],
        3
    )

    save_order_snapshot(
        supabase,
        core_orders
    )

    save_order_snapshot(
        supabase,
        sat_orders
    )

    print(
        "Snapshots gespeichert."
    )

    print(
        "=== DAILY UPDATE ENDE ==="
    )


if __name__ == "__main__":

    run_daily_update()
