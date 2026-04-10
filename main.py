#main.py

import sys, os
import streamlit as st
from PIL import Image
from logs.logger import registrar_log
import base64
import mimetypes

st.set_page_config(layout="wide")
    
logo_path = "biotecsa.png"
if os.path.exists(logo_path):
    imagen = Image.open(logo_path)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.image(imagen, width=200)

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def _get_modulo_forzado_desde_deeplink() -> str | None:
    qp = st.query_params

    sg_id = (qp.get("sg_id") or "").strip()
    token = (qp.get("t") or "").strip()

    if sg_id and token:
        return "solicitudesConta"

    deeplink_session = st.session_state.get("deeplink_params") or {}
    if deeplink_session.get("sg_id") and deeplink_session.get("t"):
        return "solicitudesConta"

    modulo_forzado = st.session_state.get("modulo_forzado")
    if modulo_forzado:
        return str(modulo_forzado)

    return None


from views.login_view import mostrar_login

if "usuario" not in st.session_state:
    mostrar_login()
else:
    usuario = st.session_state["usuario"]
    nombre = usuario.get("nombre", "Usuario")
    roles = usuario.get("roles", [])
    estatus = usuario.get("estatus", "")

    ### Aqui el manejo de las politicas

    ## avisos = st.session_state.get("avisos_politicas", [])
    ## if avisos:
    ##     nombres = ", ".join([p["Nombre"] for p in avisos])
    ##     st.warning(f"📢 Tienes políticas pendientes: {nombres}")

    ## avisos = st.session_state.get("avisos_politicas", [])
    ## if avisos:
    ##     st.warning("📢 Tienes políticas pendientes de firmar:")
    ##     for p in avisos:
    ##         # Link con query param
    ##         st.markdown(
    ##             f"- 🔗 [**{p['Nombre']}**](?modulo=ver_docs_politicas&politica_id={p['Id']})"
    ##         )
    def construir_link_descarga(nombre_archivo, datos_binarios):
        tipo_mime, _ = mimetypes.guess_type(nombre_archivo)
        if not tipo_mime:
            tipo_mime = "application/octet-stream"
        b64 = base64.b64encode(datos_binarios).decode()
        return f'<a href="data:{tipo_mime};base64,{b64}" download="{nombre_archivo}">🔗 {nombre_archivo}</a>'

    avisos = st.session_state.get("avisos_politicas", [])
    if avisos:
        st.warning("📢 Tienes políticas pendientes de firmar:")
        for p in avisos:
            #nombre_archivo = f"{p['Nombre_archivo']}.{p['Extension']}"
            nombre_archivo = f"{p['Nombre_archivo']}"
            datos = p["Documento"]
            st.markdown(construir_link_descarga(nombre_archivo, datos), unsafe_allow_html=True)

    #### Finaliza el manejo de politicas

    #st.title("Panel principal")

    st.sidebar.success(f"{nombre}")
    if estatus == "Suspendido":
        st.sidebar.warning("⚠️ Tu cuenta está actualmente suspendida.")

    if st.sidebar.button("🔒 Cerrar sesión"):
        registrar_log(usuario.get("username", "-"), "Cerrar sesión", "-")
        st.session_state.clear()
        st.session_state["logout_success"] = True
        st.rerun()

    menu_opciones = {}

    if "SuperAdmin" in roles:
        menu_opciones["Compras"] = "compras"
        menu_opciones["Solicitudes Contabilidad"] = "solicitudesConta"
        menu_opciones["Solicitudes"] = "solicitudes"
        menu_opciones["Dashboard Auxiliar Contable"] = "auxconta"
        menu_opciones["Administracion de Presupuestos"] = "presupuestos"
        menu_opciones["💸 Registro de Gastos"] = "regGasto"
        menu_opciones["Unidades de Negocio"] = "unidades"
        menu_opciones["Politicas Internas"] = "PolInt"
        menu_opciones["📥 Mis políticas"] = "mis_pendientes"
        menu_opciones[" Tablero CFDI"] = "tab_cfdi" 
        menu_opciones["⚙️ Polizas "] = "polizas"
        menu_opciones["⚙️ Bridge COI - JAVA "] = "bridgeCJ"
        menu_opciones[" Prorrateo View"] = "prorrateo"
        menu_opciones[" Dashboard Prorrateos"] = "dash_prorrateos"
        menu_opciones[" Dashboard CXP"] = "cxp_dashboard"
        menu_opciones[" Gastos"] = "gastos"
        menu_opciones[" Ventas"] = "ventas"
        
        menu_opciones["⚙️ Configuración del sistema"] = "config"
        menu_opciones["📂 Ver documentos test"] = "ver_docs_test"
        menu_opciones["🗂️ Admin Tipos Test"] = "tipos_documento_test"
        menu_opciones[" Test"] = "test"
        menu_opciones["Test Navegacion"] = "test_navegacion"
        menu_opciones["📊 Matriz de permisos_test"] = "matriz_permisos_test"
        menu_opciones["Gastos - ksae10t"] = "ksae10t"

    if "Admin" in roles:
        menu_opciones["👥 Administración de usuarios"] = "admin_usuarios"
        menu_opciones["📤 Exportar Permisos"] = "exp_permisos"
        menu_opciones["📄 Historial de actividad"] = "historial"
        menu_opciones["🎭 Administración de roles"] = "roles"
        menu_opciones["⚙️ Administración de Archivos"] = "config"
        menu_opciones["🐇 Carga Multiple"] = "carga_multiple"
        menu_opciones["📁 -> 📁 Carga Estructura"] = "carga_estructura"
        menu_opciones["📊 Matriz de permisos"] = "matriz_permisos"
        menu_opciones["📥 Mis políticas"] = "mis_pendientes"
             
    if "Documentos" in roles:
        menu_opciones["🧑🏻‍💻 Navegar"] = "navegar"
        menu_opciones["📂 Ver documentos"] = "ver_docs"
        menu_opciones["📤 Subir documento"] = "subir_doc"
        menu_opciones["🕓 Historial de versiones"] = "historial_versiones"
        menu_opciones["🗂️ Tipos de documento"] = "tipos_documento"
        menu_opciones["📥 Mis políticas"] = "mis_pendientes"

    if "Usuarios_Presupuestos" in roles:
        menu_opciones["💸 Registro de Gastos"] = "regGasto"

    #if "Tablero CFDI" in roles:
    #    menu_opciones["Tablero CFDI"] = "tab_cfdi"

    if "Contabilidad" in roles:
        menu_opciones["Dashboard Auxiliar Contable"] = "auxconta"
        menu_opciones["Tablero CFDI"] = "tab_cfdi"        
        menu_opciones[" Dashboard Prorrateos"] = "dash_prorrateos"
        menu_opciones["📥 Mis políticas"] = "mis_pendientes"
        menu_opciones["Solicitudes Contabilidad"] = "solicitudesConta"

    if "Auxiliar Contable" in roles:
        menu_opciones["Dashboard Auxiliar Contable"] = "auxconta"
        menu_opciones["📥 Mis políticas"] = "mis_pendientes"
    #if "Control_Presupuestos" or "Admin_Presupuestos" in roles:
    #    menu_opciones["Administracion de Presupuestos"] = "presupuestos"
    
    #st.write("roles:", roles, type(roles))
    #st.write(f"Usuario {nombre}")
    if "Ventas" in roles:
        menu_opciones["Solicitudes"] = "solicitudes"
        menu_opciones["🧑🏻‍💻 Navegar"] = "navegar"
        menu_opciones["Administracion de Presupuestos"] = "presupuestos"
        menu_opciones["💸 Registro de Gastos"] = "regGasto"

    if "Compras" in roles:
        menu_opciones["Solicitudes"] = "solicitudes"


    #if menu_opciones:
    #    seleccion = st.sidebar.selectbox("Módulos disponibles", list(menu_opciones.keys()))
    #    modulo = menu_opciones[seleccion]

    if menu_opciones:
        opciones_menu = list(menu_opciones.keys())

        modulo_forzado = _get_modulo_forzado_desde_deeplink()
        idx_default = 0

        if modulo_forzado:
            for i, nombre_opcion in enumerate(opciones_menu):
                if menu_opciones[nombre_opcion] == modulo_forzado:
                    idx_default = i
                    break

        seleccion = st.sidebar.selectbox(
            "Módulos disponibles",
            opciones_menu,
            index=idx_default,
        )

        modulo = menu_opciones[seleccion]

        if st.session_state.get("modulo_forzado") == modulo:
            st.session_state["modulo_forzado"] = None

        if modulo == "admin_usuarios":
            from views.modulos_admin.admin_usuarios import mostrar_admin_usuarios
            mostrar_admin_usuarios()
        elif modulo == "test":
            from views.modulos_test.test import codigo_test
            codigo_test()
        elif modulo == "test_navegacion":
            from views.modulos_test.test_navegacion import mostrar_menu_documentos
            mostrar_menu_documentos()
        elif modulo == "exp_permisos":
            from views.modulos_documentos.exportar_permisos import exportar_permisos
            exportar_permisos()
        elif modulo == "historial":
            from views.modulos_admin.historial_actividad import mostrar_historial
            mostrar_historial()
        elif modulo == "roles":
            from views.modulos_admin.admin_roles import mostrar_admin_roles
            mostrar_admin_roles()
        elif modulo == "config":
            #st.info("Módulo de configuración en construcción.")
            from views.modulos_documentos.mostrar_documentos_admin import mostrar_documentos_admin
            mostrar_documentos_admin()
        elif modulo == "ver_docs":
            from views.modulos_documentos.ver_documentos import mostrar_documentos
            mostrar_documentos()
        elif modulo == "ver_docs_test":
            from views.modulos_documentos.ver_documentos_test import mostrar_documentos
            mostrar_documentos()
        elif modulo == "subir_doc":
            from views.modulos_documentos.subir_documento import mostrar_formulario_subida
            mostrar_formulario_subida()
        #elif modulo == "historial_versiones":
            #from views.modulos_documentos.historial_versiones import mostrar_historial_versiones
            #mostrar_historial_versiones()
        elif modulo == "tipos_documento":
            from views.modulos_documentos.admin_tipos import mostrar_admin_tipos
            mostrar_admin_tipos()
        elif modulo == "tipos_documento_test":
            from views.modulos_documentos.admin_tipos_old import mostrar_admin_tipos
            mostrar_admin_tipos()
        elif modulo == "navegar":
            from views.modulos_documentos.app_navegar import mostrar_menu_documentos
            mostrar_menu_documentos()
        elif modulo == "carga_multiple":
            from views.modulos_documentos.app_carga_multiple import cargar_multiples_documentos
            cargar_multiples_documentos()
        elif modulo == "carga_estructura":
            from views.modulos_documentos.app_carga_estructura_docs import cargar_estructura
            cargar_estructura()
        elif modulo == "matriz_permisos":
            from views.modulos_documentos.matriz_permisos import mostrar_matriz_permisos
            mostrar_matriz_permisos()
        elif modulo == "matriz_permisos_test":
            from views.modulos_documentos.matriz_permisos_test import mostrar_matriz_permisos
            mostrar_matriz_permisos()
        elif modulo == 'ksae10t':
            from views.modulos_iaspel.ksae10t import tablas_iaspel
            tablas_iaspel()
        elif modulo == 'polizas':
            from views.modulos_iaspel.polizas import pantalla_polizas
            pantalla_polizas()
        elif modulo == 'bridgeCJ':
            from views.modulos_iaspel.bridge_view import pantalla_bridge_java
            pantalla_bridge_java()
        elif modulo == 'prorrateo':
            from views.modulos_iaspel.prorrateo_view import pantalla_prorrateos
            pantalla_prorrateos()
        elif modulo == 'dash_prorrateos':
            from views.modulos_iaspel.dashboard_view import pantalla_dashboard
            pantalla_dashboard()
        elif modulo == 'cxp_dashboard':
            from views.modulos_iaspel.cxp_view import pantalla_cxp_vs_polizas
            pantalla_cxp_vs_polizas()
        elif modulo == 'gastos':
            from views.modulos_iaspel.gastos_view import pantalla_gastos
            pantalla_gastos()
        elif modulo == 'ventas':
            from views.modulos_iaspel.ventas_view import pantalla_ventas
            pantalla_ventas()
        elif modulo == 'tab_cfdi':
            from views.modulos_cfd.ada_view import pantalla_documentos_ada
            pantalla_documentos_ada()
        elif modulo == 'PolInt':
            from views.modulos_politicas.politica_view import mostrar_pestanas_politicas
            mostrar_pestanas_politicas()
        elif modulo == "mis_pendientes":
            from views.modulos_politicas.mis_pendientes_view import mostrar_mis_pendientes
            mostrar_mis_pendientes()
        elif modulo == "unidades":
            from views.modulo_unidades.dashboard_unidades import dashboard_unidades
            dashboard_unidades()
        elif modulo == "presupuestos":
            from views.modulo_presupuesto.presupuesto_view import pantalla_presupuestos
            pantalla_presupuestos()
        elif modulo == "regGasto":
            from views.modulo_presupuesto.registro_gastos_view import pantalla_registro_gastos
            pantalla_registro_gastos()
        elif modulo =="auxconta":
            from views.modulo_auxiliar_contable.dashboard_aux_contable_view import pantalla_dashboard_aux_conta
            pantalla_dashboard_aux_conta()
        elif modulo =="solicitudes":
            from views.modulo_solicitudes.solicitudes_gastos_view import mostrar_modulo_solicitudes_gastos
            mostrar_modulo_solicitudes_gastos()
        elif modulo =="solicitudesConta":
            from views.modulo_solicitudes.solicitudes_conta_view import mostrar_modulo_solicitudes_conta
            mostrar_modulo_solicitudes_conta() 
        elif modulo =="compras":
            from views.modulo_compras.compras_view import mostrar_modulo_compras
            mostrar_modulo_compras() 
    else:
        st.warning("⚠️ No tienes roles asignados para acceder a los módulos.")
        ## st.json(roles)
        ## if "usuario" in st.session_state:
        ##     st.write("🧪 Usuario cargado:", st.session_state["usuario"])
        ## else:
        ##     st.write("🧪 No se guarda la session")



