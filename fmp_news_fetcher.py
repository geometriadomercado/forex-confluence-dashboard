
import requests
import pandas as pd
from datetime import datetime, timedelta
import streamlit as st

@st.cache_data(ttl=3600) # Cache por 1 hora
def fetch_forex_news(api_key, limit=10):
    url = f"https://financialmodelingprep.com/api/v3/forex_news?limit={limit}&apikey={api_key}"
    response = requests.get(url)
    if response.status_code == 200:
        news_data = response.json()
        df = pd.DataFrame(news_data)
        if not df.empty:
            df["publishedDate"] = pd.to_datetime(df["publishedDate"])
            df = df.sort_values(by="publishedDate", ascending=False)
        return df
    else:
        print(f"Erro ao buscar notícias Forex: {response.status_code} - {response.text}")
        return pd.DataFrame()

@st.cache_data(ttl=3600) # Cache por 1 hora
def fetch_economic_calendar(api_key, from_date=None, to_date=None):
    if from_date is None:
        from_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    if to_date is None:
        to_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")

    url = f"https://financialmodelingprep.com/api/v3/economic_calendar?from={from_date}&to={to_date}&apikey={api_key}"
    response = requests.get(url)
    if response.status_code == 200:
        calendar_data = response.json()
        df = pd.DataFrame(calendar_data)
        if not df.empty:
            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values(by="date", ascending=False)
        return df
    else:
        print(f"Erro ao buscar calendário econômico: {response.status_code} - {response.text}")
        return pd.DataFrame()


