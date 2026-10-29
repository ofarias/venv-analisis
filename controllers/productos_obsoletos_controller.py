import pandas as pd

from models.productos_obsoletos_model import construir_reporte_productos_obsoletos_model

ALMACENES_DISPONIBLES = {17: "ALMACEN MATERIAS PRIMAS", 18: "ALMACEN DE PRODUCTO TERMINADO", 22: "ALMACEN MUESTRAS"}


def obtener_reporte_productos_obsoletos_ctrl(anio: int, almacenes: list[int]) -> pd.DataFrame:
    if not almacenes:
        return pd.DataFrame()
    return construir_reporte_productos_obsoletos_model(anio, almacenes)
