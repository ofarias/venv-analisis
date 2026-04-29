# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Application

```bash
# Start the Streamlit app
streamlit run main.py

# Load test with Locust
locust -f locustfile.py --host=http://localhost:8501
```

There is no test suite. `app_login_test.py` is a standalone Locust/manual test script, not a pytest suite.

## Secrets Configuration

The app reads all credentials from `.streamlit/secrets.toml` (gitignored). This file must exist locally with the following sections:

```toml
[msal]
client_id = "..."
client_secret = "..."
redirect_uri = "..."
authority = "https://login.microsoftonline.com/<tenant>"
scopes = ["User.Read"]

[MYSQL_BIO]
host = "..."
user = "..."
password = "..."
database = "..."

[MYSQL_CTRLDOCE]
host = "..."
user = "..."
password = "..."
database = "..."

[MYSQL_TEST]
host = "..."
user = "..."
password = "..."
database = "..."

[FIREBIRD_BIO_ADA]
host = "..."
database = "..."
user = "..."
password = "..."
port = 3050
charset = "ISO8859_1"
```

`settings.py` and `database/conexion.py` contain hardcoded localhost credentials used only for the `documentos` MySQL database (user management). All other connections use `st.secrets`.

## Architecture

### Entry Point & Routing

`main.py` is the single Streamlit entrypoint. It renders a sidebar selectbox whose options are built dynamically based on `st.session_state["usuario"]["roles"]`. Each menu selection imports and calls the corresponding view function inline (no URL routing).

### Authentication Flow

1. User clicks "Entrar con Microsoft" → `controllers/auth_controller.py` builds an MSAL OAuth URL.
2. Microsoft redirects back with `?code=...` → `handle_redirect()` exchanges the code for an access token.
3. The Microsoft email (`preferred_username`) is looked up in the local MySQL `documentos` database via `models/usuario_model.py`.
4. On success, `st.session_state["usuario"]` and `st.session_state["microsoft_token"]` are populated and the app reruns.

The OAuth `state` parameter carries deeplink data (e.g., `?sg_id=...&t=...`) serialized as base64 JSON so it survives the Microsoft redirect. After login, `main.py` reads `st.session_state["modulo_forzado"]` to auto-select a module.

### Database Layer

There are two parallel DB access patterns in use:

| Pattern | File | When used |
|---|---|---|
| Raw `mysql.connector` | `database/conexion.py` → `obtener_conexion()` | User/auth/document models |
| SQLAlchemy + connection pool | `models/db.py` → `run_query(db_key, sql, params)` | Prorrateos (BIO), CFDIs (CTRLDOCE) |
| Firebird (fdb) | `models/db.py` → `run_query_firebird()` | IASPEL accounting data |
| Firebird (fdb, direct) | `models/ada_model.py` | CFDI/ADA documents from Firebird |

`models/db.py` manages named SQLAlchemy engines keyed by `"BIO"`, `"CTRLDOCE"`, and `"MYSQL_TEST"`, configured from `st.secrets`.

### Module Structure

Views are organized under `views/` by business domain:

- `modulos_admin/` — user management, roles, activity log
- `modulos_documentos/` — document upload, navigation, permissions matrix
- `modulos_iaspel/` — accounting integrations: pólizas, prorrateos, CXP dashboard, gastos, ventas (reads from Firebird/IASPEL)
- `modulos_cfd/` — CFDI/ADA tablero (reads from Firebird ADA database)
- `modulo_solicitudes/` — expense request workflow with approval tabs (solicitudes de gastos + contabilidad)
- `modulo_compras/` — purchase request workflow with catalogs
- `modulo_presupuesto/` — budget management and expense registration
- `modulo_presupuesto_ventas/` — sales budget upload
- `modulo_auxiliar_contable/` — accounting dashboard
- `modulo_unidades/` — business unit dashboard
- `modulos_politicas/` — internal policy management and pending signatures

Each module follows the pattern: `views/<module>/<module>_view.py` calls controller/model functions and renders `st.tabs()`.

### Email Notifications

`utils/envio_correo.py` sends email via **Microsoft Graph API** (`POST /v1.0/users/{sender}/sendMail`) using the OAuth access token stored in `st.session_state["microsoft_token"]`. There is no SMTP fallback.

### Roles

Roles are stored in MySQL and checked directly against `st.session_state["usuario"]["roles"]` (a list of strings). Key roles: `SuperAdmin`, `Admin`, `Contabilidad`, `Auxiliar Contable`, `Ventas`, `Compras`, `Documentos`, `Usuarios_Presupuestos`.

### Logging

`logs/logger.py` (gitignored at runtime) provides `registrar_log(username, action, detail)`. Calls are scattered across login/logout and module access via `utils/utils.py:registrar_acceso_modulo()`.
