import pandas as pd
import yfinance as yf


def get_latest_price_date(supabase, ticker):
    result = (
        supabase.table("price_history")
        .select("price_date")
        .eq("ticker", ticker)
        .order("price_date", desc=True)
        .limit(1)
        .execute()
    )

    if not result.data:
        return None

    return pd.to_datetime(result.data[0]["price_date"]).date()


def download_price_history(supabase, ticker, incremental=True):
    latest_date = get_latest_price_date(supabase, ticker)

    if incremental and latest_date:
        start_date = latest_date + pd.Timedelta(days=1)

        data = yf.download(
            ticker,
            start=start_date.strftime("%Y-%m-%d"),
            auto_adjust=True,
            progress=False,
            group_by="column"
        )
    else:
        data = yf.download(
            ticker,
            period="5y",
            auto_adjust=True,
            progress=False,
            group_by="column"
        )

    if data.empty:
        return None

    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    return data.reset_index()


def transform_price_data(ticker, data):
    if data is None:
        return []

    required_columns = ["Open", "High", "Low", "Close", "Volume"]

    if not all(col in data.columns for col in required_columns):
        return []

    date_column = data.columns[0]
    records = []

    for _, row in data.iterrows():
        records.append({
            "ticker": ticker,
            "price_date": str(pd.to_datetime(row[date_column]).date()),
            "open": float(row["Open"]),
            "high": float(row["High"]),
            "low": float(row["Low"]),
            "close": float(row["Close"]),
            "adj_close": float(row["Close"]),
            "volume": float(row["Volume"])
        })

    return records
