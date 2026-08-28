import mysql.connector

from mysql.connector import Error

from config import DB_CONFIG


# =========================================================
# CONEXIÓN MYSQL
# =========================================================

def conectar():

    try:

        conexion = mysql.connector.connect(

            host=DB_CONFIG["host"],

            port=DB_CONFIG["port"],

            user=DB_CONFIG["user"],

            password=DB_CONFIG["password"],

            database=DB_CONFIG["database"],

            charset="utf8mb4",

            use_unicode=True
        )


        if conexion.is_connected():

            return conexion


    except Error as error:

        print("")
        print("========================================")
        print("ERROR DE CONEXIÓN MYSQL")
        print("========================================")

        print(error)

        print("")

        print(
            "HOST:",
            DB_CONFIG["host"]
        )

        print(
            "PORT:",
            DB_CONFIG["port"]
        )

        print(
            "USER:",
            DB_CONFIG["user"]
        )

        print(
            "DATABASE:",
            DB_CONFIG["database"]
        )

        print("========================================")
        print("")

        return None


    except Exception as error:

        print("")
        print("========================================")
        print("ERROR GENERAL DE CONEXIÓN")
        print("========================================")
        print(error)
        print("========================================")
        print("")

        return None