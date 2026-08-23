import os


# =========================================================
# CONFIGURACIÓN GENERAL DEL SISTEMA ETFA
# =========================================================

SECRET_KEY = os.environ.get(
    "SECRET_KEY",
    "ETFA_LOCAL_2026_DESARROLLO"
)


# =========================================================
# BASE DE DATOS
# =========================================================

# ---------------------------------------------------------
# PRODUCCIÓN - RAILWAY
# ---------------------------------------------------------

if os.environ.get("MYSQLHOST"):

    DB_CONFIG = {

        "host": os.environ.get("MYSQLHOST"),

        "port": int(
            os.environ.get(
                "MYSQLPORT",
                3306
            )
        ),

        "user": os.environ.get(
            "MYSQLUSER"
        ),

        "password": os.environ.get(
            "MYSQLPASSWORD"
        ),

        "database": os.environ.get(
            "MYSQLDATABASE"
        )
    }


# ---------------------------------------------------------
# LOCAL - TU COMPUTADORA
# ---------------------------------------------------------

else:

    DB_CONFIG = {

        "host": "127.0.0.1",

        "port": 3306,

        "user": "root",

        "password": "12345",

        # CAMBIA SOLO ESTO SI TU BASE
        # TIENE OTRO NOMBRE
        "database": "asistencia_etfa"
    }