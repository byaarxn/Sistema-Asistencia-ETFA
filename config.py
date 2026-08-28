import os


# =========================================================
# CONFIGURACIÓN MYSQL
# LOCAL + RAILWAY
# =========================================================

DB_CONFIG = {

    "host": os.getenv(
        "MYSQLHOST",
        "127.0.0.1"
    ),

    "port": int(
        os.getenv(
            "MYSQLPORT",
            "3306"
        )
    ),

    "user": os.getenv(
        "MYSQLUSER",
        "root"
    ),

    "password": os.getenv(
        "MYSQLPASSWORD",
        "12345"
    ),

    "database": os.getenv(
        "MYSQLDATABASE",
        "asistencia_etfa"
    )
}


# =========================================================
# SECRET KEY
# =========================================================

SECRET_KEY = os.getenv(
    "SECRET_KEY",
    "etfa-clave-secreta-local"
)