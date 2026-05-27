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
