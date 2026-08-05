from __future__ import annotations

import requests
import streamlit as st

# serie SF43718 = tipo de cambio FIX (pesos por dólar), publicación oficial de
# Banxico — "oportuno" trae el dato más reciente disponible
_SERIE_TIPO_CAMBIO_FIX = "SF43718"
_URL = (
    f"https://www.banxico.org.mx/SieAPIRest/service/v1/series/"
    f"{_SERIE_TIPO_CAMBIO_FIX}/datos/oportuno"
)


@st.cache_data(ttl=86400, show_spinner="consultando tipo de cambio oficial (Banxico)…")
def obtener_tipo_cambio_fix_banxico() -> float:
    """Tipo de cambio FIX oficial (MXN por USD) más reciente publicado por
    Banxico. Se cachea 24 h para no exceder el límite de la API."""
    token = st.secrets["BANXICO"]["token"]
    resp = requests.get(
        _URL,
        headers={"Bmx-Token": token},
        params={"mediaType": "json"},
        timeout=15,
    )
    resp.raise_for_status()
    datos = resp.json()["bmx"]["series"][0]["datos"][0]
    return float(datos["dato"].replace(",", ""))
