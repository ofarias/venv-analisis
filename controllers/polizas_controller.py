# controllers/polizas_controller.py

from models.polizas_model import (
    obtener_resumen_polizas,
    obtener_detalle_poliza,
    obtener_xml_resumen_mes_anio,
    obtener_xml_con_poliza,
)


def get_resumen_polizas_ctrl(ejercicio: int, periodo: int, tipo_poliza: str | None = None):
    return obtener_resumen_polizas(ejercicio, periodo, tipo_poliza)


def get_detalle_poliza_ctrl(ejercicio: int, periodo: int, tipo_poliza: str, num_poliz: str):
    return obtener_detalle_poliza(ejercicio, periodo, tipo_poliza, num_poliz)


def get_xml_resumen_mes_anio_ctrl(cliente: str = "PCP220503B20"):
    return obtener_xml_resumen_mes_anio(cliente)


def get_xml_con_poliza_ctrl(cliente: str = "PCP220503B20"):
    return obtener_xml_con_poliza(cliente)