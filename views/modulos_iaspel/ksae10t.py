import streamlit as st
import pandas as pd
from io import BytesIO
from models.iaspel_model import *

def main():

    st.title("Tabla ksae10t")

    page_size = 500
    page = st.number_input("Página", min_value=1, value=1, step=1)
    offset = (page - 1) * page_size

    data = obtener_ksae10t(limit=page_size, offset=offset)

    if not data:
        st.warning("No se encontraron registros en ksae10t")
        return

    df = pd.DataFrame(data)
    st.dataframe(df, use_container_width=True)

    # opción de exportar a Excel
    # exportar a Excel en memoria
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="ksae10t")

    st.download_button(
        label="Descargar Excel",
        data=buffer.getvalue(),
        file_name="ksae10t.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    st.title("tabla ksae20t ")
    data20t = obtener_ksae20t(limit=page_size, offset=offset)

    if not data20t:
            st.warning("No se encontraron registros en ksae10t")
            return

    df = pd.DataFrame(data20t)
    st.dataframe(df, use_container_width=True)


    st.title("Proveedores SAE")
    data = obtener_prov01()
    df= pd.DataFrame(data)
    st.dataframe(df, use_container_width=True) 


    st.title("Polizas COI ")
    data = polizas_coi()
    df = pd.DataFrame(data)
    st.dataframe(df, use_container_width=True
                 
                 )
def tablas_iaspel():
    main()