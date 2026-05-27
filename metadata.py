import time
import yfinance as yf


def enrich_underlying_metadata(supabase, ticker):

    try:
        time.sleep(1.0)

        stock = yf.Ticker(ticker)

        info = stock.get_info()

        company_name = (
            info.get("longName")
            or info.get("shortName")
            or ticker
        )

        exchange = info.get("exchange")
        currency = info.get("currency")
        sector = info.get("sector")
        country = info.get("country")

        supabase.table("underlyings").upsert(
            {
                "ticker": ticker,
                "company_name": company_name,
                "exchange": exchange,
                "currency": currency,
                "sector": sector,
                "region": country
            },
            on_conflict="ticker"
        ).execute()

        return True, None

    except Exception as e:
        return False, str(e)
