import pandas as pd
import yfinance as yf


def download_full_history(
    ticker
):

    data = yf.download(
        ticker,
        period="5y",
        auto_adjust=True,
        progress=False,
        group_by="column"
    )

    if data.empty:
        return None

    if isinstance(
        data.columns,
        pd.MultiIndex
    ):
        data.columns = data.columns.get_level_values(0)

    data = data.reset_index()

    return data


def transform_price_data(
    ticker,
    data
):

    if data is None:
        return []

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
        return []

    date_column = data.columns[0]

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

    return records
