from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for
)

from datetime import (
    datetime,
    date,
    timedelta
)

from database import conectar

from config import SECRET_KEY

from auth import (
    auth_bp,
    login_requerido,
    administrador_requerido,
    crear_admin_inicial
)


# =========================================================
# FLASK
# =========================================================

app = Flask(__name__)

app.secret_key = SECRET_KEY

app.register_blueprint(
    auth_bp
)


# =========================================================
# INICIALIZACIÓN
# FUNCIONA TAMBIÉN CON GUNICORN / RAILWAY
# =========================================================

_sistema_inicializado = False


@app.before_request
def inicializar_sistema():

    global _sistema_inicializado

    if not _sistema_inicializado:

        try:

            crear_admin_inicial()

            _sistema_inicializado = True

        except Exception as error:

            print(
                "ERROR INICIALIZANDO SISTEMA:",
                error
            )


# =========================================================
# UTILIDAD PARA HORAS MYSQL
# =========================================================

def hora_a_datetime(valor):

    if valor is None:

        return None


    if isinstance(
        valor,
        timedelta
    ):

        segundos = int(
            valor.total_seconds()
        )

        horas = segundos // 3600

        minutos = (
            segundos % 3600
        ) // 60

        segundos_restantes = (
            segundos % 60
        )


        return datetime.combine(
            date.today(),
            datetime.min.time()
        ).replace(
            hour=horas,
            minute=minutos,
            second=segundos_restantes
        )


    return datetime.combine(
        date.today(),
        valor
    )


def hora_formulario(valor):

    if valor is None:

        return ""


    if isinstance(
        valor,
        timedelta
    ):

        segundos = int(
            valor.total_seconds()
        )

        horas = segundos // 3600

        minutos = (
            segundos % 3600
        ) // 60


        return (
            f"{horas:02d}:"
            f"{minutos:02d}"
        )


    return valor.strftime(
        "%H:%M"
    )


# =========================================================
# DASHBOARD
# =========================================================

@app.route("/")
@login_requerido
def inicio():

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
            SELECT COUNT(*) AS total
            FROM alumnos
        """)

        total_alumnos = (
            cursor.fetchone()["total"]
        )


        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM alumnos
            WHERE estado = 'DISPONIBLE'
        """)

        disponibles = (
            cursor.fetchone()["total"]
        )


        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM alumnos
            WHERE estado = 'DESCANSO MÉDICO'
        """)

        descanso_medico = (
            cursor.fetchone()["total"]
        )


        cursor.execute("""
            SELECT
                COUNT(
                    DISTINCT id_alumno
                ) AS total

            FROM asistencia

            WHERE fecha = CURDATE()

            AND estado IN (
                'PUNTUAL',
                'ATRASADO'
            )
        """)

        presentes = (
            cursor.fetchone()["total"]
        )


        cursor.execute("""
            SELECT
                COUNT(
                    DISTINCT id_alumno
                ) AS total

            FROM asistencia

            WHERE fecha = CURDATE()

            AND estado = 'ATRASADO'
        """)

        atrasados = (
            cursor.fetchone()["total"]
        )


        ausentes = (
            total_alumnos -
            presentes
        )


        if ausentes < 0:

            ausentes = 0


        cursor.execute("""
            SELECT
                a.numero_lista,
                a.cedula,
                a.nombres,
                a.apellidos,
                a.estado AS estado_alumno,

                asi.fecha,
                asi.hora_entrada,
                asi.hora_salida,
                asi.estado,
                asi.horas_trabajadas

            FROM asistencia asi

            INNER JOIN alumnos a
                ON asi.id_alumno =
                   a.id_alumno

            ORDER BY
                asi.fecha DESC,
                asi.id_asistencia DESC

            LIMIT 8
        """)


        registros = (
            cursor.fetchall()
        )


        return render_template(
            "dashboard.html",

            total_alumnos=
                total_alumnos,

            disponibles=
                disponibles,

            descanso_medico=
                descanso_medico,

            presentes=
                presentes,

            atrasados=
                atrasados,

            ausentes=
                ausentes,

            registros=
                registros
        )


    except Exception as error:

        return (
            f"Error al cargar Dashboard: "
            f"{error}"
        )


    finally:

        cursor.close()
        conexion.close()


# =========================================================
# ALUMNOS
# =========================================================

@app.route("/alumnos")
@login_requerido
def alumnos():

    buscar = request.args.get(
        "buscar",
        ""
    ).strip()


    conexion = conectar()

    if conexion is None:

        return (
            "Error al conectar con MySQL"
        )


    cursor = conexion.cursor(
        dictionary=True
    )


    try:

        consulta = """
            SELECT *
            FROM alumnos

            WHERE 1 = 1
        """

        parametros = []


        if buscar:

            consulta += """
                AND (
                    cedula LIKE %s
                    OR nombres LIKE %s
                    OR apellidos LIKE %s
                    OR especialidad LIKE %s
                    OR CAST(numero_lista AS CHAR)
                       LIKE %s
                )
            """

            parametros.extend([
                f"%{buscar}%",
                f"%{buscar}%",
                f"%{buscar}%",
                f"%{buscar}%",
                f"%{buscar}%"
            ])


        consulta += """
            ORDER BY
                numero_lista IS NULL,
                numero_lista ASC,
                apellidos ASC,
                nombres ASC
        """


        cursor.execute(
            consulta,
            tuple(parametros)
        )


        lista = cursor.fetchall()


        return render_template(
            "alumnos.html",
            alumnos=lista,
            buscar=buscar
        )


    except Exception as error:

        return (
            f"Error al cargar alumnos: "
            f"{error}"
        )


    finally:

        cursor.close()
        conexion.close()


# =========================================================
# NUEVO ALUMNO
# =========================================================

@app.route(
    "/alumnos/nuevo",
    methods=[
        "GET",
        "POST"
    ]
)
@login_requerido
def nuevo_alumno():

    if request.method == "POST":

        try:

            numero_lista = int(
                request.form.get(
                    "numero_lista"
                )
            )

        except (
            ValueError,
            TypeError
        ):

            numero_lista = None


        cedula = request.form.get(
            "cedula",
            ""
        ).strip()


        nombres = request.form.get(
            "nombres",
            ""
        ).strip()


        apellidos = request.form.get(
            "apellidos",
            ""
        ).strip()


        curso = request.form.get(
            "curso",
            "Primer Año Militar"
        ).strip()


        paralelo = request.form.get(
            "paralelo",
            "C"
        ).strip()


        especialidad = request.form.get(
            "especialidad",
            "Especialidad por asignar"
        ).strip()


        estado = request.form.get(
            "estado",
            "DISPONIBLE"
        )


        if not especialidad:

            especialidad = (
                "Especialidad por asignar"
            )


        if estado not in [
            "DISPONIBLE",
            "DESCANSO MÉDICO"
        ]:

            estado = "DISPONIBLE"


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
                SELECT id_alumno
                FROM alumnos

                WHERE cedula = %s

                LIMIT 1
            """, (
                cedula,
            ))


            if cursor.fetchone():

                return (
                    "Ya existe un alumno "
                    "con esta cédula."
                )


            if numero_lista is not None:

                cursor.execute("""
                    SELECT id_alumno
                    FROM alumnos

                    WHERE numero_lista = %s

                    LIMIT 1
                """, (
                    numero_lista,
                ))


                if cursor.fetchone():

                    return (
                        "Ese número de lista "
                        "ya está asignado."
                    )


            cursor.execute("""
                INSERT INTO alumnos (
                    numero_lista,
                    cedula,
                    nombres,
                    apellidos,
                    curso,
                    paralelo,
                    especialidad,
                    estado
                )

                VALUES (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )
            """, (
                numero_lista,
                cedula,
                nombres,
                apellidos,
                curso,
                paralelo,
                especialidad,
                estado
            ))


            conexion.commit()


            return redirect(
                url_for("alumnos")
            )


        except Exception as error:

            conexion.rollback()

            return (
                f"Error al registrar alumno: "
                f"{error}"
            )


        finally:

            cursor.close()
            conexion.close()


    return render_template(
        "nuevo_alumno.html"
    )


# =========================================================
# EDITAR ALUMNO
# =========================================================

@app.route(
    "/alumnos/editar/<int:id_alumno>",
    methods=[
        "GET",
        "POST"
    ]
)
@login_requerido
def editar_alumno(id_alumno):

    conexion = conectar()

    if conexion is None:

        return (
            "Error al conectar con MySQL"
        )


    cursor = conexion.cursor(
        dictionary=True
    )


    try:

        if request.method == "POST":

            try:

                numero_lista = int(
                    request.form.get(
                        "numero_lista"
                    )
                )

            except (
                ValueError,
                TypeError
            ):

                numero_lista = None


            cedula = request.form.get(
                "cedula",
                ""
            ).strip()


            nombres = request.form.get(
                "nombres",
                ""
            ).strip()


            apellidos = request.form.get(
                "apellidos",
                ""
            ).strip()


            curso = request.form.get(
                "curso",
                ""
            ).strip()


            paralelo = request.form.get(
                "paralelo",
                ""
            ).strip()


            especialidad = request.form.get(
                "especialidad",
                ""
            ).strip()


            estado = request.form.get(
                "estado",
                "DISPONIBLE"
            )


            if not especialidad:

                especialidad = (
                    "Especialidad por asignar"
                )


            if estado not in [
                "DISPONIBLE",
                "DESCANSO MÉDICO"
            ]:

                estado = "DISPONIBLE"


            cursor.execute("""
                SELECT id_alumno
                FROM alumnos

                WHERE cedula = %s
                AND id_alumno <> %s
            """, (
                cedula,
                id_alumno
            ))


            if cursor.fetchone():

                return (
                    "La cédula ya pertenece "
                    "a otro alumno."
                )


            if numero_lista is not None:

                cursor.execute("""
                    SELECT id_alumno
                    FROM alumnos

                    WHERE numero_lista = %s
                    AND id_alumno <> %s
                """, (
                    numero_lista,
                    id_alumno
                ))


                if cursor.fetchone():

                    return (
                        "El número de lista ya "
                        "pertenece a otro alumno."
                    )


            cursor.execute("""
                UPDATE alumnos

                SET
                    numero_lista = %s,
                    cedula = %s,
                    nombres = %s,
                    apellidos = %s,
                    curso = %s,
                    paralelo = %s,
                    especialidad = %s,
                    estado = %s

                WHERE id_alumno = %s
            """, (
                numero_lista,
                cedula,
                nombres,
                apellidos,
                curso,
                paralelo,
                especialidad,
                estado,
                id_alumno
            ))


            conexion.commit()


            return redirect(
                url_for("alumnos")
            )


        cursor.execute("""
            SELECT *
            FROM alumnos
            WHERE id_alumno = %s
        """, (
            id_alumno,
        ))


        alumno = cursor.fetchone()


        if alumno is None:

            return (
                "Alumno no encontrado"
            )


        return render_template(
            "editar_alumno.html",
            alumno=alumno
        )


    except Exception as error:

        conexion.rollback()

        return (
            f"Error al editar alumno: "
            f"{error}"
        )


    finally:

        cursor.close()
        conexion.close()


# =========================================================
# CAMBIAR CONDICIÓN
# =========================================================

@app.route(
    "/alumnos/estado/<int:id_alumno>"
)
@administrador_requerido
def cambiar_estado_alumno(
    id_alumno
):

    conexion = conectar()

    if conexion is None:

        return (
            "Error al conectar con MySQL"
        )


    cursor = conexion.cursor()


    try:

        cursor.execute("""
            UPDATE alumnos

            SET estado = CASE

                WHEN estado =
                    'DISPONIBLE'

                THEN
                    'DESCANSO MÉDICO'

                ELSE
                    'DISPONIBLE'

            END

            WHERE id_alumno = %s
        """, (
            id_alumno,
        ))


        conexion.commit()


    except Exception as error:

        conexion.rollback()

        print(
            "ERROR CAMBIAR ESTADO:",
            error
        )


    finally:

        cursor.close()
        conexion.close()


    return redirect(
        url_for("alumnos")
    )


# =========================================================
# ELIMINAR ALUMNO
# =========================================================

@app.route(
    "/alumnos/eliminar/<int:id_alumno>"
)
@administrador_requerido
def eliminar_alumno(
    id_alumno
):

    conexion = conectar()

    if conexion is None:

        return (
            "Error al conectar con MySQL"
        )


    cursor = conexion.cursor()


    try:

        cursor.execute("""
            DELETE FROM asistencia
            WHERE id_alumno = %s
        """, (
            id_alumno,
        ))


        cursor.execute("""
            DELETE FROM alumnos
            WHERE id_alumno = %s
        """, (
            id_alumno,
        ))


        conexion.commit()


    except Exception as error:

        conexion.rollback()

        print(
            "ERROR ELIMINAR ALUMNO:",
            error
        )


    finally:

        cursor.close()
        conexion.close()


    return redirect(
        url_for("alumnos")
    )


# =========================================================
# ASISTENCIA
# =========================================================

@app.route("/asistencia")
@login_requerido
def asistencia():

    buscar = request.args.get(
        "buscar",
        ""
    ).strip()


    conexion = conectar()

    if conexion is None:

        return (
            "Error al conectar con MySQL"
        )


    cursor = conexion.cursor(
        dictionary=True
    )


    try:

        consulta = """
            SELECT
                a.id_alumno,
                a.numero_lista,
                a.cedula,
                a.nombres,
                a.apellidos,
                a.curso,
                a.paralelo,
                a.especialidad,

                a.estado AS condicion,

                asi.id_asistencia,
                asi.fecha,
                asi.hora_entrada,
                asi.hora_salida,

                asi.estado
                    AS estado_asistencia,

                asi.minutos_atraso,
                asi.horas_trabajadas,
                asi.observacion

            FROM alumnos a

            LEFT JOIN asistencia asi

                ON asi.id_alumno =
                   a.id_alumno

                AND asi.fecha =
                    CURDATE()

            WHERE 1 = 1
        """


        parametros = []


        if buscar:

            consulta += """
                AND (
                    a.cedula LIKE %s
                    OR a.nombres LIKE %s
                    OR a.apellidos LIKE %s
                    OR a.especialidad LIKE %s
                    OR CAST(
                        a.numero_lista AS CHAR
                    ) LIKE %s
                )
            """

            parametros.extend([
                f"%{buscar}%",
                f"%{buscar}%",
                f"%{buscar}%",
                f"%{buscar}%",
                f"%{buscar}%"
            ])


        consulta += """
            ORDER BY
                a.numero_lista IS NULL,
                a.numero_lista ASC,
                a.apellidos ASC,
                a.nombres ASC
        """


        cursor.execute(
            consulta,
            tuple(parametros)
        )


        lista = cursor.fetchall()


        total = len(lista)


        presentes = sum(
            1
            for alumno in lista
            if (
                alumno["hora_entrada"]
                is not None
            )
        )


        salidas = sum(
            1
            for alumno in lista
            if (
                alumno["hora_salida"]
                is not None
            )
        )


        sin_marcar = sum(
            1
            for alumno in lista
            if (
                alumno["hora_entrada"]
                is None
            )
        )


        atrasados = sum(
            1
            for alumno in lista
            if (
                alumno[
                    "estado_asistencia"
                ]
                == "ATRASADO"
            )
        )


        return render_template(
            "asistencia.html",

            alumnos=lista,

            buscar=buscar,

            total=total,

            presentes=presentes,

            salidas=salidas,

            sin_marcar=sin_marcar,

            atrasados=atrasados
        )


    except Exception as error:

        return (
            f"Error al cargar asistencia: "
            f"{error}"
        )


    finally:

        cursor.close()
        conexion.close()


# =========================================================
# MARCAR ENTRADA
# =========================================================

@app.route(
    "/asistencia/entrada/<int:id_alumno>"
)
@login_requerido
def marcar_entrada(
    id_alumno
):

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
            SELECT *
            FROM alumnos
            WHERE id_alumno = %s
        """, (
            id_alumno,
        ))


        alumno = cursor.fetchone()


        if alumno is None:

            return (
                "Alumno no encontrado"
            )


        cursor.execute("""
            SELECT *
            FROM asistencia

            WHERE id_alumno = %s
            AND fecha = CURDATE()

            LIMIT 1
        """, (
            id_alumno,
        ))


        if cursor.fetchone():

            return redirect(
                url_for("asistencia")
            )


        cursor.execute("""
            SELECT *
            FROM horarios

            WHERE estado = 'ACTIVO'

            ORDER BY
                id_horario DESC

            LIMIT 1
        """)


        horario = cursor.fetchone()


        if horario is None:

            return (
                "No existe un horario activo."
            )


        ahora = datetime.now()


        hora_limite = hora_a_datetime(
            horario["hora_entrada"]
        )


        if hora_limite is None:

            return (
                "El horario no tiene "
                "hora de entrada."
            )


        tolerancia = int(
            horario[
                "tolerancia_minutos"
            ]
            or 0
        )


        hora_limite += timedelta(
            minutes=tolerancia
        )


        if ahora <= hora_limite:

            estado = "PUNTUAL"

            minutos_atraso = 0


        else:

            estado = "ATRASADO"

            diferencia = (
                ahora -
                hora_limite
            )

            minutos_atraso = int(
                diferencia.total_seconds()
                / 60
            )


        cursor.execute("""
            INSERT INTO asistencia (
                id_alumno,
                fecha,
                hora_entrada,
                estado,
                minutos_atraso,
                horas_trabajadas
            )

            VALUES (
                %s,
                CURDATE(),
                CURTIME(),
                %s,
                %s,
                0
            )
        """, (
            id_alumno,
            estado,
            minutos_atraso
        ))


        conexion.commit()


        return redirect(
            url_for("asistencia")
        )


    except Exception as error:

        conexion.rollback()

        return (
            f"Error al marcar entrada: "
            f"{error}"
        )


    finally:

        cursor.close()
        conexion.close()


# =========================================================
# MARCAR SALIDA
# =========================================================

@app.route(
    "/asistencia/salida/<int:id_alumno>"
)
@login_requerido
def marcar_salida(
    id_alumno
):

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
            SELECT *
            FROM asistencia

            WHERE id_alumno = %s
            AND fecha = CURDATE()

            LIMIT 1
        """, (
            id_alumno,
        ))


        registro = cursor.fetchone()


        if registro is None:

            return redirect(
                url_for("asistencia")
            )


        if (
            registro["hora_salida"]
            is not None
        ):

            return redirect(
                url_for("asistencia")
            )


        entrada = hora_a_datetime(
            registro["hora_entrada"]
        )


        if entrada is None:

            return (
                "Registro sin hora "
                "de entrada."
            )


        ahora = datetime.now()


        diferencia = (
            ahora -
            entrada
        )


        horas = round(
            diferencia.total_seconds()
            / 3600,
            2
        )


        if horas < 0:

            horas = 0


        cursor.execute("""
            UPDATE asistencia

            SET
                hora_salida =
                    CURTIME(),

                horas_trabajadas =
                    %s

            WHERE
                id_asistencia = %s
        """, (
            horas,
            registro[
                "id_asistencia"
            ]
        ))


        conexion.commit()


        return redirect(
            url_for("asistencia")
        )


    except Exception as error:

        conexion.rollback()

        return (
            f"Error al marcar salida: "
            f"{error}"
        )


    finally:

        cursor.close()
        conexion.close()


# =========================================================
# HISTORIAL
# =========================================================

@app.route("/historial")
@login_requerido
def historial():

    buscar = request.args.get(
        "buscar",
        ""
    ).strip()

    fecha = request.args.get(
        "fecha",
        ""
    ).strip()

    estado = request.args.get(
        "estado",
        ""
    ).strip()


    conexion = conectar()

    if conexion is None:

        return (
            "Error al conectar con MySQL"
        )


    cursor = conexion.cursor(
        dictionary=True
    )


    try:

        consulta = """
            SELECT
                asi.*,

                a.numero_lista,
                a.cedula,
                a.nombres,
                a.apellidos,
                a.curso,
                a.paralelo,
                a.especialidad,

                a.estado
                    AS estado_alumno

            FROM asistencia asi

            INNER JOIN alumnos a

                ON asi.id_alumno =
                   a.id_alumno

            WHERE 1 = 1
        """


        parametros = []


        if buscar:

            consulta += """
                AND (
                    a.cedula LIKE %s
                    OR a.nombres LIKE %s
                    OR a.apellidos LIKE %s
                    OR a.especialidad LIKE %s
                    OR CAST(
                        a.numero_lista AS CHAR
                    ) LIKE %s
                )
            """

            parametros.extend([
                f"%{buscar}%",
                f"%{buscar}%",
                f"%{buscar}%",
                f"%{buscar}%",
                f"%{buscar}%"
            ])


        if fecha:

            consulta += """
                AND asi.fecha = %s
            """

            parametros.append(
                fecha
            )


        if estado:

            consulta += """
                AND asi.estado = %s
            """

            parametros.append(
                estado
            )


        consulta += """
            ORDER BY
                asi.fecha DESC,
                a.numero_lista IS NULL,
                a.numero_lista ASC,
                a.apellidos ASC
        """


        cursor.execute(
            consulta,
            tuple(parametros)
        )


        registros = cursor.fetchall()


        total_registros = len(
            registros
        )


        puntuales = sum(
            1
            for r in registros
            if r["estado"] == "PUNTUAL"
        )


        atrasados = sum(
            1
            for r in registros
            if r["estado"] == "ATRASADO"
        )


        ausentes = sum(
            1
            for r in registros
            if r["estado"] == "AUSENTE"
        )


        justificados = sum(
            1
            for r in registros
            if (
                r["estado"]
                == "JUSTIFICADO"
            )
        )


        total_horas = sum(
            float(
                r["horas_trabajadas"]
                or 0
            )
            for r in registros
        )


        return render_template(
            "historial.html",

            registros=registros,

            buscar=buscar,
            fecha=fecha,
            estado=estado,

            total_registros=
                total_registros,

            puntuales=
                puntuales,

            atrasados=
                atrasados,

            ausentes=
                ausentes,

            justificados=
                justificados,

            total_horas=
                round(
                    total_horas,
                    2
                )
        )


    except Exception as error:

        return (
            f"Error al cargar historial: "
            f"{error}"
        )


    finally:

        cursor.close()
        conexion.close()


# =========================================================
# HORARIOS
# =========================================================

@app.route("/horarios")
@login_requerido
def horarios():

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
            SELECT *
            FROM horarios

            ORDER BY
                estado = 'ACTIVO' DESC,
                id_horario DESC
        """)


        lista = cursor.fetchall()


        cursor.execute("""
            SELECT *
            FROM horarios

            WHERE estado = 'ACTIVO'

            ORDER BY
                id_horario DESC

            LIMIT 1
        """)


        activo = cursor.fetchone()


        return render_template(
            "horarios.html",

            horarios=lista,

            horario_activo=activo
        )


    except Exception as error:

        return (
            f"Error al cargar horarios: "
            f"{error}"
        )


    finally:

        cursor.close()
        conexion.close()


# =========================================================
# NUEVO HORARIO
# =========================================================

@app.route(
    "/horarios/nuevo",
    methods=[
        "GET",
        "POST"
    ]
)
@administrador_requerido
def nuevo_horario():

    if request.method == "POST":

        nombre = request.form.get(
            "nombre",
            ""
        ).strip()


        hora_entrada = request.form.get(
            "hora_entrada",
            ""
        )


        hora_salida = request.form.get(
            "hora_salida",
            ""
        )


        try:

            tolerancia = int(
                request.form.get(
                    "tolerancia_minutos",
                    0
                )
            )

        except (
            ValueError,
            TypeError
        ):

            tolerancia = 0


        if tolerancia < 0:

            tolerancia = 0


        conexion = conectar()

        if conexion is None:

            return (
                "Error al conectar con MySQL"
            )


        cursor = conexion.cursor()


        try:

            cursor.execute("""
                UPDATE horarios

                SET estado =
                    'INACTIVO'

                WHERE estado =
                    'ACTIVO'
            """)


            cursor.execute("""
                INSERT INTO horarios (
                    nombre,
                    hora_entrada,
                    hora_salida,
                    tolerancia_minutos,
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
                nombre,
                hora_entrada,
                hora_salida,
                tolerancia
            ))


            conexion.commit()


            return redirect(
                url_for("horarios")
            )


        except Exception as error:

            conexion.rollback()

            return (
                f"Error al crear horario: "
                f"{error}"
            )


        finally:

            cursor.close()
            conexion.close()


    return render_template(
        "nuevo_horario.html"
    )


# =========================================================
# EDITAR HORARIO
# =========================================================

@app.route(
    "/horarios/editar/<int:id_horario>",
    methods=[
        "GET",
        "POST"
    ]
)
@administrador_requerido
def editar_horario(
    id_horario
):

    conexion = conectar()

    if conexion is None:

        return (
            "Error al conectar con MySQL"
        )


    cursor = conexion.cursor(
        dictionary=True
    )


    try:

        if request.method == "POST":

            nombre = request.form.get(
                "nombre",
                ""
            ).strip()


            hora_entrada = request.form.get(
                "hora_entrada",
                ""
            )


            hora_salida = request.form.get(
                "hora_salida",
                ""
            )


            try:

                tolerancia = int(
                    request.form.get(
                        "tolerancia_minutos",
                        0
                    )
                )

            except (
                ValueError,
                TypeError
            ):

                tolerancia = 0


            cursor.execute("""
                UPDATE horarios

                SET
                    nombre = %s,
                    hora_entrada = %s,
                    hora_salida = %s,
                    tolerancia_minutos = %s

                WHERE id_horario = %s
            """, (
                nombre,
                hora_entrada,
                hora_salida,
                tolerancia,
                id_horario
            ))


            conexion.commit()


            return redirect(
                url_for("horarios")
            )


        cursor.execute("""
            SELECT *
            FROM horarios
            WHERE id_horario = %s
        """, (
            id_horario,
        ))


        horario = cursor.fetchone()


        if horario is None:

            return (
                "Horario no encontrado"
            )


        horario[
            "hora_entrada_form"
        ] = hora_formulario(
            horario["hora_entrada"]
        )


        horario[
            "hora_salida_form"
        ] = hora_formulario(
            horario["hora_salida"]
        )


        return render_template(
            "editar_horario.html",
            horario=horario
        )


    except Exception as error:

        conexion.rollback()

        return (
            f"Error al editar horario: "
            f"{error}"
        )


    finally:

        cursor.close()
        conexion.close()


# =========================================================
# ACTIVAR HORARIO
# =========================================================

@app.route(
    "/horarios/activar/<int:id_horario>"
)
@administrador_requerido
def activar_horario(
    id_horario
):

    conexion = conectar()

    if conexion is None:

        return (
            "Error al conectar con MySQL"
        )


    cursor = conexion.cursor()


    try:

        cursor.execute("""
            UPDATE horarios
            SET estado = 'INACTIVO'
        """)


        cursor.execute("""
            UPDATE horarios
            SET estado = 'ACTIVO'

            WHERE id_horario = %s
        """, (
            id_horario,
        ))


        conexion.commit()


    except Exception as error:

        conexion.rollback()

        print(
            "ERROR ACTIVAR HORARIO:",
            error
        )


    finally:

        cursor.close()
        conexion.close()


    return redirect(
        url_for("horarios")
    )


# =========================================================
# ELIMINAR HORARIO
# =========================================================

@app.route(
    "/horarios/eliminar/<int:id_horario>"
)
@administrador_requerido
def eliminar_horario(
    id_horario
):

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
            SELECT estado
            FROM horarios

            WHERE id_horario = %s
        """, (
            id_horario,
        ))


        horario = cursor.fetchone()


        if horario is None:

            return redirect(
                url_for("horarios")
            )


        if horario["estado"] == "ACTIVO":

            return redirect(
                url_for("horarios")
            )


        cursor.execute("""
            DELETE FROM horarios

            WHERE id_horario = %s
        """, (
            id_horario,
        ))


        conexion.commit()


    except Exception as error:

        conexion.rollback()

        print(
            "ERROR ELIMINAR HORARIO:",
            error
        )


    finally:

        cursor.close()
        conexion.close()


    return redirect(
        url_for("horarios")
    )


# =========================================================
# NÓMINA
# =========================================================

@app.route("/nomina")
@login_requerido
def nomina():

    buscar = request.args.get(
        "buscar",
        ""
    ).strip()


    estado = request.args.get(
        "estado",
        ""
    ).strip()


    conexion = conectar()

    if conexion is None:

        return (
            "Error al conectar con MySQL"
        )


    cursor = conexion.cursor(
        dictionary=True
    )


    try:

        consulta = """
            SELECT *
            FROM alumnos

            WHERE 1 = 1
        """


        parametros = []


        if buscar:

            consulta += """
                AND (
                    cedula LIKE %s
                    OR nombres LIKE %s
                    OR apellidos LIKE %s
                    OR especialidad LIKE %s
                    OR CAST(
                        numero_lista AS CHAR
                    ) LIKE %s
                )
            """

            parametros.extend([
                f"%{buscar}%",
                f"%{buscar}%",
                f"%{buscar}%",
                f"%{buscar}%",
                f"%{buscar}%"
            ])


        if estado in [
            "DISPONIBLE",
            "DESCANSO MÉDICO"
        ]:

            consulta += """
                AND estado = %s
            """

            parametros.append(
                estado
            )


        consulta += """
            ORDER BY
                numero_lista IS NULL,
                numero_lista ASC,
                apellidos ASC,
                nombres ASC
        """


        cursor.execute(
            consulta,
            tuple(parametros)
        )


        lista = cursor.fetchall()


        total = len(lista)


        disponibles = sum(
            1
            for alumno in lista
            if (
                alumno["estado"]
                == "DISPONIBLE"
            )
        )


        descanso_medico = sum(
            1
            for alumno in lista
            if (
                alumno["estado"]
                == "DESCANSO MÉDICO"
            )
        )


        return render_template(
            "nomina.html",

            alumnos=lista,

            buscar=buscar,

            estado=estado,

            total=total,

            disponibles=disponibles,

            descanso_medico=
                descanso_medico
        )


    except Exception as error:

        return (
            f"Error al cargar nómina: "
            f"{error}"
        )


    finally:

        cursor.close()
        conexion.close()


# =========================================================
# REPORTES
# =========================================================

@app.route("/reportes")
@login_requerido
def reportes():

    buscar = request.args.get(
        "buscar",
        ""
    ).strip()


    fecha_inicio = request.args.get(
        "fecha_inicio",
        ""
    ).strip()


    fecha_fin = request.args.get(
        "fecha_fin",
        ""
    ).strip()


    estado = request.args.get(
        "estado",
        ""
    ).strip()


    conexion = conectar()

    if conexion is None:

        return (
            "Error al conectar con MySQL"
        )


    cursor = conexion.cursor(
        dictionary=True
    )


    try:

        consulta = """
            SELECT
                asi.*,

                a.numero_lista,
                a.cedula,
                a.nombres,
                a.apellidos,
                a.curso,
                a.paralelo,
                a.especialidad,

                a.estado
                    AS estado_alumno

            FROM asistencia asi

            INNER JOIN alumnos a

                ON asi.id_alumno =
                   a.id_alumno

            WHERE 1 = 1
        """


        parametros = []


        if buscar:

            consulta += """
                AND (
                    a.cedula LIKE %s
                    OR a.nombres LIKE %s
                    OR a.apellidos LIKE %s
                    OR a.especialidad LIKE %s
                )
            """

            parametros.extend([
                f"%{buscar}%",
                f"%{buscar}%",
                f"%{buscar}%",
                f"%{buscar}%"
            ])


        if fecha_inicio:

            consulta += """
                AND asi.fecha >= %s
            """

            parametros.append(
                fecha_inicio
            )


        if fecha_fin:

            consulta += """
                AND asi.fecha <= %s
            """

            parametros.append(
                fecha_fin
            )


        if estado:

            consulta += """
                AND asi.estado = %s
            """

            parametros.append(
                estado
            )


        consulta += """
            ORDER BY
                asi.fecha DESC,
                a.numero_lista IS NULL,
                a.numero_lista ASC,
                a.apellidos ASC
        """


        cursor.execute(
            consulta,
            tuple(parametros)
        )


        registros = cursor.fetchall()


        total_registros = len(
            registros
        )


        puntuales = sum(
            1
            for r in registros
            if r["estado"] == "PUNTUAL"
        )


        atrasados = sum(
            1
            for r in registros
            if r["estado"] == "ATRASADO"
        )


        ausentes = sum(
            1
            for r in registros
            if r["estado"] == "AUSENTE"
        )


        justificados = sum(
            1
            for r in registros
            if (
                r["estado"]
                == "JUSTIFICADO"
            )
        )


        incompletos = sum(
            1
            for r in registros
            if (
                r["hora_entrada"]
                is not None
                and
                r["hora_salida"]
                is None
            )
        )


        total_horas = sum(
            float(
                r["horas_trabajadas"]
                or 0
            )
            for r in registros
        )


        total_atraso = sum(
            int(
                r["minutos_atraso"]
                or 0
            )
            for r in registros
        )


        alumnos_reportados = len({
            r["id_alumno"]
            for r in registros
        })


        registros_validos = (
            puntuales +
            atrasados
        )


        if registros_validos:

            porcentaje = round(
                (
                    puntuales
                    /
                    registros_validos
                ) * 100,
                1
            )

        else:

            porcentaje = 0


        return render_template(
            "reportes.html",

            registros=registros,

            buscar=buscar,

            fecha_inicio=fecha_inicio,

            fecha_fin=fecha_fin,

            estado=estado,

            total_registros=
                total_registros,

            puntuales=puntuales,

            atrasados=atrasados,

            ausentes=ausentes,

            justificados=
                justificados,

            incompletos=
                incompletos,

            total_horas=
                round(
                    total_horas,
                    2
                ),

            total_atraso=
                total_atraso,

            alumnos_reportados=
                alumnos_reportados,

            porcentaje_puntualidad=
                porcentaje
        )


    except Exception as error:

        return (
            f"Error al cargar reportes: "
            f"{error}"
        )


    finally:

        cursor.close()
        conexion.close()


# =========================================================
# CONFIGURACIÓN
# =========================================================

@app.route("/configuracion")
@administrador_requerido
def configuracion():

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
            SELECT *
            FROM horarios

            WHERE estado = 'ACTIVO'

            ORDER BY
                id_horario DESC

            LIMIT 1
        """)


        horario_activo = (
            cursor.fetchone()
        )


        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM alumnos
        """)

        total_alumnos = (
            cursor.fetchone()["total"]
        )


        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM alumnos

            WHERE estado = 'DISPONIBLE'
        """)

        disponibles = (
            cursor.fetchone()["total"]
        )


        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM alumnos

            WHERE estado =
                'DESCANSO MÉDICO'
        """)

        descanso_medico = (
            cursor.fetchone()["total"]
        )


        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM usuarios

            WHERE estado = 'ACTIVO'
        """)

        usuarios_activos = (
            cursor.fetchone()["total"]
        )


        return render_template(
            "configuracion.html",

            horario_activo=
                horario_activo,

            total_alumnos=
                total_alumnos,

            disponibles=
                disponibles,

            descanso_medico=
                descanso_medico,

            usuarios_activos=
                usuarios_activos
        )


    except Exception as error:

        return (
            f"Error al cargar configuración: "
            f"{error}"
        )


    finally:

        cursor.close()
        conexion.close()


# =========================================================
# EJECUCIÓN LOCAL
# =========================================================

if __name__ == "__main__":

    crear_admin_inicial()

    app.run(
        debug=True,
        host="0.0.0.0",
        port=5000
    )