from datetime import datetime

import pandas as pd
from supabase import create_client

from data_loader import (
    get_latest_price_dates,
    download_price_history,
    transform_price_data
)

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
from orders import generate_core_orders, generate_sat_orders

from snapshot import (
    clear_today_snapshots,
    save_regime_snapshot,
    save_momentum_snapshot,
    save_order_snapshot
)


def run_daily_update(incremental=True):
    from streamlit import secrets

    print("=== DAILY UPDATE START ===")

    supabase = create_client(
        secrets["SUPABASE_URL"],
        secrets["SUPABASE_KEY"]
    )

    underlying_result = supabase.table("underlyings").select("*").execute()
    underlying_df = pd.DataFrame(underlying_result.data)

    trade_result = supabase.table("trades").select("*").execute()
    trade_df = pd.DataFrame(trade_result.data)

    tickers = underlying_df["ticker"].dropna().unique()

    total_rows = 0
    failed_tickers = []
    latest_dates = get_latest_price_dates(
        supabase
    )
    for ticker in tickers:
        ticker = str(ticker).strip()

        try:
            print(f"Lade Daten für {ticker}")

            data = download_price_history(
                supabase,
                ticker,
                incremental=incremental 
            )
            records = transform_price_data(ticker, data)

            if not records:
                failed_tickers.append(ticker)
                continue

            supabase.table("price_history").upsert(
                records,
                on_conflict="ticker,price_date"
            ).execute()

            total_rows += len(records)

        except Exception as e:
            failed_tickers.append(ticker)
            print(f"Fehler bei {ticker}: {e}")

    print(f"{total_rows} Kursdaten verarbeitet.")
    print(f"Fehlgeschlagene Ticker: {failed_tickers}")

    all_price_rows = []
    chunk_size = 1000
    start = 0

    while True:
        chunk = (
            supabase.table("price_history")
            .select("*")
            .range(start, start + chunk_size - 1)
            .execute()
        )

        if not chunk.data:
            break

        all_price_rows.extend(chunk.data)

        if len(chunk.data) < chunk_size:
            break

        start += chunk_size

    price_df = pd.DataFrame(all_price_rows)

    print(f"{len(price_df)} Preiszeilen geladen.")

    if price_df.empty:
        print("Keine Kursdaten vorhanden.")
        return

    price_df["price_date"] = pd.to_datetime(price_df["price_date"])
    price_df["adj_close"] = pd.to_numeric(price_df["adj_close"])
    price_df = price_df.sort_values(["ticker", "price_date"])

    pivot_close = price_df.pivot(
        index="price_date",
        columns="ticker",
        values="adj_close"
    )

    pivot_close = pivot_close.sort_index()
    pivot_close = pivot_close.ffill()

    price_df = pivot_close.reset_index().melt(
        id_vars="price_date",
        var_name="ticker",
        value_name="adj_close"
    )

    price_df = price_df.dropna()

    core_tickers = underlying_df.loc[
        underlying_df["strategy_role"].isin(["CORE", "BOTH"]),
        "ticker"
    ].tolist()

    sat_tickers = underlying_df.loc[
        underlying_df["strategy_role"].isin(["SATELLITE", "BOTH"]),
        "ticker"
    ].tolist()

    core_prices = price_df[price_df["ticker"].isin(core_tickers)]
    sat_prices = price_df[price_df["ticker"].isin(sat_tickers)]

    regime, top10_mom = get_regime(core_prices)

    if regime == "STRONG":
        core_weights = STRONG_CORE_WEIGHTS
        core_size = 3
        core_leverage = [2.0, 1.7, 1.3]
        core_sell_buffer = 2

    elif regime == "NORMAL":
        core_weights = NORMAL_CORE_WEIGHTS
        core_size = 5
        core_leverage = [1.8, 1.5, 1.3, 1.1, 1.0]
        core_sell_buffer = 7

    else:
        core_weights = WEAK_CORE_WEIGHTS
        core_size = 7
        core_leverage = [1.3, 1.2, 1.1, 1.0, 1.0, 1.0, 1.0]
        core_sell_buffer = 1

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

    core_target = core_rank.head(core_size).copy()
    core_target["target_position"] = range(1, len(core_target) + 1)
    core_target["target_leverage"] = core_leverage[:len(core_target)]
    core_target["sell_buffer"] = core_sell_buffer

    sat_target = sat_rank.head(1).copy()
    sat_target["target_position"] = 1
    sat_target["target_leverage"] = 10.0
    sat_target["sell_buffer"] = 3

    open_positions = pd.DataFrame()

    if not trade_df.empty:
        grouped = trade_df.groupby(
            ["system_type", "underlying_ticker", "turbo_wkn"],
            dropna=False
        ).apply(
            lambda x: pd.Series({
                "BUY_QTY": x.loc[x["action"] == "BUY", "quantity"].sum(),
                "SELL_QTY": x.loc[x["action"] == "SELL", "quantity"].sum()
            })
        ).reset_index()

        grouped["OPEN_QTY"] = grouped["BUY_QTY"] - grouped["SELL_QTY"]
        open_positions = grouped[grouped["OPEN_QTY"] > 0].copy()

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

    clear_today_snapshots(supabase)

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

    save_order_snapshot(supabase, core_orders)
    save_order_snapshot(supabase, sat_orders)

    supabase.table("system_status").upsert(
        {
            "status_key": "last_daily_update",
            "status_value": datetime.utcnow().isoformat()
        },
        on_conflict="status_key"
    ).execute()

    print("Snapshots gespeichert.")
    print("System Status aktualisiert.")
    print("=== DAILY UPDATE ENDE ===")


if __name__ == "__main__":
    run_daily_update()
