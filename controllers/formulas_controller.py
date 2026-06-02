import pandas as pd

from models.formulas_model import (
    listar_mp_model,
    crear_mp_model,
    actualizar_mp_model,
    cambiar_estado_mp_model,
    listar_formulas_model,
    get_formula_model,
    crear_formula_model,
    nueva_version_formula_model,
    cambiar_estado_formula_model,
    listar_mp_sae_model,
    sincronizar_mp_sae_a_mysql_model,
)


def listar_mp_ctrl(solo_activas=True):
    return pd.DataFrame(listar_mp_model(solo_activas=solo_activas))


def crear_mp_ctrl(data):
    return crear_mp_model(data)


def actualizar_mp_ctrl(mp_id, data):
    return actualizar_mp_model(mp_id, data)


def cambiar_estado_mp_ctrl(mp_id, activo, usuario_id=None):
    return cambiar_estado_mp_model(mp_id, activo, usuario_id)


def listar_formulas_ctrl(solo_activas=True):
    return pd.DataFrame(listar_formulas_model(solo_activas=solo_activas))


def get_formula_ctrl(formula_id):
    return get_formula_model(formula_id)


def crear_formula_ctrl(data, detalle):
    return crear_formula_model(data, detalle)


def nueva_version_formula_ctrl(formula_id, data, detalle):
    return nueva_version_formula_model(formula_id, data, detalle)


def cambiar_estado_formula_ctrl(formula_id, activo, usuario_id):
    return cambiar_estado_formula_model(formula_id, activo, usuario_id)


def generar_clave_formula_ctrl(segmento, consecutivo, es_alterna=False, clave_base=None, num_alterna=None):
    prefijos = {
        "Pan": "PN",
        "Tortilla": "PN",
        "Alimentos": "AL",
        "Textil": "TE",
        "Cuero": "CU",
        "Cerveza": "CE",
        "Jugos": "JU",
        "Bacterias": "BA",
    }

    if es_alterna and clave_base:
        return f"{clave_base}-A{num_alterna or 1}"

    prefijo = prefijos.get(segmento, "AL")
    return f"PT-{prefijo}-{str(consecutivo).zfill(3)}"

def listar_mp_sae_ctrl():
    df = pd.DataFrame(listar_mp_sae_model())

    if df.empty:
        return df

    df.columns = [str(c).lower() for c in df.columns]

    return df

def sincronizar_mp_sae_a_mysql_ctrl(usuario_id=None):
    return sincronizar_mp_sae_a_mysql_model(usuario_id)
