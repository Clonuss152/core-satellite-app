import pandas as pd


def get_underlying_info(ticker, df):

    info = {
        "company_name": None,
        "isin": None,
        "wkn": None,
        "exchange": None,
        "currency": None,
    }

    if df.empty:
        return info

    row = df[df["ticker"] == ticker]

    if row.empty:
        return info

    first = row.iloc[0]

    for key in info.keys():
        if key in first:
            info[key] = first.get(key)

    return info


def add_business_days(start_date, days):

    dates = pd.bdate_range(
        start=start_date,
        periods=days + 1
    )

    return dates[-1].date()
