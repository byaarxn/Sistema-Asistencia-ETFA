import mysql.connector

from mysql.connector import Error

from config import DB_CONFIG


# =========================================================
# CONECTAR A MYSQL
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

            use_unicode=True,

            connection_timeout=10
        )


        if conexion.is_connected():

            return conexion


        return None


    except Error as error:

        print("")
        print("========================================")
        print("ERROR DE CONEXIÓN MYSQL")
        print("========================================")
        print(error)
        print("========================================")
        print("")

        return None


    except Exception as error:

        print("")
        print("========================================")
        print("ERROR GENERAL DE BASE DE DATOS")
        print("========================================")
        print(error)
        print("========================================")
        print("")

        return None


# =========================================================
# PROBAR CONEXIÓN
# =========================================================

def probar_conexion():

    conexion = None
    cursor = None

    try:

        conexion = conectar()

        if conexion is None:

            print(
                "No se pudo conectar con MySQL."
            )

            return False


        cursor = conexion.cursor()

        cursor.execute(
            "SELECT DATABASE();"
        )

        resultado = cursor.fetchone()


        print("")
        print("========================================")
        print("CONEXIÓN MYSQL CORRECTA")
        print("========================================")
        print(
            "Base de datos:",
            resultado[0]
        )
        print("========================================")
        print("")


        return True


    except Exception as error:

        print(
            "ERROR:",
            error
        )

        return False


    finally:

        if cursor is not None:

            try:
                cursor.close()
            except Exception:
                pass


        if conexion is not None:

            try:

                if conexion.is_connected():
                    conexion.close()

            except Exception:
                pass


# =========================================================
# PRUEBA DIRECTA
# =========================================================

if __name__ == "__main__":

    probar_conexion()