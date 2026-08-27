from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session
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
# CONFIGURACIÓN GENERAL
# =========================================================

app = Flask(__name__)

app.secret_key = SECRET_KEY

app.register_blueprint(auth_bp)


# =========================================================
# INICIALIZACIÓN
# =========================================================

_sistema_inicializado = False


@app.before_request
def inicializar_sistema():

    global _sistema_inicializado

    if _sistema_inicializado:
        return

    try:

        crear_admin_inicial()

        _sistema_inicializado = True

    except Exception as error:

        print(
            "ERROR INICIALIZANDO SISTEMA:",
            error
        )


# =========================================================
# FUNCIONES AUXILIARES
# =========================================================

def hora_a_datetime(valor, fecha_base=None):

    if valor is None:
        return None

    if fecha_base is None:
        fecha_base = date.today()

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
            fecha_base,
            datetime.min.time()
        ).replace(
            hour=horas,
            minute=minutos,
            second=segundos_restantes
        )

    return datetime.combine(
        fecha_base,
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

        horas = (
            segundos // 3600
        )

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


def calcular_horas_bloque(
    hora_inicio,
    hora_fin
):

    inicio = hora_a_datetime(
        hora_inicio
    )

    fin = hora_a_datetime(
        hora_fin
    )

    if inicio is None or fin is None:
        return 0

    diferencia = (
        fin -
        inicio
    )

    horas = (
        diferencia.total_seconds()
        / 3600
    )

    if horas < 0:
        return 0

    return round(
        horas,
        2
    )


# =========================================================
# DASHBOARD
# =========================================================

@app.route("/")
@login_requerido
def inicio():

    conexion = conectar()

    if conexion is None:
        return "Error al conectar con MySQL"

    cursor = conexion.cursor(
        dictionary=True
    )

    try:

        # =================================================
        # TOTAL DE ALUMNOS
        # =================================================

        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM alumnos
        """)

        total_alumnos = cursor.fetchone()["total"]


        # =================================================
        # DISPONIBLES
        # =================================================

        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM alumnos
            WHERE estado = 'DISPONIBLE'
        """)

        disponibles = cursor.fetchone()["total"]


        # =================================================
        # DESCANSO MÉDICO
        # =================================================

        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM alumnos
            WHERE estado = 'DESCANSO MÉDICO'
        """)

        descanso_medico = cursor.fetchone()["total"]


        # =================================================
        # CLASE ACTUAL
        # =================================================

        cursor.execute("""
            SELECT
                h.id_horario_academico,
                h.fecha,
                h.dia_semana,
                h.hora_inicio,
                h.hora_fin,
                h.docente,
                h.lugar,
                h.horas_clase,
                h.estado,

                m.id_materia,
                m.codigo,
                m.nombre AS materia,
                m.tipo,
                m.contabiliza_asistencia

            FROM horario_academico h

            INNER JOIN materias m
                ON h.id_materia = m.id_materia

            WHERE h.fecha = CURDATE()

            AND CURTIME() >= h.hora_inicio
            AND CURTIME() < h.hora_fin

            AND h.estado <> 'CANCELADA'

            ORDER BY h.hora_inicio ASC

            LIMIT 1
        """)

        clase_actual = cursor.fetchone()


        # =================================================
        # PRÓXIMA CLASE / ACTIVIDAD
        # =================================================

        cursor.execute("""
            SELECT
                h.id_horario_academico,
                h.fecha,
                h.dia_semana,
                h.hora_inicio,
                h.hora_fin,
                h.docente,
                h.lugar,
                h.horas_clase,
                h.estado,

                m.id_materia,
                m.codigo,
                m.nombre AS materia,
                m.tipo,
                m.contabiliza_asistencia

            FROM horario_academico h

            INNER JOIN materias m
                ON h.id_materia = m.id_materia

            WHERE h.fecha = CURDATE()

            AND h.hora_inicio > CURTIME()

            AND h.estado <> 'CANCELADA'

            ORDER BY h.hora_inicio ASC

            LIMIT 1
        """)

        proxima_clase = cursor.fetchone()


        # =================================================
        # CLASES ACADÉMICAS PROGRAMADAS HOY
        # =================================================

        cursor.execute("""
            SELECT COUNT(*) AS total

            FROM horario_academico h

            INNER JOIN materias m
                ON h.id_materia = m.id_materia

            WHERE h.fecha = CURDATE()

            AND h.estado <> 'CANCELADA'

            AND m.contabiliza_asistencia = TRUE
        """)

        clases_hoy = cursor.fetchone()["total"]


        # =================================================
        # HORAS ACADÉMICAS PROGRAMADAS HOY
        # =================================================

        cursor.execute("""
            SELECT
                COALESCE(
                    SUM(h.horas_clase),
                    0
                ) AS total

            FROM horario_academico h

            INNER JOIN materias m
                ON h.id_materia = m.id_materia

            WHERE h.fecha = CURDATE()

            AND h.estado <> 'CANCELADA'

            AND m.contabiliza_asistencia = TRUE
        """)

        horas_hoy = float(
            cursor.fetchone()["total"] or 0
        )


        # =================================================
        # ASISTENCIA DE LA CLASE ACTUAL
        # =================================================

        presentes = 0
        ausentes = 0
        justificados = 0
        porcentaje_asistencia = 0


        if (
            clase_actual
            and clase_actual["contabiliza_asistencia"]
        ):

            id_clase = clase_actual[
                "id_horario_academico"
            ]


            cursor.execute("""
                SELECT
                    COUNT(*) AS total

                FROM asistencia_clases

                WHERE id_horario_academico = %s

                AND estado_asistencia = 'ASISTE'
            """, (
                id_clase,
            ))

            presentes = cursor.fetchone()["total"]


            cursor.execute("""
                SELECT
                    COUNT(*) AS total

                FROM asistencia_clases

                WHERE id_horario_academico = %s

                AND estado_asistencia = 'NO_ASISTE'
            """, (
                id_clase,
            ))

            ausentes = cursor.fetchone()["total"]


            cursor.execute("""
                SELECT
                    COUNT(*) AS total

                FROM asistencia_clases

                WHERE id_horario_academico = %s

                AND estado_asistencia = 'JUSTIFICADO'
            """, (
                id_clase,
            ))

            justificados = cursor.fetchone()["total"]


            total_registrados = (
                presentes
                + ausentes
                + justificados
            )


            if total_registrados > 0:

                porcentaje_asistencia = round(
                    (
                        presentes
                        / total_registrados
                    ) * 100,
                    1
                )

            else:

                # Todavía no se abrió la pantalla de asistencia:
                # según la regla del sistema todos comienzan como ASISTE.
                presentes = total_alumnos

                if total_alumnos > 0:
                    porcentaje_asistencia = 100


        # =================================================
        # ÚLTIMOS REGISTROS DE ASISTENCIA
        # =================================================

        cursor.execute("""
            SELECT
                ac.id_asistencia_clase,
                ac.fecha,
                ac.estado_asistencia,
                ac.horas_programadas,
                ac.horas_asistidas,
                ac.observacion,

                a.numero_lista,
                a.cedula,
                a.nombres,
                a.apellidos,
                a.curso,
                a.paralelo,
                a.estado AS condicion,

                h.hora_inicio,
                h.hora_fin,

                m.nombre AS materia

            FROM asistencia_clases ac

            INNER JOIN alumnos a
                ON ac.id_alumno = a.id_alumno

            INNER JOIN horario_academico h
                ON ac.id_horario_academico =
                   h.id_horario_academico

            INNER JOIN materias m
                ON h.id_materia = m.id_materia

            ORDER BY
                ac.fecha_modificacion DESC,
                ac.id_asistencia_clase DESC

            LIMIT 5
        """)

        registros = cursor.fetchall()


        return render_template(
            "dashboard.html",

            total_alumnos=total_alumnos,
            disponibles=disponibles,
            descanso_medico=descanso_medico,

            presentes=presentes,
            ausentes=ausentes,
            justificados=justificados,
            atrasados=0,

            clases_hoy=clases_hoy,
            horas_hoy=horas_hoy,

            porcentaje_asistencia=
                porcentaje_asistencia,

            clase_actual=clase_actual,
            proxima_clase=proxima_clase,

            registros=registros
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
        return "Error al conectar con MySQL"


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


        lista_alumnos = (
            cursor.fetchall()
        )


        return render_template(
            "alumnos.html",

            alumnos=
                lista_alumnos,

            buscar=
                buscar
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
        ).strip().title()


        apellidos = request.form.get(
            "apellidos",
            ""
        ).strip().title()


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


        if (
            not cedula.isdigit()
            or len(cedula) != 10
        ):

            return (
                "La cédula debe contener "
                "exactamente 10 dígitos."
            )


        conexion = conectar()

        if conexion is None:
            return "Error al conectar con MySQL"


        cursor = conexion.cursor(
            dictionary=True
        )


        try:

            # =================================================
            # VALIDAR CÉDULA
            # =================================================

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


            # =================================================
            # VALIDAR NÚMERO DE LISTA
            # =================================================

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
                        "El número de lista "
                        "ya está asignado."
                    )


            # =================================================
            # INSERTAR
            # =================================================

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
                url_for(
                    "alumnos"
                )
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
def editar_alumno(
    id_alumno
):

    conexion = conectar()

    if conexion is None:
        return "Error al conectar con MySQL"


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
            ).strip().title()


            apellidos = request.form.get(
                "apellidos",
                ""
            ).strip().title()


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


            if (
                not cedula.isdigit()
                or len(cedula) != 10
            ):

                return (
                    "La cédula debe contener "
                    "exactamente 10 dígitos."
                )


            # =================================================
            # CÉDULA DUPLICADA
            # =================================================

            cursor.execute("""
                SELECT id_alumno

                FROM alumnos

                WHERE cedula = %s
                AND id_alumno <> %s

                LIMIT 1
            """, (
                cedula,
                id_alumno
            ))


            if cursor.fetchone():

                return (
                    "La cédula pertenece "
                    "a otro alumno."
                )


            # =================================================
            # NÚMERO DE LISTA DUPLICADO
            # =================================================

            if numero_lista is not None:

                cursor.execute("""
                    SELECT id_alumno

                    FROM alumnos

                    WHERE numero_lista = %s
                    AND id_alumno <> %s

                    LIMIT 1
                """, (
                    numero_lista,
                    id_alumno
                ))


                if cursor.fetchone():

                    return (
                        "El número de lista "
                        "pertenece a otro alumno."
                    )


            # =================================================
            # ACTUALIZAR
            # =================================================

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
                url_for(
                    "alumnos"
                )
            )


        # =================================================
        # CARGAR ALUMNO
        # =================================================

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

            alumno=
                alumno
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
# CAMBIAR CONDICIÓN DEL ALUMNO
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
        return "Error al conectar con MySQL"


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
            "ERROR CAMBIANDO CONDICIÓN:",
            error
        )


    finally:

        cursor.close()
        conexion.close()


    return redirect(
        url_for(
            "alumnos"
        )
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
        return "Error al conectar con MySQL"


    cursor = conexion.cursor()


    try:

        # =================================================
        # ASISTENCIA ACADÉMICA
        # =================================================

        cursor.execute("""
            DELETE FROM asistencia_clases

            WHERE id_alumno = %s
        """, (
            id_alumno,
        ))


        # =================================================
        # ASISTENCIA ANTIGUA
        # SI LA TABLA EXISTE
        # =================================================

        try:

            cursor.execute("""
                DELETE FROM asistencia

                WHERE id_alumno = %s
            """, (
                id_alumno,
            ))

        except Exception:

            pass


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
            "ERROR ELIMINANDO ALUMNO:",
            error
        )


    finally:

        cursor.close()
        conexion.close()


    return redirect(
        url_for(
            "alumnos"
        )
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
        return "Error al conectar con MySQL"


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


        lista_alumnos = (
            cursor.fetchall()
        )


        total = len(
            lista_alumnos
        )


        disponibles = sum(
            1
            for alumno in lista_alumnos

            if (
                alumno["estado"]
                == "DISPONIBLE"
            )
        )


        descanso_medico = sum(
            1
            for alumno in lista_alumnos

            if (
                alumno["estado"]
                == "DESCANSO MÉDICO"
            )
        )


        return render_template(
            "nomina.html",

            alumnos=
                lista_alumnos,

            buscar=
                buscar,

            estado=
                estado,

            total=
                total,

            disponibles=
                disponibles,

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
# MATERIAS
# =========================================================

@app.route("/materias")
@login_requerido
def materias():

    conexion = conectar()

    if conexion is None:
        return "Error al conectar con MySQL"


    cursor = conexion.cursor(
        dictionary=True
    )


    try:

        cursor.execute("""
            SELECT *
            FROM materias

            ORDER BY
                nombre ASC
        """)


        lista = (
            cursor.fetchall()
        )


        return render_template(
            "materias.html",

            materias=
                lista
        )


    except Exception as error:

        return (
            f"Error al cargar materias: "
            f"{error}"
        )


    finally:

        cursor.close()
        conexion.close()


# =========================================================
# NUEVA MATERIA
# =========================================================

@app.route(
    "/materias/nueva",
    methods=[
        "GET",
        "POST"
    ]
)
@administrador_requerido
def nueva_materia():

    if request.method == "POST":

        codigo = request.form.get(
            "codigo",
            ""
        ).strip()


        nombre = request.form.get(
            "nombre",
            ""
        ).strip()


        tipo = request.form.get(
            "tipo",
            "MATERIA"
        )


        contabiliza = (
            request.form.get(
                "contabiliza_asistencia"
            )
            == "1"
        )


        tipos_validos = [
            "MATERIA",
            "EXAMEN",
            "REGIMEN_INTERNO",
            "ENTRENAMIENTO_FISICO",
            "TRABAJO_AUTONOMO",
            "ACTO_CIVICO",
            "ALIMENTACION",
            "RECESO",
            "OTRO"
        ]


        if tipo not in tipos_validos:

            tipo = "MATERIA"


        conexion = conectar()

        if conexion is None:
            return "Error al conectar con MySQL"


        cursor = conexion.cursor()


        try:

            cursor.execute("""
                INSERT INTO materias (
                    codigo,
                    nombre,
                    tipo,
                    contabiliza_asistencia,
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
                codigo or None,
                nombre,
                tipo,
                contabiliza
            ))


            conexion.commit()


            return redirect(
                url_for(
                    "materias"
                )
            )


        except Exception as error:

            conexion.rollback()

            return (
                f"Error al crear materia: "
                f"{error}"
            )


        finally:

            cursor.close()
            conexion.close()


    return render_template(
        "nueva_materia.html"
    )


# =========================================================
# HORARIO ACADÉMICO
# =========================================================

@app.route("/horarios")
@login_requerido
def horarios():

    fecha_busqueda = request.args.get(
        "fecha",
        ""
    ).strip()


    conexion = conectar()

    if conexion is None:
        return "Error al conectar con MySQL"


    cursor = conexion.cursor(
        dictionary=True
    )


    try:

        consulta = """
            SELECT
                h.*,

                m.codigo,
                m.nombre AS materia,
                m.tipo,
                m.contabiliza_asistencia

            FROM horario_academico h

            INNER JOIN materias m
                ON h.id_materia =
                   m.id_materia

            WHERE 1 = 1
        """


        parametros = []


        if fecha_busqueda:

            consulta += """
                AND h.fecha = %s
            """

            parametros.append(
                fecha_busqueda
            )


        consulta += """
            ORDER BY
                h.fecha ASC,
                h.hora_inicio ASC
        """


        cursor.execute(
            consulta,
            tuple(parametros)
        )


        lista_horarios = (
            cursor.fetchall()
        )


        # =================================================
        # CLASE ACTUAL
        # =================================================

        cursor.execute("""
            SELECT
                h.*,
                m.nombre AS materia,
                m.tipo,
                m.contabiliza_asistencia

            FROM horario_academico h

            INNER JOIN materias m
                ON h.id_materia =
                   m.id_materia

            WHERE h.fecha = CURDATE()

            AND CURTIME() >=
                h.hora_inicio

            AND CURTIME() <
                h.hora_fin

            AND h.estado <>
                'CANCELADA'

            ORDER BY
                h.hora_inicio ASC

            LIMIT 1
        """)


        horario_activo = (
            cursor.fetchone()
        )


        return render_template(
            "horarios.html",

            horarios=
                lista_horarios,

            horario_activo=
                horario_activo,

            fecha_busqueda=
                fecha_busqueda
        )


    except Exception as error:

        return (
            f"Error al cargar horario académico: "
            f"{error}"
        )


    finally:

        cursor.close()
        conexion.close()


# =========================================================
# NUEVO BLOQUE DE HORARIO
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

    conexion = conectar()

    if conexion is None:
        return "Error al conectar con MySQL"


    cursor = conexion.cursor(
        dictionary=True
    )


    try:

        if request.method == "POST":

            fecha = request.form.get(
                "fecha"
            )


            dia_semana = request.form.get(
                "dia_semana",
                ""
            ).strip()


            hora_inicio = request.form.get(
                "hora_inicio"
            )


            hora_fin = request.form.get(
                "hora_fin"
            )


            id_materia = request.form.get(
                "id_materia"
            )


            docente = request.form.get(
                "docente",
                ""
            ).strip()


            lugar = request.form.get(
                "lugar",
                ""
            ).strip()


            numero_hora = request.form.get(
                "numero_hora"
            )


            curso = request.form.get(
                "curso",
                "Primer Año Militar"
            ).strip()


            paralelo = request.form.get(
                "paralelo",
                "C"
            ).strip()


            horas_clase = (
                calcular_horas_bloque(
                    datetime.strptime(
                        hora_inicio,
                        "%H:%M"
                    ).time(),
                    datetime.strptime(
                        hora_fin,
                        "%H:%M"
                    ).time()
                )
            )


            cursor.execute("""
                INSERT INTO horario_academico (
                    fecha,
                    dia_semana,
                    hora_inicio,
                    hora_fin,
                    id_materia,
                    docente,
                    lugar,
                    numero_hora,
                    horas_clase,
                    curso,
                    paralelo,
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
                    %s,
                    %s,
                    %s,
                    %s,
                    'PROGRAMADA'
                )
            """, (
                fecha,
                dia_semana,
                hora_inicio,
                hora_fin,
                id_materia,
                docente,
                lugar,
                numero_hora or None,
                horas_clase,
                curso,
                paralelo
            ))


            conexion.commit()


            return redirect(
                url_for(
                    "horarios"
                )
            )


        cursor.execute("""
            SELECT *
            FROM materias

            WHERE estado = 'ACTIVO'

            ORDER BY
                nombre ASC
        """)


        lista_materias = (
            cursor.fetchall()
        )


        return render_template(
            "nuevo_horario.html",

            materias=
                lista_materias
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


# =========================================================
# EDITAR BLOQUE ACADÉMICO
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
        return "Error al conectar con MySQL"


    cursor = conexion.cursor(
        dictionary=True
    )


    try:

        if request.method == "POST":

            fecha = request.form.get(
                "fecha"
            )


            dia_semana = request.form.get(
                "dia_semana",
                ""
            ).strip()


            hora_inicio = request.form.get(
                "hora_inicio"
            )


            hora_fin = request.form.get(
                "hora_fin"
            )


            id_materia = request.form.get(
                "id_materia"
            )


            docente = request.form.get(
                "docente",
                ""
            ).strip()


            lugar = request.form.get(
                "lugar",
                ""
            ).strip()


            estado = request.form.get(
                "estado",
                "PROGRAMADA"
            )


            estados_validos = [
                "PROGRAMADA",
                "EN_CURSO",
                "FINALIZADA",
                "CANCELADA"
            ]


            if estado not in estados_validos:

                estado = "PROGRAMADA"


            horas_clase = (
                calcular_horas_bloque(
                    datetime.strptime(
                        hora_inicio,
                        "%H:%M"
                    ).time(),
                    datetime.strptime(
                        hora_fin,
                        "%H:%M"
                    ).time()
                )
            )


            cursor.execute("""
                UPDATE horario_academico

                SET
                    fecha = %s,
                    dia_semana = %s,
                    hora_inicio = %s,
                    hora_fin = %s,
                    id_materia = %s,
                    docente = %s,
                    lugar = %s,
                    horas_clase = %s,
                    estado = %s

                WHERE
                    id_horario_academico = %s
            """, (
                fecha,
                dia_semana,
                hora_inicio,
                hora_fin,
                id_materia,
                docente,
                lugar,
                horas_clase,
                estado,
                id_horario
            ))


            conexion.commit()


            return redirect(
                url_for(
                    "horarios"
                )
            )


        cursor.execute("""
            SELECT *
            FROM horario_academico

            WHERE
                id_horario_academico = %s
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
            horario["hora_inicio"]
        )


        horario[
            "hora_salida_form"
        ] = hora_formulario(
            horario["hora_fin"]
        )


        cursor.execute("""
            SELECT *
            FROM materias

            WHERE estado = 'ACTIVO'

            ORDER BY nombre ASC
        """)


        lista_materias = (
            cursor.fetchall()
        )


        return render_template(
            "editar_horario.html",

            horario=
                horario,

            materias=
                lista_materias
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
# ELIMINAR BLOQUE ACADÉMICO
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
        return "Error al conectar con MySQL"


    cursor = conexion.cursor()


    try:

        cursor.execute("""
            DELETE FROM horario_academico

            WHERE
                id_horario_academico = %s
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
        url_for(
            "horarios"
        )
    )


# =========================================================
# ACTIVAR / PROGRAMAR BLOQUE
# COMPATIBILIDAD CON PLANTILLAS ANTERIORES
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
        return "Error al conectar con MySQL"


    cursor = conexion.cursor()


    try:

        cursor.execute("""
            UPDATE horario_academico

            SET estado = 'PROGRAMADA'

            WHERE
                id_horario_academico = %s
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
        url_for(
            "horarios"
        )
    )


# =========================================================
# ASISTENCIA ACADÉMICA AUTOMÁTICA
# =========================================================

@app.route("/asistencia")
@login_requerido
def asistencia():

    buscar = request.args.get(
        "buscar",
        ""
    ).strip()


    id_horario_manual = (
        request.args.get(
            "id_horario",
            ""
        ).strip()
    )


    conexion = conectar()

    if conexion is None:
        return "Error al conectar con MySQL"


    cursor = conexion.cursor(
        dictionary=True
    )


    try:

        clase_actual = None


        # =================================================
        # PERMITIR VER UNA CLASE ESPECÍFICA
        # ÚTIL PARA PRUEBAS O CORRECCIONES
        # =================================================

        if id_horario_manual:

            cursor.execute("""
                SELECT
                    h.*,

                    m.codigo,
                    m.nombre AS materia,
                    m.tipo,
                    m.contabiliza_asistencia

                FROM horario_academico h

                INNER JOIN materias m
                    ON h.id_materia =
                       m.id_materia

                WHERE
                    h.id_horario_academico = %s

                LIMIT 1
            """, (
                id_horario_manual,
            ))


            clase_actual = (
                cursor.fetchone()
            )


        # =================================================
        # DETECTAR CLASE AUTOMÁTICAMENTE
        # =================================================

        else:

            cursor.execute("""
                SELECT
                    h.*,

                    m.codigo,
                    m.nombre AS materia,
                    m.tipo,
                    m.contabiliza_asistencia

                FROM horario_academico h

                INNER JOIN materias m
                    ON h.id_materia =
                       m.id_materia

                WHERE h.fecha = CURDATE()

                AND CURTIME() >=
                    h.hora_inicio

                AND CURTIME() <
                    h.hora_fin

                AND h.estado <>
                    'CANCELADA'

                ORDER BY
                    h.hora_inicio ASC

                LIMIT 1
            """)


            clase_actual = (
                cursor.fetchone()
            )


        # =================================================
        # NO HAY CLASE ACTUAL
        # =================================================

        if clase_actual is None:

            cursor.execute("""
                SELECT
                    h.*,

                    m.nombre AS materia,
                    m.tipo,
                    m.contabiliza_asistencia

                FROM horario_academico h

                INNER JOIN materias m
                    ON h.id_materia =
                       m.id_materia

                WHERE h.fecha = CURDATE()

                AND h.hora_inicio >
                    CURTIME()

                AND h.estado <>
                    'CANCELADA'

                ORDER BY
                    h.hora_inicio ASC

                LIMIT 1
            """)


            proxima_clase = (
                cursor.fetchone()
            )


            return render_template(
                "asistencia.html",

                clase_actual=None,

                proxima_clase=
                    proxima_clase,

                alumnos=[],

                buscar=
                    buscar,

                total=0,

                asisten=0,

                no_asisten=0,

                justificados=0
            )


        # =================================================
        # ACTIVIDAD QUE NO CONTABILIZA ASISTENCIA
        # =================================================

        if not clase_actual[
            "contabiliza_asistencia"
        ]:

            return render_template(
                "asistencia.html",

                clase_actual=
                    clase_actual,

                proxima_clase=None,

                alumnos=[],

                buscar=
                    buscar,

                total=0,

                asisten=0,

                no_asisten=0,

                justificados=0
            )


        # =================================================
        # GENERAR ASISTENCIA AUTOMÁTICAMENTE
        #
        # REGLA:
        #
        # DISPONIBLE       -> ASISTE
        # DESCANSO MÉDICO  -> ASISTE
        #
        # SOLO EL DOCENTE CAMBIA
        # A NO_ASISTE O JUSTIFICADO.
        # =================================================

        cursor.execute("""
            INSERT IGNORE INTO asistencia_clases (
                id_horario_academico,
                id_alumno,
                fecha,
                estado_asistencia,
                horas_programadas,
                horas_asistidas,
                id_usuario_registro
            )

            SELECT
                %s,
                a.id_alumno,
                %s,
                'ASISTE',
                %s,
                %s,
                %s

            FROM alumnos a
        """, (
            clase_actual[
                "id_horario_academico"
            ],

            clase_actual[
                "fecha"
            ],

            clase_actual[
                "horas_clase"
            ],

            clase_actual[
                "horas_clase"
            ],

            session.get(
                "id_usuario"
            )
        ))


        cursor.execute("""
            UPDATE horario_academico

            SET
                asistencia_generada =
                    TRUE,

                estado =
                    CASE

                        WHEN estado =
                            'PROGRAMADA'

                        THEN
                            'EN_CURSO'

                        ELSE
                            estado

                    END

            WHERE
                id_horario_academico = %s
        """, (
            clase_actual[
                "id_horario_academico"
            ],
        ))


        conexion.commit()


        # =================================================
        # CARGAR NÓMINA
        # =================================================

        consulta = """
            SELECT
                a.id_alumno,
                a.numero_lista,
                a.cedula,
                a.nombres,
                a.apellidos,
                a.especialidad,

                a.estado
                    AS condicion,

                ac.id_asistencia_clase,
                ac.estado_asistencia,
                ac.horas_programadas,
                ac.horas_asistidas,
                ac.observacion

            FROM alumnos a

            INNER JOIN asistencia_clases ac

                ON ac.id_alumno =
                   a.id_alumno

            WHERE
                ac.id_horario_academico = %s
        """


        parametros = [
            clase_actual[
                "id_horario_academico"
            ]
        ]


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


        lista_alumnos = (
            cursor.fetchall()
        )


        total = len(
            lista_alumnos
        )


        asisten = sum(
            1
            for alumno in lista_alumnos

            if (
                alumno[
                    "estado_asistencia"
                ]
                == "ASISTE"
            )
        )


        no_asisten = sum(
            1
            for alumno in lista_alumnos

            if (
                alumno[
                    "estado_asistencia"
                ]
                == "NO_ASISTE"
            )
        )


        justificados = sum(
            1
            for alumno in lista_alumnos

            if (
                alumno[
                    "estado_asistencia"
                ]
                == "JUSTIFICADO"
            )
        )


        return render_template(
            "asistencia.html",

            clase_actual=
                clase_actual,

            proxima_clase=None,

            alumnos=
                lista_alumnos,

            buscar=
                buscar,

            total=
                total,

            asisten=
                asisten,

            no_asisten=
                no_asisten,

            justificados=
                justificados
        )


    except Exception as error:

        conexion.rollback()

        return (
            "Error al cargar asistencia "
            f"académica: {error}"
        )


    finally:

        cursor.close()
        conexion.close()


# =========================================================
# CAMBIAR ASISTENCIA DE UN ALUMNO
# =========================================================

@app.route(
    "/asistencia/clase/<int:id_asistencia_clase>/<estado>",
    methods=[
        "GET",
        "POST"
    ]
)
@login_requerido
def cambiar_asistencia_clase(
    id_asistencia_clase,
    estado
):

    estados_validos = [
        "ASISTE",
        "NO_ASISTE",
        "JUSTIFICADO"
    ]


    if estado not in estados_validos:

        return redirect(
            url_for(
                "asistencia"
            )
        )


    conexion = conectar()

    if conexion is None:
        return "Error al conectar con MySQL"


    cursor = conexion.cursor(
        dictionary=True
    )


    try:

        cursor.execute("""
            SELECT
                id_asistencia_clase,
                id_horario_academico,
                horas_programadas

            FROM asistencia_clases

            WHERE
                id_asistencia_clase = %s
        """, (
            id_asistencia_clase,
        ))


        registro = (
            cursor.fetchone()
        )


        if registro is None:

            return redirect(
                url_for(
                    "asistencia"
                )
            )


        # =================================================
        # HORAS
        # =================================================

        if estado == "ASISTE":

            horas_asistidas = (
                registro[
                    "horas_programadas"
                ]
            )

        else:

            horas_asistidas = 0


        cursor.execute("""
            UPDATE asistencia_clases

            SET
                estado_asistencia = %s,
                horas_asistidas = %s,
                id_usuario_registro = %s

            WHERE
                id_asistencia_clase = %s
        """, (
            estado,
            horas_asistidas,
            session.get(
                "id_usuario"
            ),
            id_asistencia_clase
        ))


        conexion.commit()


        return redirect(
            url_for(
                "asistencia",
                id_horario=
                    registro[
                        "id_horario_academico"
                    ]
            )
        )


    except Exception as error:

        conexion.rollback()

        return (
            f"Error al cambiar asistencia: "
            f"{error}"
        )


    finally:

        cursor.close()
        conexion.close()


# =========================================================
# GUARDAR OBSERVACIÓN
# =========================================================

@app.route(
    "/asistencia/observacion/<int:id_asistencia_clase>",
    methods=[
        "POST"
    ]
)
@login_requerido
def guardar_observacion(
    id_asistencia_clase
):

    observacion = request.form.get(
        "observacion",
        ""
    ).strip()


    conexion = conectar()

    if conexion is None:
        return "Error al conectar con MySQL"


    cursor = conexion.cursor(
        dictionary=True
    )


    try:

        cursor.execute("""
            SELECT
                id_horario_academico

            FROM asistencia_clases

            WHERE
                id_asistencia_clase = %s
        """, (
            id_asistencia_clase,
        ))


        registro = (
            cursor.fetchone()
        )


        if registro is None:

            return redirect(
                url_for(
                    "asistencia"
                )
            )


        cursor.execute("""
            UPDATE asistencia_clases

            SET
                observacion = %s,
                id_usuario_registro = %s

            WHERE
                id_asistencia_clase = %s
        """, (
            observacion,
            session.get(
                "id_usuario"
            ),
            id_asistencia_clase
        ))


        conexion.commit()


        return redirect(
            url_for(
                "asistencia",
                id_horario=
                    registro[
                        "id_horario_academico"
                    ]
            )
        )


    except Exception as error:

        conexion.rollback()

        return (
            f"Error al guardar observación: "
            f"{error}"
        )


    finally:

        cursor.close()
        conexion.close()


# =========================================================
# CERRAR ASISTENCIA DE UNA CLASE
# =========================================================

@app.route(
    "/asistencia/cerrar/<int:id_horario>",
    methods=[
        "GET",
        "POST"
    ]
)
@login_requerido
def cerrar_asistencia(
    id_horario
):

    conexion = conectar()

    if conexion is None:
        return "Error al conectar con MySQL"


    cursor = conexion.cursor()


    try:

        cursor.execute("""
            UPDATE horario_academico

            SET
                estado =
                    'FINALIZADA',

                fecha_cierre_asistencia =
                    NOW(),

                id_usuario_cierre =
                    %s

            WHERE
                id_horario_academico = %s
        """, (
            session.get(
                "id_usuario"
            ),
            id_horario
        ))


        conexion.commit()


        return redirect(
            url_for(
                "asistencia",
                id_horario=
                    id_horario
            )
        )


    except Exception as error:

        conexion.rollback()

        return (
            f"Error al cerrar asistencia: "
            f"{error}"
        )


    finally:

        cursor.close()
        conexion.close()


# =========================================================
# HISTORIAL ACADÉMICO
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


    materia = request.args.get(
        "materia",
        ""
    ).strip()


    conexion = conectar()

    if conexion is None:
        return "Error al conectar con MySQL"


    cursor = conexion.cursor(
        dictionary=True
    )


    try:

        consulta = """
            SELECT
                ac.id_asistencia_clase,
                ac.fecha,
                ac.estado_asistencia,
                ac.horas_programadas,
                ac.horas_asistidas,
                ac.observacion,

                a.id_alumno,
                a.numero_lista,
                a.cedula,
                a.nombres,
                a.apellidos,
                a.especialidad,
                a.estado
                    AS estado_alumno,

                h.id_horario_academico,
                h.hora_inicio,
                h.hora_fin,
                h.docente,
                h.lugar,

                m.id_materia,
                m.nombre
                    AS materia,
                m.codigo

            FROM asistencia_clases ac

            INNER JOIN alumnos a
                ON ac.id_alumno =
                   a.id_alumno

            INNER JOIN horario_academico h
                ON ac.id_horario_academico =
                   h.id_horario_academico

            INNER JOIN materias m
                ON h.id_materia =
                   m.id_materia

            WHERE 1 = 1
        """


        parametros = []


        if buscar:

            consulta += """
                AND (
                    a.cedula LIKE %s
                    OR a.nombres LIKE %s
                    OR a.apellidos LIKE %s
                    OR CAST(
                        a.numero_lista AS CHAR
                    ) LIKE %s
                )
            """

            parametros.extend([
                f"%{buscar}%",
                f"%{buscar}%",
                f"%{buscar}%",
                f"%{buscar}%"
            ])


        if fecha:

            consulta += """
                AND ac.fecha = %s
            """

            parametros.append(
                fecha
            )


        if estado in [
            "ASISTE",
            "NO_ASISTE",
            "JUSTIFICADO"
        ]:

            consulta += """
                AND ac.estado_asistencia = %s
            """

            parametros.append(
                estado
            )


        if materia:

            consulta += """
                AND CAST(
                    m.id_materia AS CHAR
                ) = %s
            """

            parametros.append(
                materia
            )


        consulta += """
            ORDER BY
                ac.fecha DESC,
                h.hora_inicio DESC,
                a.numero_lista IS NULL,
                a.numero_lista ASC
        """


        cursor.execute(
            consulta,
            tuple(parametros)
        )


        registros = (
            cursor.fetchall()
        )


        total_registros = len(
            registros
        )


        asisten = sum(
            1
            for r in registros

            if (
                r["estado_asistencia"]
                == "ASISTE"
            )
        )


        no_asisten = sum(
            1
            for r in registros

            if (
                r["estado_asistencia"]
                == "NO_ASISTE"
            )
        )


        justificados = sum(
            1
            for r in registros

            if (
                r["estado_asistencia"]
                == "JUSTIFICADO"
            )
        )


        total_horas = sum(
            float(
                r[
                    "horas_asistidas"
                ]
                or 0
            )
            for r in registros
        )


        cursor.execute("""
            SELECT
                id_materia,
                nombre

            FROM materias

            WHERE estado =
                'ACTIVO'

            ORDER BY
                nombre ASC
        """)


        lista_materias = (
            cursor.fetchall()
        )


        return render_template(
            "historial.html",

            registros=
                registros,

            buscar=
                buscar,

            fecha=
                fecha,

            estado=
                estado,

            materia=
                materia,

            materias=
                lista_materias,

            total_registros=
                total_registros,

            puntuales=
                asisten,

            atrasados=
                no_asisten,

            ausentes=
                no_asisten,

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
# REPORTES ACADÉMICOS
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
        return "Error al conectar con MySQL"


    cursor = conexion.cursor(
        dictionary=True
    )


    try:

        consulta = """
            SELECT
                ac.id_asistencia_clase,
                ac.fecha,
                ac.estado_asistencia,
                ac.horas_programadas,
                ac.horas_asistidas,
                ac.observacion,

                a.id_alumno,
                a.numero_lista,
                a.cedula,
                a.nombres,
                a.apellidos,
                a.especialidad,
                a.estado
                    AS estado_alumno,

                h.hora_inicio,
                h.hora_fin,
                h.docente,
                h.lugar,

                m.nombre
                    AS materia

            FROM asistencia_clases ac

            INNER JOIN alumnos a
                ON ac.id_alumno =
                   a.id_alumno

            INNER JOIN horario_academico h
                ON ac.id_horario_academico =
                   h.id_horario_academico

            INNER JOIN materias m
                ON h.id_materia =
                   m.id_materia

            WHERE
                m.contabiliza_asistencia =
                    TRUE
        """


        parametros = []


        if buscar:

            consulta += """
                AND (
                    a.cedula LIKE %s
                    OR a.nombres LIKE %s
                    OR a.apellidos LIKE %s
                    OR m.nombre LIKE %s
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
                AND ac.fecha >= %s
            """

            parametros.append(
                fecha_inicio
            )


        if fecha_fin:

            consulta += """
                AND ac.fecha <= %s
            """

            parametros.append(
                fecha_fin
            )


        if estado in [
            "ASISTE",
            "NO_ASISTE",
            "JUSTIFICADO"
        ]:

            consulta += """
                AND ac.estado_asistencia = %s
            """

            parametros.append(
                estado
            )


        consulta += """
            ORDER BY
                ac.fecha DESC,
                h.hora_inicio DESC,
                a.numero_lista IS NULL,
                a.numero_lista ASC
        """


        cursor.execute(
            consulta,
            tuple(parametros)
        )


        registros = (
            cursor.fetchall()
        )


        total_registros = len(
            registros
        )


        puntuales = sum(
            1
            for r in registros

            if (
                r["estado_asistencia"]
                == "ASISTE"
            )
        )


        ausentes = sum(
            1
            for r in registros

            if (
                r["estado_asistencia"]
                == "NO_ASISTE"
            )
        )


        justificados = sum(
            1
            for r in registros

            if (
                r["estado_asistencia"]
                == "JUSTIFICADO"
            )
        )


        total_horas = sum(
            float(
                r[
                    "horas_asistidas"
                ]
                or 0
            )
            for r in registros
        )


        horas_programadas = sum(
            float(
                r[
                    "horas_programadas"
                ]
                or 0
            )
            for r in registros
        )


        if horas_programadas > 0:

            porcentaje_puntualidad = round(
                (
                    total_horas
                    /
                    horas_programadas
                )
                * 100,
                2
            )

        else:

            porcentaje_puntualidad = 0


        alumnos_reportados = len({
            r["id_alumno"]
            for r in registros
        })


        return render_template(
            "reportes.html",

            registros=
                registros,

            buscar=
                buscar,

            fecha_inicio=
                fecha_inicio,

            fecha_fin=
                fecha_fin,

            estado=
                estado,

            total_registros=
                total_registros,

            puntuales=
                puntuales,

            atrasados=0,

            ausentes=
                ausentes,

            justificados=
                justificados,

            incompletos=0,

            total_horas=
                round(
                    total_horas,
                    2
                ),

            horas_programadas=
                round(
                    horas_programadas,
                    2
                ),

            total_atraso=0,

            alumnos_reportados=
                alumnos_reportados,

            porcentaje_puntualidad=
                porcentaje_puntualidad
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
        return "Error al conectar con MySQL"


    cursor = conexion.cursor(
        dictionary=True
    )


    try:

        # =================================================
        # CLASE ACTUAL
        # =================================================

        cursor.execute("""
            SELECT
                h.*,
                m.nombre AS materia

            FROM horario_academico h

            INNER JOIN materias m
                ON h.id_materia =
                   m.id_materia

            WHERE h.fecha = CURDATE()

            AND CURTIME() >=
                h.hora_inicio

            AND CURTIME() <
                h.hora_fin

            AND h.estado <>
                'CANCELADA'

            LIMIT 1
        """)


        horario_activo = (
            cursor.fetchone()
        )


        # =================================================
        # TOTAL ALUMNOS
        # =================================================

        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM alumnos
        """)


        total_alumnos = (
            cursor.fetchone()["total"]
        )


        # =================================================
        # DISPONIBLES
        # =================================================

        cursor.execute("""
            SELECT COUNT(*) AS total

            FROM alumnos

            WHERE estado =
                'DISPONIBLE'
        """)


        disponibles = (
            cursor.fetchone()["total"]
        )


        # =================================================
        # DESCANSO MÉDICO
        # =================================================

        cursor.execute("""
            SELECT COUNT(*) AS total

            FROM alumnos

            WHERE estado =
                'DESCANSO MÉDICO'
        """)


        descanso_medico = (
            cursor.fetchone()["total"]
        )


        # =================================================
        # USUARIOS
        # =================================================

        cursor.execute("""
            SELECT COUNT(*) AS total

            FROM usuarios

            WHERE estado =
                'ACTIVO'
        """)


        usuarios_activos = (
            cursor.fetchone()["total"]
        )


        # =================================================
        # MATERIAS
        # =================================================

        cursor.execute("""
            SELECT COUNT(*) AS total

            FROM materias

            WHERE estado =
                'ACTIVO'
        """)


        total_materias = (
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
                usuarios_activos,

            total_materias=
                total_materias
        )


    except Exception as error:

        return (
            "Error al cargar configuración: "
            f"{error}"
        )


    finally:

        cursor.close()
        conexion.close()


# =========================================================
# EJECUTAR LOCALMENTE
# =========================================================

if __name__ == "__main__":

    crear_admin_inicial()

    app.run(
        debug=True,
        host="0.0.0.0",
        port=5000
    )