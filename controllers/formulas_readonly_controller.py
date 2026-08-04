import pandas as pd

from models.formulas_readonly_model import (
    listar_formulas_readonly_model,
    obtener_formula_readonly_model,
    listar_materias_primas_readonly_model,
    listar_ordenes_produccion_readonly_model,
    obtener_orden_produccion_readonly_model,
    listar_pt_sin_formula_model,
)


def listar_formulas_readonly_ctrl():
    return pd.DataFrame(listar_formulas_readonly_model())


def obtener_formula_readonly_ctrl(formula_id):
    return obtener_formula_readonly_model(formula_id)


def listar_materias_primas_readonly_ctrl():
    return pd.DataFrame(listar_materias_primas_readonly_model())


def listar_ordenes_produccion_readonly_ctrl():
    return pd.DataFrame(listar_ordenes_produccion_readonly_model())


def obtener_orden_produccion_readonly_ctrl(ord_id):
    return obtener_orden_produccion_readonly_model(ord_id)


def listar_pt_sin_formula_ctrl():
    return pd.DataFrame(listar_pt_sin_formula_model())