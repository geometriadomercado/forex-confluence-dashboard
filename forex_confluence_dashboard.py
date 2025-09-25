# =============================================================================
# Forex Confluence Dashboard (FREE)
# Desenvolvido por seu parceiro de trading 🤝
#
# Este dashboard interativo, construído com Streamlit, oferece uma análise de
# confluências no mercado Forex, combinando dados do Índice DXY com pares de
# moedas, indicadores técnicos e notícias econômicas.
#
# Requisitos:
#   - streamlit
#   - pandas
#   - numpy
#   - plotly
#   - requests
#   - dukascopy-python
#
# Como rodar:
#   1. Certifique-se de ter Python 3.9+ instalado.
#   2. Instale as dependências: `pip install -r requirements.txt`
#   3. Execute o dashboard: `streamlit run forex_confluence_dashboard.py`
#
# =============================================================================

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

import plotly.graph_objs as go
import requests

from fmp_news_fetcher import fetch_forex_news, fetch_economic_calendar
from dukascopy_data_fetcher import fetch_dukascopy_data
import dukascopy_python

# Configuração da página do Streamlit
st.set_page_config(page_title="Forex Confluence Dashboard (FREE)", layout="wide")

def ema(series, n):
    return series.ewm(span=n, adjust=False).mean()

# ✅ ATR corrigido
def atr(df, n=14):
    high = df['High']
    low = df['Low']
    close = df['Close']
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(n).mean()

def cvd_proxy(df):
    if 'volume' in df.columns:
        # Usar volume se disponível para um CVD mais preciso
        body = df["Close"] - df["Open"]
        return (body * df["volume"]).cumsum()
    else:
        # Fallback para o proxy original se o volume não estiver disponível
        body = df["Close"] - df["Open"]
        return body.cumsum()

# ✅ in_zone corrigido (retorna só True/False)
def in_zone(close, ma_series, atr_val, k=1.5):
    """True se o último preço está dentro da zona definida."""
    if ma_series is None or ma_series.dropna().empty:
        return False
    ma_last = float(ma_series.iloc[-1])
    price_last = float(close.iloc[-1])
    if np.isnan(atr_val) or atr_val == 0:
        atr_val = float(close.iloc[-1]) * 0.001  # fallback pequeno
    return abs(price_last - ma_last) <= k * atr_val

def crossover_recent(series_a, series_b, lookback=5):
    a = series_a.iloc[-lookback:]
    b = series_b.iloc[-lookback:]
    crosses = ( (a > b) & (a.shift(1) <= b.shift(1)) ) | ( (a < b) & (a.shift(1) >= b.shift(1)) )
    return crosses.any()

# ✅ divergence_proxy corrigido
def divergence_proxy(df, window=30):
    """Detecta divergência simples entre preço e CVD proxy"""
    c = df['Close']
    d = df['CVD']
    if len(df) < window + 2:
        return "none"

    price_change = float(c.iloc[-1]) - float(c.iloc[-window])
    cvd_change = float(d.iloc[-1]) - float(d.iloc[-window])

    if price_change < 0 and cvd_change > 0:
        return "bullish"
    if price_change > 0 and cvd_change < 0:
        return "bearish"
    return "none"

def plot_candles_with_mas(df, title, ma_periods, show_cvd=True):
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
        name='Price'
    ))
    for p in ma_periods:
        colname = f"MA_{p}"
        if colname in df.columns and df[colname].notna().any():
            fig.add_trace(go.Scatter(x=df.index, y=df[colname], mode='lines', name=colname))
    if show_cvd and 'CVD' in df.columns:
        fig2 = go.Scatter(x=df.index, y=df['CVD'], mode='lines', name='CVD (proxy)', yaxis='y2')
        fig.add_trace(fig2)
        fig.update_layout(
            yaxis2=dict(overlaying='y', side='right', showgrid=False, title="CVD proxy")
        )
    fig.update_layout(title=title, xaxis_rangeslider_visible=False, height=520, legend=dict(orientation="h"))
    return fig

# -----------------------------
# Sidebar
# -----------------------------
st.sidebar.title("Configurações")
interval = st.sidebar.selectbox("Intervalo", ["5m", "15m", "1h", "1d"], index=1)
period_map = {"5m":"7d","15m":"60d","1h":"2y","1d":"5y"}
period = period_map[interval]
window_div = st.sidebar.slider("Janela Divergência (barras)", 10, 120, 40, 5)
atr_n = st.sidebar.slider("ATR (n)", 5, 50, 14, 1)
zone_k = st.sidebar.slider("Zona da MA (k x ATR)", 0.5, 5.0, 1.5, 0.1)
atr_multiplier_sl = st.sidebar.slider("Multiplicador ATR para SL/TP", 0.5, 5.0, 2.0, 0.1)
ma_periods = [20,50,100,200,600,1200,2000]
show_cvd = st.sidebar.checkbox("Mostrar CVD proxy no gráfico", True)
fmp_api_key = st.secrets["FMP_API_KEY"]
show_news = st.sidebar.checkbox("Mostrar Notícias Forex e Calendário Econômico", False)



# -----------------------------
# Data: DXY
# -----------------------------
from datetime import datetime, timedelta

# Mapeamento de intervalos para Dukascopy
interval_map_dukascopy = {
    "5m": dukascopy_python.INTERVAL_MINUTE_5,
    "15m": dukascopy_python.INTERVAL_MINUTE_15,
    "1h": dukascopy_python.INTERVAL_HOUR_1,
    "1d": dukascopy_python.INTERVAL_DAY_1,
}

# Mapeamento de períodos para Dukascopy
period_map_dukascopy = {
    "7d": timedelta(days=7),
    "60d": timedelta(days=60),
    "2y": timedelta(days=730),
    "5y": timedelta(days=1825),
}

start_date = datetime.now() - period_map_dukascopy[period]
# interval_value, time_unit = interval_map_dukascopy[interval] # Não mais necessário

with st.spinner("Carregando dados do DXY..."):
    dxy = fetch_dukascopy_data(
        "USDX",
        interval_map_dukascopy[interval],
        dukascopy_python.OFFER_SIDE_BID,
        start_date
    )


dxy_used = "USD.USD_DXY"
if dxy.empty:
    st.error("Não foi possível baixar dados do DXY.")
    st.stop()

for p in [50, 200]:
    dxy[f"EMA_{p}"] = ema(dxy["Close"], p)
dxy['ATR'] = atr(dxy, atr_n)
dxy['CVD'] = cvd_proxy(dxy)

macro_up = dxy["EMA_50"].iloc[-1] > dxy["EMA_200"].iloc[-1]
macro_str = "USD FORTE (preferir vender EUR/GBP/AUD; comprar USDCHF)" if macro_up else "USD FRACO (preferir comprar EUR/GBP/AUD; vender USDCHF)"

# -----------------------------
# Data: Pairs
# -----------------------------
pairs = {
    "EURUSD": dukascopy_python.INSTRUMENT_FX_MAJORS_EUR_USD,
    "GBPUSD": dukascopy_python.INSTRUMENT_FX_MAJORS_GBP_USD,
    "AUDUSD": dukascopy_python.INSTRUMENT_FX_MAJORS_AUD_USD,
    "USDCHF": dukascopy_python.INSTRUMENT_FX_MAJORS_USD_CHF
}

results = []
tabs = st.tabs(["DXY"] + list(pairs.keys()))

with tabs[0]:
    st.subheader(f"DXY – usado: {dxy_used}")
    st.plotly_chart(plot_candles_with_mas(dxy.assign(MA_50=dxy["EMA_50"], MA_200=dxy["EMA_200"]),
                                          "DXY com EMA50/EMA200 + CVD proxy",
                                          [50,200], show_cvd=True), use_container_width=True)
    st.info(f"Filtro Macro: {macro_str}")

for i, (name, instrument_code) in enumerate(pairs.items(), start=1):
    with st.spinner(f"Carregando dados para {name}..."):
        df = fetch_dukascopy_data(
            instrument_code,
            interval_map_dukascopy[interval],
            dukascopy_python.OFFER_SIDE_BID,
            start_date
        )

    used = name
    if df.empty:
        with tabs[i]:
            st.error(f"Sem dados para {name}.")
        continue

    for p in ma_periods:
        if len(df) >= p + 5:
            df[f"MA_{p}"] = df["Close"].rolling(p).mean()
        else:
            df[f"MA_{p}"] = np.nan
    df['ATR'] = atr(df, atr_n)
    df['CVD'] = cvd_proxy(df)

    has_zone = any([
        in_zone(df['Close'], df.get(f"MA_{p}"), df['ATR'].iloc[-1], k=zone_k)
        for p in [600,1200,2000]
    ])

    crossed = False
    if df.get("MA_600") is not None and df.get("MA_1200") is not None:
        crossed = crossover_recent(df["MA_600"].fillna(method='bfill'), df["MA_1200"].fillna(method='bfill'), lookback=10)

    div = divergence_proxy(df, window=window_div)

    suggestion = "SEM TRADE"
    if has_zone or crossed:
        if div == "bullish":
            if name != "USDCHF":
                suggestion = "COMPRA" if not macro_up else "SEM TRADE"
            else:
                suggestion = "VENDA" if not macro_up else "SEM TRADE"
        elif div == "bearish":
            if name != "USDCHF":
                suggestion = "VENDA" if macro_up else "SEM TRADE"
            else:
                suggestion = "COMPRA" if macro_up else "SEM TRADE"
        else:
            suggestion = "AGUARDAR CONFIRMAÇÃO"
    else:
        suggestion = "AGUARDAR ZONA"

    stop_loss, take_profit = calculate_sl_tp(df, df["ATR"].iloc[-1], atr_multiplier_sl)

    results.append({
        "Par": name,
        "Ticker": used,
        "Macro USD": "Forte" if macro_up else "Fraco",
        "Na Zona (600/1200/2000)": "Sim" if has_zone else "Não",
        "Cruzamento 600x1200 (10b)": "Sim" if crossed else "Não",
        "Divergência (proxy)": div,
        "Sinal": suggestion,
        "Stop Loss": f"{stop_loss:.5f}" if stop_loss else "N/A",
        "Take Profit": f"{take_profit:.5f}" if take_profit else "N/A"
    })

    with tabs[i]:
        st.subheader(f"{name} – usado: {used}")
        st.plotly_chart(
            plot_candles_with_mas(df, f"{name} – Candles + MAs + CVD proxy", ma_periods, show_cvd=show_cvd),
            use_container_width=True
        )
        st.caption("CVD proxy = soma acumulada do corpo das velas (Close-Open). É uma aproximação gratuita.")
        st.write(f"ATR atual: {df['ATR'].iloc[-1]:.5f}")

st.divider()
st.subheader("Resumo de Confluências")
if results:
    st.dataframe(pd.DataFrame(results))
else:
    st.write("Sem resultados.")


def calculate_sl_tp(df, atr_val, atr_multiplier):
    if df.empty or atr_val is None or np.isnan(atr_val) or atr_val == 0:
        return None, None

    last_close = float(df["Close"].iloc[-1])
    # Exemplo simples: SL/TP baseados no último preço e ATR
    # Para uma estratégia real, isso seria mais complexo e dependeria do sinal de entrada
    stop_loss = last_close - (atr_multiplier * atr_val)
    take_profit = last_close + (atr_multiplier * atr_val)
    return stop_loss, take_profit



# -----------------------------
# Notícias e Calendário Econômico
# -----------------------------
if show_news:
    st.divider()
    st.subheader("Notícias Forex Recentes")
    forex_news = fetch_forex_news(fmp_api_key, limit=10)
    if not forex_news.empty:
        for index, row in forex_news.iterrows():
            st.markdown(f"**[{row["title"]}]({row["url"]})**")
            st.write(f"<small>Publicado em: {row["publishedDate"].strftime("%Y-%m-%d %H:%M")} - {row["source"]}</small>", unsafe_allow_html=True)
            st.markdown("---")
    else:
        st.write("Não foi possível carregar as notícias Forex.")

    st.subheader("Calendário Econômico (Próximos 7 dias)")
    economic_calendar = fetch_economic_calendar(fmp_api_key)
    if not economic_calendar.empty:
        st.dataframe(economic_calendar[["date", "country", "event", "impact", "actual", "previous", "change", "changePercentage"]].style.format({"date": lambda t: t.strftime("%Y-%m-%d %H:%M")}))
    else:
        st.write("Não foi possível carregar o calendário econômico.")


