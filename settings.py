import os 


# Configuración general del sistema

# Conexión a la base de datos
DB_CONFIG = {
    "host": "localhost",
    "user": "root",         # ← remplazar
    "password": "genseg01",       # ← remplazar
    "database": "documentos"
}

# Nombre del sistema
NOMBRE_SISTEMA = "Sistema de Control Documental"

# Configuración de sesión/cookie
COOKIE_CONFIG = {
    "expiry_days": 3,
    "key": "firma_segura",
    "name": "auth_cookie"
}

# Configuración visual por rol (opcional)
ROL_ICONOS = {
    "Admin": "🔧",
    "Logistica": "📦",
    "Ventas": "🛒"
}

# Ruta absoluta al logo
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOGO_PATH = os.path.join(BASE_DIR, "static", "biotecsa.png")
