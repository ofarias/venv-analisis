# usuarios_unidades_view.py
import streamlit as st
from controllers.usuario_controller import get_usuarios
from controllers.unidades_controller import (
    get_unidades,
    asignar_unidades_a_usuarios,
    obtener_asignaciones,
    cambiar_estatus_asignacion,
    eliminar_asignaciones, 
)

def pantalla_usuarios_unidades():
    st.subheader("👥 Asignar unidades a usuarios")

    usuarios_df = get_usuarios()
    unidades_df = get_unidades()

    if usuarios_df.empty or unidades_df.empty:
        st.warning("Debe existir al menos un usuario y una unidad registrada.")
        return

    col1, col2 = st.columns(2)
    with col1:
        usuarios_sel = st.multiselect("Usuarios", usuarios_df["username"].tolist())
    with col2:
        unidades_sel = st.multiselect("Unidades de negocio", unidades_df["nombre"].tolist())

    st.caption("""
        🛈 **Instrucciones de uso:**
        - Estos usuarios podran asignar gastos a las unidades de negocio seleccionadas.
        """)
    if st.button("💾 Asignar", use_container_width=True):
        if not usuarios_sel or not unidades_sel:
            st.warning("Selecciona al menos un usuario y una unidad.")
        else:
            user = st.session_state["usuario"]
            creador = user.get("username")
            asignar_unidades_a_usuarios(usuarios_sel, unidades_sel, creador)
            st.success("Asignaciones guardadas correctamente.")
            st.rerun()

    st.divider()
    st.subheader("📋 Asignaciones actuales")

    df = obtener_asignaciones()
    if df.empty:
        st.info("No hay asignaciones registradas.")
        return

    # transformar campos
    if "status" not in df.columns:
        df["status"] = 1
    df["status_texto"] = df["status"].map({1: "Activo", 0: "Baja"})

    # proteger columnas faltantes
    for col in ["fecha_baja", "creado_por", "baja_por"]:
        if col not in df.columns:
            df[col] = ""

    # normalizar tipo
    df["fecha_baja"] = df["fecha_baja"].fillna("").astype(str)

    # --- FILTROS múltiples ---
    colf1, colf2 = st.columns([1.5, 1.5])
    with colf1:
        usuarios_fil = st.multiselect(
            "Filtrar por usuario",
            options=sorted(df["usuario"].unique().tolist()),
            default=[]
        )
    with colf2:
        unidades_fil = st.multiselect(
            "Filtrar por unidad",
            options=sorted(df["unidad"].unique().tolist()),
            default=[]
        )

    df_filtrado = df.copy()
    if usuarios_fil:
        df_filtrado = df_filtrado[df_filtrado["usuario"].isin(usuarios_fil)]
    if unidades_fil:
        df_filtrado = df_filtrado[df_filtrado["unidad"].isin(unidades_fil)]

    # columnas ordenadas y renombradas para vista
    cols_vista = [
        "id", "usuario", "unidad", "status_texto",
        "fecha_alta", "creado_por", "fecha_baja", "baja_por"
    ]
    df_filtrado = df_filtrado[cols_vista]

    # aplicar color a bajas
    def estilo_bajas(row):
        if row["status_texto"] == "Baja":
            return ["background-color:#fce4e4; color:#8b0000;"] * len(row)
        return ["" for _ in row]

    st.dataframe(
        df_filtrado.style.apply(estilo_bajas, axis=1),
        hide_index=True,
        use_container_width=True,
        height=min(800, 120 + 34 * len(df_filtrado))
    )

    st.divider()
    colb1, colb2 = st.columns([1, 1])

    with colb1:
        if st.button("Actualizar estatus seleccionados", use_container_width=True):
            for _, row in df_filtrado.iterrows():
                if row["status_texto"] == "Baja":
                    cambiar_estatus_asignacion(row["id"], 1)
                else:
                    cambiar_estatus_asignacion(row["id"], 0)
            st.success("Estatus actualizados correctamente.")
            st.rerun()
        # instrucciones para el usuario
        st.caption("""
        🛈 **Instrucciones de uso:**
        - Este botón aplica sobre *todas las filas visibles* en la tabla actual.
        - Si la asignación está **Activa**, se marcará como **Baja**.
        - Si está **Baja**, se reactivará automáticamente.
        - Usa los filtros de usuario o unidad para limitar las filas visibles antes de actualizar.
        """)
    with colb2:
        opciones = [
            (row["id"], f"{row['usuario']} → {row['unidad']}")
            for _, row in df_filtrado.iterrows()
        ]

        seleccionadas = st.multiselect(
            "Seleccionar asignaciones a dar de baja",
            options=[op[0] for op in opciones],
            format_func=lambda i: next(label for val, label in opciones if val == i),
            key="asig_a_baja"
        )

        if seleccionadas and st.button("🗑️ Dar de baja seleccionadas", use_container_width=True):
            user = st.session_state["usuario"]
            usuario_baja = user.get("username")
            eliminar_asignaciones(seleccionadas, usuario_baja)
            st.success(f"Se dieron de baja {len(seleccionadas)} asignaciones.")
            st.rerun()