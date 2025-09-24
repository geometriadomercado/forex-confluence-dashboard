
from datetime import datetime, timedelta
import dukascopy_python
import pandas as pd
import streamlit as st

@st.cache_data(ttl=3600) # Cache por 1 hora
def fetch_dukascopy_data(instrument_code, interval, offer_side, start_date, end_date=None):
    """
    Busca dados históricos do Dukascopy.

    Args:
        instrument_code: Código do instrumento (ex: INSTRUMENT_FX_MAJORS_EUR_USD).
        interval_value: Valor do intervalo (ex: 1 para 1 minuto, 5 para 5 minutos).
        time_unit: Unidade de tempo (ex: dukascopy_python.TIME_UNIT_MIN).
        offer_side: Lado da oferta (ex: dukascopy_python.OFFER_SIDE_BID).
        start_date: Data de início (datetime.datetime).
        end_date: Data de fim (datetime.datetime, opcional. Se None, busca até agora).

    Returns:
        pandas.DataFrame: DataFrame com os dados OHLCV e volume.
    """
    if end_date is None:
        end_date = datetime.now()

    df = dukascopy_python.fetch(
        instrument_code,
        interval,
        offer_side,
        start_date,
        end_date,
    )
    return df



