from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    session
)

from functools import wraps

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

from database import conectar


# =========================================================
# BLUEPRINT
# =========================================================

auth_bp = Blueprint(
    "auth",
    __name__
)


# =========================================================
# LOGIN REQUERIDO
# =========================================================

def login_requerido(funcion):

    @wraps(funcion)
    def decorador(*args, **kwargs):

        if "id_usuario" not in session:

            return redirect(
                url_for("auth.login")
            )

        return funcion(
            *args,
            **kwargs
        )

    return decorador


# =========================================================
# ADMINISTRADOR REQUERIDO
# =========================================================

def administrador_requerido(funcion):

    @wraps(funcion)
    def decorador(*args, **kwargs):

        if "id_usuario" not in session:

            return redirect(
                url_for("auth.login")
            )

        if session.get("rol") != "ADMINISTRADOR":

            return redirect(
                url_for("inicio")
            )

        return funcion(
            *args,
            **kwargs
        )

    return decorador


# =========================================================
# LOGIN
# =========================================================

@auth_bp.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if "id_usuario" in session:

        return redirect(
            url_for("inicio")
        )

    error = None

    if request.method == "POST":

        usuario = request.form.get(
            "usuario",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )


        if not usuario or not password:

            error = (
                "Ingrese usuario y contraseña."
            )

            return render_template(
                "login.html",
                error=error
            )


        conexion = conectar()

        if conexion is None:

            return render_template(
                "login.html",
                error="Error al conectar con MySQL."
            )


        cursor = conexion.cursor(
            dictionary=True
        )


        try:

            cursor.execute("""
                SELECT *
                FROM usuarios

                WHERE usuario = %s

                LIMIT 1
            """, (
                usuario,
            ))


            datos = cursor.fetchone()


            if datos is None:

                error = (
                    "Usuario o contraseña incorrectos."
                )


            elif datos["estado"] != "ACTIVO":

                error = (
                    "Este usuario se encuentra inactivo."
                )


            elif not check_password_hash(
                datos["password"],
                password
            ):

                error = (
                    "Usuario o contraseña incorrectos."
                )


            else:

                session.clear()

                session["id_usuario"] = (
                    datos["id_usuario"]
                )

                session["usuario"] = (
                    datos["usuario"]
                )

                session["nombres"] = (
                    datos["nombres"]
                )

                session["rol"] = (
                    datos["rol"]
                )


                return redirect(
                    url_for("inicio")
                )


        except Exception as error_sql:

            print(
                "ERROR LOGIN:",
                error_sql
            )

            error = (
                "No se pudo iniciar sesión."
            )


        finally:

            cursor.close()
            conexion.close()


    return render_template(
        "login.html",
        error=error
    )


# =========================================================
# CERRAR SESIÓN
# =========================================================

@auth_bp.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("auth.login")
    )


# =========================================================
# LISTA DE USUARIOS
# =========================================================

@auth_bp.route("/usuarios")
@administrador_requerido
def usuarios():

    conexion = conectar()

    if conexion is None:

        return (
            "Error al conectar con MySQL"
        )


    cursor = conexion.cursor(
        dictionary=True
    )


    try:

        cursor.execute("""
            SELECT
                id_usuario,
                usuario,
                nombres,
                rol,
                estado,
                fecha_creacion

            FROM usuarios

            ORDER BY
                nombres ASC,
                usuario ASC
        """)


        lista_usuarios = (
            cursor.fetchall()
        )


        return render_template(
            "usuarios.html",
            usuarios=lista_usuarios
        )


    except Exception as error:

        return (
            f"Error al cargar usuarios: "
            f"{error}"
        )


    finally:

        cursor.close()
        conexion.close()


# =========================================================
# NUEVO USUARIO
# =========================================================

@auth_bp.route(
    "/usuarios/nuevo",
    methods=["GET", "POST"]
)
@administrador_requerido
def nuevo_usuario():

    error = None


    if request.method == "POST":

        nombres = request.form.get(
            "nombres",
            ""
        ).strip()

        usuario = request.form.get(
            "usuario",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        confirmar = request.form.get(
            "confirmar_password",
            ""
        )

        rol = request.form.get(
            "rol",
            "USUARIO"
        )


        if not nombres:

            error = (
                "Ingrese el nombre."
            )


        elif not usuario:

            error = (
                "Ingrese el usuario."
            )


        elif len(password) < 6:

            error = (
                "La contraseña debe tener "
                "mínimo 6 caracteres."
            )


        elif password != confirmar:

            error = (
                "Las contraseñas no coinciden."
            )


        if rol not in [
            "ADMINISTRADOR",
            "USUARIO"
        ]:

            rol = "USUARIO"


        if error:

            return render_template(
                "nuevo_usuario.html",
                error=error
            )


        conexion = conectar()

        if conexion is None:

            return (
                "Error al conectar con MySQL"
            )


        cursor = conexion.cursor(
            dictionary=True
        )


        try:

            # ---------------------------------------------
            # VALIDAR USUARIO REPETIDO
            # ---------------------------------------------

            cursor.execute("""
                SELECT id_usuario
                FROM usuarios

                WHERE usuario = %s

                LIMIT 1
            """, (
                usuario,
            ))


            existente = cursor.fetchone()


            if existente:

                return render_template(
                    "nuevo_usuario.html",
                    error=(
                        "Ese nombre de usuario "
                        "ya está registrado."
                    )
                )


            # ---------------------------------------------
            # CIFRAR CONTRASEÑA
            # ---------------------------------------------

            password_hash = (
                generate_password_hash(
                    password
                )
            )


            # ---------------------------------------------
            # INSERTAR USUARIO
            # ---------------------------------------------

            cursor.execute("""
                INSERT INTO usuarios (
                    usuario,
                    password,
                    nombres,
                    rol,
                    estado
                )

                VALUES (
                    %s,
                    %s,
                    %s,
                    %s,
                    'ACTIVO'
                )
            """, (
                usuario,
                password_hash,
                nombres,
                rol
            ))


            conexion.commit()


            return redirect(
                url_for(
                    "auth.usuarios"
                )
            )


        except Exception as error_sql:

            conexion.rollback()

            print(
                "ERROR NUEVO USUARIO:",
                error_sql
            )

            error = (
                "No se pudo registrar el usuario."
            )


        finally:

            cursor.close()
            conexion.close()


    return render_template(
        "nuevo_usuario.html",
        error=error
    )


# =========================================================
# EDITAR USUARIO
# =========================================================

@auth_bp.route(
    "/usuarios/editar/<int:id_usuario>",
    methods=["GET", "POST"]
)
@administrador_requerido
def editar_usuario(id_usuario):

    conexion = conectar()

    if conexion is None:

        return (
            "Error al conectar con MySQL"
        )


    cursor = conexion.cursor(
        dictionary=True
    )

    error = None


    try:

        if request.method == "POST":

            nombres = request.form.get(
                "nombres",
                ""
            ).strip()

            usuario = request.form.get(
                "usuario",
                ""
            ).strip()

            password = request.form.get(
                "password",
                ""
            )

            rol = request.form.get(
                "rol",
                "USUARIO"
            )

            estado = request.form.get(
                "estado",
                "ACTIVO"
            )


            if rol not in [
                "ADMINISTRADOR",
                "USUARIO"
            ]:

                rol = "USUARIO"


            if estado not in [
                "ACTIVO",
                "INACTIVO"
            ]:

                estado = "ACTIVO"


            # ---------------------------------------------
            # VALIDAR USUARIO REPETIDO
            # ---------------------------------------------

            cursor.execute("""
                SELECT id_usuario
                FROM usuarios

                WHERE usuario = %s
                AND id_usuario <> %s

                LIMIT 1
            """, (
                usuario,
                id_usuario
            ))


            existente = cursor.fetchone()


            if existente:

                error = (
                    "Ese nombre de usuario "
                    "pertenece a otra cuenta."
                )


            # ---------------------------------------------
            # CAMBIAR CONTRASEÑA
            # ---------------------------------------------

            elif password:

                if len(password) < 6:

                    error = (
                        "La contraseña debe tener "
                        "mínimo 6 caracteres."
                    )

                else:

                    password_hash = (
                        generate_password_hash(
                            password
                        )
                    )


                    cursor.execute("""
                        UPDATE usuarios

                        SET
                            nombres = %s,
                            usuario = %s,
                            password = %s,
                            rol = %s,
                            estado = %s

                        WHERE id_usuario = %s
                    """, (
                        nombres,
                        usuario,
                        password_hash,
                        rol,
                        estado,
                        id_usuario
                    ))


            # ---------------------------------------------
            # NO CAMBIAR CONTRASEÑA
            # ---------------------------------------------

            else:

                cursor.execute("""
                    UPDATE usuarios

                    SET
                        nombres = %s,
                        usuario = %s,
                        rol = %s,
                        estado = %s

                    WHERE id_usuario = %s
                """, (
                    nombres,
                    usuario,
                    rol,
                    estado,
                    id_usuario
                ))


            if error is None:

                conexion.commit()


                # -----------------------------------------
                # SI EDITA SU PROPIA CUENTA
                # -----------------------------------------

                if (
                    id_usuario
                    == session.get(
                        "id_usuario"
                    )
                ):

                    session["nombres"] = (
                        nombres
                    )

                    session["usuario"] = (
                        usuario
                    )

                    session["rol"] = (
                        rol
                    )


                return redirect(
                    url_for(
                        "auth.usuarios"
                    )
                )


        # -------------------------------------------------
        # CARGAR DATOS DEL USUARIO
        # -------------------------------------------------

        cursor.execute("""
            SELECT
                id_usuario,
                usuario,
                nombres,
                rol,
                estado

            FROM usuarios

            WHERE id_usuario = %s
        """, (
            id_usuario,
        ))


        datos = cursor.fetchone()


        if datos is None:

            return (
                "Usuario no encontrado"
            )


        return render_template(
            "editar_usuario.html",
            usuario=datos,
            error=error
        )


    except Exception as error_sql:

        conexion.rollback()

        return (
            f"Error al editar usuario: "
            f"{error_sql}"
        )


    finally:

        cursor.close()
        conexion.close()


# =========================================================
# CAMBIAR ESTADO DEL USUARIO
# =========================================================

@auth_bp.route(
    "/usuarios/estado/<int:id_usuario>"
)
@administrador_requerido
def cambiar_estado_usuario(id_usuario):

    # No permitir que el administrador
    # desactive su propia cuenta

    if (
        id_usuario
        == session.get("id_usuario")
    ):

        return redirect(
            url_for(
                "auth.usuarios"
            )
        )


    conexion = conectar()

    if conexion is None:

        return (
            "Error al conectar con MySQL"
        )


    cursor = conexion.cursor()


    try:

        cursor.execute("""
            UPDATE usuarios

            SET estado = CASE

                WHEN estado = 'ACTIVO'
                THEN 'INACTIVO'

                ELSE 'ACTIVO'

            END

            WHERE id_usuario = %s
        """, (
            id_usuario,
        ))


        conexion.commit()


    except Exception as error:

        conexion.rollback()

        print(
            "ERROR CAMBIAR ESTADO USUARIO:",
            error
        )


    finally:

        cursor.close()
        conexion.close()


    return redirect(
        url_for(
            "auth.usuarios"
        )
    )


# =========================================================
# CREAR TABLA DE USUARIOS
# =========================================================

def crear_tabla_usuarios():

    conexion = conectar()

    if conexion is None:

        return False


    cursor = conexion.cursor()


    try:

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (

                id_usuario INT
                AUTO_INCREMENT
                PRIMARY KEY,

                usuario VARCHAR(50)
                NOT NULL
                UNIQUE,

                password VARCHAR(255)
                NOT NULL,

                nombres VARCHAR(120)
                NOT NULL,

                rol ENUM(
                    'ADMINISTRADOR',
                    'USUARIO'
                )
                NOT NULL
                DEFAULT 'USUARIO',

                estado ENUM(
                    'ACTIVO',
                    'INACTIVO'
                )
                NOT NULL
                DEFAULT 'ACTIVO',

                fecha_creacion TIMESTAMP
                DEFAULT CURRENT_TIMESTAMP

            )
        """)


        conexion.commit()

        return True


    except Exception as error:

        conexion.rollback()

        print(
            "ERROR CREANDO TABLA USUARIOS:",
            error
        )

        return False


    finally:

        cursor.close()
        conexion.close()


# =========================================================
# CREAR ADMINISTRADOR INICIAL
# =========================================================

def crear_admin_inicial():

    # -----------------------------------------------------
    # ASEGURAR QUE EXISTA LA TABLA
    # -----------------------------------------------------

    if not crear_tabla_usuarios():

        return False


    conexion = conectar()

    if conexion is None:

        return False


    cursor = conexion.cursor(
        dictionary=True
    )


    try:

        # -------------------------------------------------
        # BUSCAR ADMINISTRADOR
        # -------------------------------------------------

        cursor.execute("""
            SELECT id_usuario

            FROM usuarios

            WHERE usuario = %s

            LIMIT 1
        """, (
            "admin",
        ))


        administrador = (
            cursor.fetchone()
        )


        # -------------------------------------------------
        # CREAR ADMIN SI NO EXISTE
        # -------------------------------------------------

        if administrador is None:

            password_hash = (
                generate_password_hash(
                    "admin123"
                )
            )


            cursor.execute("""
                INSERT INTO usuarios (
                    usuario,
                    password,
                    nombres,
                    rol,
                    estado
                )

                VALUES (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )
            """, (
                "admin",
                password_hash,
                "Administrador",
                "ADMINISTRADOR",
                "ACTIVO"
            ))


            conexion.commit()


            print("")
            print("========================================")
            print("ADMINISTRADOR INICIAL CREADO")
            print("========================================")
            print("Usuario: admin")
            print("Contraseña: admin123")
            print("========================================")
            print("")


        return True


    except Exception as error:

        conexion.rollback()

        print(
            "ERROR CREANDO ADMINISTRADOR:",
            error
        )

        return False


    finally:

        cursor.close()
        conexion.close()