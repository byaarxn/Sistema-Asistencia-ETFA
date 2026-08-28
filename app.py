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

import os
import re
import unicodedata
from difflib import SequenceMatcher

from werkzeug.utils import secure_filename
import pdfplumber

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
# CONFIGURACIÓN PARA SUBIR HORARIOS PDF
# =========================================================

UPLOAD_FOLDER = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "static",
    "uploads",
    "horarios"
)

ALLOWED_EXTENSIONS = {
    "pdf"
}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# Máximo 10 MB por archivo PDF
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

os.makedirs(
    UPLOAD_FOLDER,
    exist_ok=True
)


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
# VALIDAR ARCHIVO PDF
# =========================================================

def archivo_pdf_permitido(nombre_archivo):

    return (
        "." in nombre_archivo
        and nombre_archivo.rsplit(".", 1)[1].lower()
        in ALLOWED_EXTENSIONS
    )


# =========================================================
# FUNCIONES AUXILIARES PARA DETECTAR HORARIOS EN PDF
# =========================================================

def normalizar_texto_pdf(valor):

    valor = valor or ""

    valor = unicodedata.normalize(
        "NFD",
        valor
    )

    valor = "".join(
        caracter
        for caracter in valor
        if unicodedata.category(caracter) != "Mn"
    )

    valor = valor.upper()

    valor = re.sub(
        r"[^A-Z0-9:/().+\- ]+",
        " ",
        valor
    )

    valor = re.sub(
        r"\s+",
        " ",
        valor
    ).strip()

    return valor


def convertir_fecha_etfa(valor):

    meses = {
        "ene": 1,
        "feb": 2,
        "mar": 3,
        "abr": 4,
        "may": 5,
        "jun": 6,
        "jul": 7,
        "ago": 8,
        "sep": 9,
        "sept": 9,
        "oct": 10,
        "nov": 11,
        "dic": 12,
    }

    valor = (valor or "").strip()

    coincidencia = re.search(
        r"(\d{1,2})-([A-Za-zÁÉÍÓÚáéíóúÑñ]{3,10})-(\d{2,4})",
        valor,
        flags=re.IGNORECASE
    )

    if not coincidencia:
        return None

    dia = int(coincidencia.group(1))

    mes_texto = normalizar_texto_pdf(
        coincidencia.group(2)
    ).lower()

    anio = int(coincidencia.group(3))

    if anio < 100:
        anio += 2000

    # El horario ETFA usa "sept".
    if mes_texto.startswith("sept"):
        mes_texto = "sept"
    else:
        mes_texto = mes_texto[:3]

    mes = meses.get(mes_texto)

    if mes is None:
        return None

    try:
        return date(anio, mes, dia)

    except ValueError:
        return None


def dia_semana_espanol(fecha_valor):

    dias = [
        "LUNES",
        "MARTES",
        "MIÉRCOLES",
        "JUEVES",
        "VIERNES",
        "SÁBADO",
        "DOMINGO",
    ]

    return dias[
        fecha_valor.weekday()
    ]


def detectar_lugar_etfa(texto):

    lugares = [
        "AULA/TALLER ETFA",
        "INSTALACIONES ETFA",
        "CAMPO MARTE",
        "AULAS ETFA",
        "COMEDOR",
        "AUDITORIO",
        "LABORATORIO",
        "ETFA",
    ]

    texto_normalizado = normalizar_texto_pdf(
        texto
    )

    for lugar in lugares:

        if normalizar_texto_pdf(lugar) in texto_normalizado:
            return lugar

    return ""


def detectar_docente_etfa(texto):

    texto = re.sub(
        r"\s+",
        " ",
        texto or ""
    ).strip()

    patrones = [
        r"INSTRUCTOR DE GUARDIA",
        r"(?:ING\.?|FIS\.?|MGTR\.?|TNTE\.?|CAPT\.?|SGOS\.?|SGOP\.?|CBOS\.?|SUBS\.?|MAYO\.?|TCRN\.?|CRNL\.?)\s+[A-ZÁÉÍÓÚÑ. ]{4,80}",
    ]

    for patron in patrones:

        coincidencia = re.search(
            patron,
            texto,
            flags=re.IGNORECASE
        )

        if coincidencia:

            docente = coincidencia.group(0).strip()

            for corte in [
                " AULAS ETFA",
                " INSTALACIONES ETFA",
                " AULA/TALLER ETFA",
                " CAMPO MARTE",
                " COMEDOR",
            ]:

                posicion = docente.upper().find(
                    corte
                )

                if posicion >= 0:
                    docente = docente[:posicion].strip()

            return docente

    return ""


def buscar_materia_en_texto(
    texto,
    materias_disponibles
):

    texto_normalizado = normalizar_texto_pdf(
        texto
    )

    mejor = None
    mejor_puntaje = 0

    # Primero intentamos coincidencia directa.
    for materia in materias_disponibles:

        nombre = materia.get("nombre") or ""

        nombre_normalizado = normalizar_texto_pdf(
            nombre
        )

        if not nombre_normalizado:
            continue

        if nombre_normalizado in texto_normalizado:

            puntaje = min(
                100,
                90 + min(len(nombre_normalizado) // 10, 10)
            )

            if puntaje > mejor_puntaje:
                mejor = materia
                mejor_puntaje = puntaje

    if mejor is not None:
        return mejor, mejor_puntaje

    # Si el PDF corta el nombre entre líneas, usamos similitud.
    for materia in materias_disponibles:

        nombre = materia.get("nombre") or ""
        nombre_normalizado = normalizar_texto_pdf(nombre)

        if len(nombre_normalizado) < 4:
            continue

        proporcion = SequenceMatcher(
            None,
            nombre_normalizado,
            texto_normalizado
        ).ratio()

        puntaje = round(
            proporcion * 100
        )

        if puntaje > mejor_puntaje:
            mejor = materia
            mejor_puntaje = puntaje

    if mejor_puntaje >= 48:
        return mejor, mejor_puntaje

    return None, mejor_puntaje


def detectar_actividad_generica(texto):

    actividades = [
        "REGIMEN INTERNO / INSTRUCCIÓN MILITAR",
        "RÉGIMEN INTERNO / INSTRUCCIÓN MILITAR",
        "ENTRENAMIENTO FÍSICO MILITAR III",
        "ACONDICIONAMIENTO FÍSICO MILITAR 3",
        "TRABAJO AUTÓNOMO",
        "ACTO CÍVICO",
        "RECESO/ BREAK -1",
        "RECESO",
        "DESAYUNO",
        "ALMUERZO",
        "MERIENDA",
        "EXAMEN MEDIA CARRERA",
        "EXAMEN TEÓRICO PRÁCTICO INTERMEDIO",
    ]

    texto_normalizado = normalizar_texto_pdf(
        texto
    )

    for actividad in actividades:

        if normalizar_texto_pdf(actividad) in texto_normalizado:
            return actividad

    return "ACTIVIDAD POR REVISAR"


def limpiar_celda_pdf(valor):
    if valor is None:
        return ""

    return re.sub(
        r"\s+",
        " ",
        str(valor)
    ).strip()


def limpiar_nombre_asignatura_etfa(nombre):
    nombre = limpiar_celda_pdf(nombre)

    # Quita prefijos tipo 3.C., 4.C., 7.B., 1.C, etc.
    nombre = re.sub(
        r"^\s*\d+\s*\.\s*[A-Z]\.?\s*",
        "",
        nombre,
        flags=re.IGNORECASE
    )

    # Quita el marcador final (C), (B), etc., si pertenece al código.
    nombre = re.sub(
        r"\s+\([A-Z]\)\s*$",
        "",
        nombre,
        flags=re.IGNORECASE
    )

    return nombre.strip()


def obtener_fecha_desde_fila_etfa(celdas):
    """
    Busca una fecha ETFA en cualquier columna de una fila.
    Esto permite trabajar con PDFs donde la columna FECHA se desplaza
    o donde existen celdas combinadas.
    """
    patron = re.compile(
        r"\b\d{1,2}-[A-Za-zÁÉÍÓÚáéíóú]{3}-\d{2,4}\b"
    )

    for celda in celdas:
        coincidencia = patron.search(
            celda or ""
        )

        if coincidencia:
            return coincidencia.group(0)

    return ""


def obtener_dia_desde_fila_etfa(celdas):
    dias = [
        "LUNES",
        "MARTES",
        "MIÉRCOLES",
        "MIERCOLES",
        "JUEVES",
        "VIERNES",
        "SÁBADO",
        "SABADO",
        "DOMINGO",
    ]

    texto = " ".join(
        celdas
    ).upper()

    for dia in dias:
        if dia in texto:
            if dia == "MIERCOLES":
                return "MIÉRCOLES"
            if dia == "SABADO":
                return "SÁBADO"
            return dia

    return ""


def obtener_horas_desde_fila_etfa(celdas):
    """
    Busca horas válidas en las celdas de la fila y devuelve
    las dos primeras horas diferentes que correspondan a inicio/fin.
    """
    patron = re.compile(
        r"^(?:[01]?\d|2[0-3]):[0-5]\d$"
    )

    horas = []

    for celda in celdas:
        valor = limpiar_celda_pdf(
            celda
        )

        if patron.match(valor):
            horas.append(valor)

    if len(horas) >= 2:
        return horas[0], horas[1]

    return None, None


def detectar_bloques_horario_etfa(
    paginas,
    materias_disponibles
):

    bloques = []
    claves_vistas = set()

    patron_hora = re.compile(
        r"^(?:[01]?\d|2[0-3]):[0-5]\d$"
    )

    for pagina in paginas:

        numero_pagina = pagina.get("numero")

        filas_tabla = pagina.get(
            "filas_tabla",
            []
        ) or []

        for fila in filas_tabla:

            if not fila:
                continue

            celdas = [
                limpiar_celda_pdf(celda)
                for celda in fila
            ]

            # El formato oficial ETFA tiene 10 columnas.
            if len(celdas) < 10:
                continue

            fecha_pdf = celdas[1]
            hora_inicio = celdas[2]
            hora_fin = celdas[3]

            # No usamos fecha heredada de otra fila.
            fecha_clase = convertir_fecha_etfa(
                fecha_pdf
            )

            if fecha_clase is None:
                continue

            if not patron_hora.fullmatch(hora_inicio):
                continue

            if not patron_hora.fullmatch(hora_fin):
                continue

            try:
                inicio_t = datetime.strptime(
                    hora_inicio,
                    "%H:%M"
                ).time()

                fin_t = datetime.strptime(
                    hora_fin,
                    "%H:%M"
                ).time()

            except ValueError:
                continue

            horas_clase = calcular_horas_bloque(
                inicio_t,
                fin_t
            )

            if horas_clase <= 0 or horas_clase > 6:
                continue

            horas_programadas_pdf = celdas[4]
            numero_hora = celdas[5]
            horas_pdf = celdas[6]

            asignatura_pdf = celdas[7]
            docente_pdf = celdas[8]
            lugar_pdf = celdas[9]

            asignatura_limpia = limpiar_nombre_asignatura_etfa(
                asignatura_pdf
            )

            if not asignatura_limpia:
                continue

            docente = re.sub(
                r"^\s*\([A-Z]\)\s*",
                "",
                docente_pdf,
                flags=re.IGNORECASE
            ).strip()

            lugar = lugar_pdf.strip()

            dia_semana = dia_semana_espanol(
                fecha_clase
            )

            texto_busqueda = " ".join([
                asignatura_limpia,
                docente,
                lugar
            ]).strip()

            materia, confianza = buscar_materia_en_texto(
                texto_busqueda,
                materias_disponibles
            )

            if materia:

                id_materia = materia.get("id_materia")
                materia_nombre = materia.get("nombre")
                tipo = materia.get("tipo", "MATERIA")

                contabiliza = bool(
                    materia.get(
                        "contabiliza_asistencia"
                    )
                )

            else:

                actividad = detectar_actividad_generica(
                    asignatura_limpia
                )

                if actividad != "ACTIVIDAD POR REVISAR":
                    materia_nombre = actividad
                    confianza = max(confianza, 90)

                else:
                    materia_nombre = asignatura_limpia
                    confianza = max(confianza, 55)

                id_materia = None
                tipo = "OTRO"
                contabiliza = False

            clave = (
                fecha_clase.isoformat(),
                hora_inicio,
                hora_fin,
                normalizar_texto_pdf(
                    asignatura_limpia
                )
            )

            if clave in claves_vistas:
                continue

            claves_vistas.add(clave)

            actividad_reconocida = detectar_actividad_generica(
                asignatura_limpia
            )

            requiere_revision = (
                (
                    id_materia is None
                    and actividad_reconocida
                    == "ACTIVIDAD POR REVISAR"
                )
                or confianza < 60
            )

            bloques.append({
                "pagina": numero_pagina,
                "fecha": fecha_clase.isoformat(),
                "dia_semana": dia_semana,
                "hora_inicio": hora_inicio,
                "hora_fin": hora_fin,
                "horas_clase": horas_clase,
                "numero_hora": numero_hora or None,
                "horas_pdf": horas_pdf or None,
                "horas_programadas_pdf":
                    horas_programadas_pdf or None,
                "id_materia": id_materia,
                "materia": materia_nombre,
                "materia_pdf": asignatura_limpia,
                "tipo": tipo,
                "contabiliza_asistencia": contabiliza,
                "docente": docente,
                "lugar": lugar,
                "confianza": confianza,
                "requiere_revision":
                    requiere_revision,
                "texto_origen": " | ".join([
                    fecha_pdf,
                    hora_inicio,
                    hora_fin,
                    asignatura_limpia,
                    docente,
                    lugar
                ])
            })

    bloques.sort(
        key=lambda bloque: (
            bloque["fecha"],
            datetime.strptime(
                bloque["hora_inicio"],
                "%H:%M"
            ).time()
        )
    )

    print("=" * 60)
    print("RESULTADO LECTOR PDF ETFA")
    print("Páginas:", len(paginas))
    print("Bloques:", len(bloques))

    resumen = {}

    for bloque in bloques:
        resumen[bloque["fecha"]] = (
            resumen.get(bloque["fecha"], 0) + 1
        )

    for fecha, total in sorted(resumen.items()):
        print(fecha, "=>", total)

    print("=" * 60)

    return bloques


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
# FUNCIONES AUXILIARES - IMPORTACIÓN DEFINITIVA DE HORARIO
# =========================================================

def extraer_paginas_horario_pdf(ruta_pdf):
    """
    Extrae texto y tablas de todas las páginas del PDF ETFA.
    Devuelve:
        paginas_detectadas, total_paginas
    """

    paginas_detectadas = []

    with pdfplumber.open(ruta_pdf) as pdf:

        total_paginas = len(pdf.pages)

        for numero, pagina in enumerate(
            pdf.pages,
            start=1
        ):

            texto_pagina = pagina.extract_text(
                x_tolerance=2,
                y_tolerance=2
            ) or ""

            configuracion_lineas = {
                "vertical_strategy": "lines",
                "horizontal_strategy": "lines",
                "intersection_tolerance": 5,
                "snap_tolerance": 3,
                "join_tolerance": 3,
                "edge_min_length": 3,
                "min_words_vertical": 1,
                "min_words_horizontal": 1,
            }

            tablas = pagina.extract_tables(
                configuracion_lineas
            ) or []

            if not tablas:

                configuracion_texto = {
                    "vertical_strategy": "text",
                    "horizontal_strategy": "text",
                    "intersection_tolerance": 5,
                    "snap_tolerance": 3,
                    "join_tolerance": 3,
                    "min_words_vertical": 1,
                    "min_words_horizontal": 1,
                }

                tablas = pagina.extract_tables(
                    configuracion_texto
                ) or []

            filas_tabla = []

            for tabla in tablas:

                for fila in tabla or []:

                    if fila:
                        filas_tabla.append(
                            fila
                        )

            paginas_detectadas.append({
                "numero": numero,
                "texto": texto_pagina.strip(),
                "filas_tabla": filas_tabla,
                "cantidad_filas": len(
                    filas_tabla
                )
            })

    return (
        paginas_detectadas,
        total_paginas
    )


def clasificar_materia_importada(nombre):
    """
    Determina el tipo y si una actividad debe contabilizar asistencia
    cuando todavía no existe en la tabla materias.
    """

    nombre_normalizado = normalizar_texto_pdf(
        nombre
    )

    if (
        "RECESO" in nombre_normalizado
        or "BREAK" in nombre_normalizado
    ):

        return (
            "RECESO",
            False
        )

    if any(
        palabra in nombre_normalizado
        for palabra in [
            "DESAYUNO",
            "ALMUERZO",
            "MERIENDA"
        ]
    ):

        return (
            "ALIMENTACION",
            False
        )

    if (
        "REGIMEN INTERNO" in nombre_normalizado
        or "INSTRUCCION MILITAR" in nombre_normalizado
    ):

        return (
            "REGIMEN_INTERNO",
            True
        )

    if (
        "ENTRENAMIENTO FISICO" in nombre_normalizado
        or "ACONDICIONAMIENTO FISICO" in nombre_normalizado
    ):

        return (
            "ENTRENAMIENTO_FISICO",
            True
        )

    if "TRABAJO AUTONOMO" in nombre_normalizado:

        return (
            "TRABAJO_AUTONOMO",
            True
        )

    if "ACTO CIVICO" in nombre_normalizado:

        return (
            "ACTO_CIVICO",
            True
        )

    if (
        "EXAMEN" in nombre_normalizado
        or "VERIFICADOR" in nombre_normalizado
    ):

        return (
            "EXAMEN",
            True
        )

    return (
        "MATERIA",
        True
    )


def obtener_o_crear_materia_importacion(
    cursor,
    bloque,
    materias_cache
):
    """
    Devuelve:
        id_materia,
        contabiliza_asistencia,
        creada
    """

    id_materia = bloque.get(
        "id_materia"
    )

    if id_materia:

        for materia in materias_cache:

            if (
                materia.get("id_materia")
                == id_materia
            ):

                return (
                    id_materia,
                    bool(
                        materia.get(
                            "contabiliza_asistencia"
                        )
                    ),
                    False
                )

        return (
            id_materia,
            bool(
                bloque.get(
                    "contabiliza_asistencia"
                )
            ),
            False
        )

    nombre = (
        bloque.get("materia")
        or bloque.get("materia_pdf")
        or "ACTIVIDAD ETFA"
    ).strip()

    nombre_normalizado = normalizar_texto_pdf(
        nombre
    )

    # Buscar nuevamente en el cache por nombre normalizado.
    for materia in materias_cache:

        if (
            normalizar_texto_pdf(
                materia.get("nombre")
            )
            == nombre_normalizado
        ):

            return (
                materia["id_materia"],
                bool(
                    materia.get(
                        "contabiliza_asistencia"
                    )
                ),
                False
            )

    # Buscar en MySQL por si fue creada por otra importación.
    cursor.execute("""
        SELECT
            id_materia,
            codigo,
            nombre,
            tipo,
            contabiliza_asistencia,
            estado

        FROM materias

        WHERE UPPER(nombre) = UPPER(%s)

        LIMIT 1
    """, (
        nombre,
    ))

    existente = cursor.fetchone()

    if existente:

        materias_cache.append(
            existente
        )

        return (
            existente["id_materia"],
            bool(
                existente[
                    "contabiliza_asistencia"
                ]
            ),
            False
        )

    tipo, contabiliza = (
        clasificar_materia_importada(
            nombre
        )
    )

    cursor.execute("""
        INSERT INTO materias (
            codigo,
            nombre,
            tipo,
            contabiliza_asistencia,
            estado
        )

        VALUES (
            NULL,
            %s,
            %s,
            %s,
            'ACTIVO'
        )
    """, (
        nombre,
        tipo,
        contabiliza
    ))

    nuevo_id = cursor.lastrowid

    nueva_materia = {
        "id_materia": nuevo_id,
        "codigo": None,
        "nombre": nombre,
        "tipo": tipo,
        "contabiliza_asistencia":
            contabiliza,
        "estado": "ACTIVO"
    }

    materias_cache.append(
        nueva_materia
    )

    return (
        nuevo_id,
        contabiliza,
        True
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
# IMPORTAR Y LEER HORARIO DESDE PDF
# =========================================================

@app.route(
    "/horarios/importar",
    methods=["GET", "POST"]
)
@login_requerido
@administrador_requerido
def importar_horario():

    if request.method == "POST":

        if "archivo_pdf" not in request.files:

            return render_template(
                "importar_horario.html",
                error="Debe seleccionar un archivo PDF."
            )

        archivo = request.files["archivo_pdf"]

        if archivo.filename == "":

            return render_template(
                "importar_horario.html",
                error="No se seleccionó ningún archivo."
            )

        if not archivo_pdf_permitido(
            archivo.filename
        ):

            return render_template(
                "importar_horario.html",
                error="Solo se permiten archivos PDF."
            )

        nombre_original = secure_filename(
            archivo.filename
        )

        fecha_archivo = datetime.now().strftime(
            "%Y%m%d_%H%M%S_%f"
        )

        nombre_guardado = (
            f"{fecha_archivo}_{nombre_original}"
        )

        ruta_guardado = os.path.join(
            app.config["UPLOAD_FOLDER"],
            nombre_guardado
        )

        conexion = None
        cursor = None

        try:

            # =============================================
            # GUARDAR Y VALIDAR EL PDF
            # =============================================

            archivo.save(
                ruta_guardado
            )

            with open(
                ruta_guardado,
                "rb"
            ) as archivo_validacion:

                encabezado = archivo_validacion.read(5)

            if encabezado != b"%PDF-":

                if os.path.exists(ruta_guardado):
                    os.remove(ruta_guardado)

                return render_template(
                    "importar_horario.html",
                    error=(
                        "El archivo seleccionado no parece "
                        "ser un documento PDF válido."
                    )
                )

            # =============================================
            # EXTRAER TODAS LAS PÁGINAS Y TABLAS
            # =============================================

            (
                paginas_detectadas,
                total_paginas
            ) = extraer_paginas_horario_pdf(
                ruta_guardado
            )

            contenido_detectado = "\n\n".join(
                pagina["texto"]
                for pagina in paginas_detectadas
                if pagina["texto"]
            ).strip()

            if not contenido_detectado:

                return render_template(
                    "revisar_horario_pdf.html",
                    nombre_archivo=nombre_original,
                    nombre_guardado=nombre_guardado,
                    total_paginas=total_paginas,
                    paginas=paginas_detectadas,
                    texto_detectado=False,
                    advertencia=(
                        "El PDF fue cargado correctamente, "
                        "pero no contiene texto extraíble."
                    )
                )

            # =============================================
            # CARGAR MATERIAS EXISTENTES EN MYSQL
            # =============================================

            conexion = conectar()

            if conexion is None:
                return "Error al conectar con MySQL"

            cursor = conexion.cursor(
                dictionary=True
            )

            cursor.execute("""
                SELECT
                    id_materia,
                    codigo,
                    nombre,
                    tipo,
                    contabiliza_asistencia,
                    estado
                FROM materias
                WHERE estado = 'ACTIVO'
                ORDER BY nombre ASC
            """)

            materias_disponibles = cursor.fetchall()

            # =============================================
            # DETECTAR BLOQUES AUTOMÁTICAMENTE
            # =============================================

            bloques_detectados = detectar_bloques_horario_etfa(
                paginas_detectadas,
                materias_disponibles
            )

            bloques_revision = sum(
                1
                for bloque in bloques_detectados
                if bloque["requiere_revision"]
            )

            bloques_listos = (
                len(bloques_detectados)
                - bloques_revision
            )

            # Guardamos únicamente el nombre temporal.
            # Los bloques todavía NO se insertan en MySQL.
            session["ultimo_pdf_horario"] = nombre_guardado
            session["ultimo_pdf_horario_original"] = nombre_original

            return render_template(
                "previsualizar_horario.html",
                nombre_archivo=nombre_original,
                nombre_guardado=nombre_guardado,
                total_paginas=total_paginas,
                bloques=bloques_detectados,
                total_bloques=len(bloques_detectados),
                bloques_listos=bloques_listos,
                bloques_revision=bloques_revision,
                materias=materias_disponibles
            )

        except Exception as error:

            print(
                "ERROR ANALIZANDO HORARIO PDF:",
                error
            )

            return render_template(
                "importar_horario.html",
                error=(
                    "No se pudo analizar el PDF. "
                    f"Detalle: {error}"
                )
            )

        finally:

            if cursor is not None:
                cursor.close()

            if conexion is not None:
                conexion.close()

    return render_template(
        "importar_horario.html"
    )


# =========================================================
# CONFIRMAR E IMPORTAR HORARIO PDF
# =========================================================

@app.route(
    "/horarios/importar/confirmar",
    methods=["POST"]
)
@login_requerido
@administrador_requerido
def confirmar_importacion_horario():

    nombre_guardado = session.get(
        "ultimo_pdf_horario"
    )

    nombre_original = session.get(
        "ultimo_pdf_horario_original",
        nombre_guardado
    )

    if not nombre_guardado:

        return redirect(
            url_for(
                "importar_horario"
            )
        )

    ruta_pdf = os.path.join(
        app.config["UPLOAD_FOLDER"],
        nombre_guardado
    )

    if not os.path.exists(
        ruta_pdf
    ):

        return render_template(
            "resultado_importacion_horario.html",
            exito=False,
            mensaje=(
                "El archivo temporal ya no existe. "
                "Vuelva a cargar el PDF."
            ),
            importados=0,
            omitidos=0,
            materias_creadas=0,
            asistencias_generadas=0,
            nombre_archivo=nombre_original
        )

    conexion = conectar()

    if conexion is None:

        return (
            "Error al conectar con MySQL"
        )

    cursor = conexion.cursor(
        dictionary=True
    )

    importados = 0
    omitidos = 0
    materias_creadas = 0
    asistencias_generadas = 0

    try:

        # =================================================
        # VOLVER A LEER EL PDF DESDE EL ARCHIVO TEMPORAL
        # =================================================

        (
            paginas_detectadas,
            total_paginas
        ) = extraer_paginas_horario_pdf(
            ruta_pdf
        )

        # =================================================
        # CARGAR MATERIAS ACTUALES
        # =================================================

        cursor.execute("""
            SELECT
                id_materia,
                codigo,
                nombre,
                tipo,
                contabiliza_asistencia,
                estado

            FROM materias

            WHERE estado = 'ACTIVO'

            ORDER BY nombre ASC
        """)

        materias_cache = cursor.fetchall()

        # =================================================
        # DETECTAR LOS BLOQUES OTRA VEZ
        # =================================================

        bloques = detectar_bloques_horario_etfa(
            paginas_detectadas,
            materias_cache
        )

        if not bloques:

            raise ValueError(
                "No se detectaron bloques válidos "
                "en el documento."
            )

        # =================================================
        # IMPORTAR BLOQUE POR BLOQUE
        # =================================================

        for bloque in bloques:

            fecha = bloque["fecha"]
            hora_inicio = bloque["hora_inicio"]
            hora_fin = bloque["hora_fin"]

            curso = "Primer Año Militar"
            paralelo = "C"

            # =============================================
            # EVITAR DUPLICADOS
            # =============================================

            cursor.execute("""
                SELECT
                    id_horario_academico

                FROM horario_academico

                WHERE fecha = %s
                  AND hora_inicio = %s
                  AND hora_fin = %s
                  AND curso = %s
                  AND paralelo = %s

                LIMIT 1
            """, (
                fecha,
                hora_inicio,
                hora_fin,
                curso,
                paralelo
            ))

            existente = cursor.fetchone()

            if existente:

                omitidos += 1
                continue

            # =============================================
            # RESOLVER / CREAR MATERIA
            # =============================================

            (
                id_materia,
                contabiliza_asistencia,
                materia_creada
            ) = obtener_o_crear_materia_importacion(
                cursor,
                bloque,
                materias_cache
            )

            if materia_creada:
                materias_creadas += 1

            # =============================================
            # INSERTAR HORARIO
            # =============================================

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
                    estado,
                    asistencia_generada
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
                    'PROGRAMADA',
                    %s
                )
            """, (
                fecha,
                bloque["dia_semana"],
                hora_inicio,
                hora_fin,
                id_materia,
                bloque.get("docente") or None,
                bloque.get("lugar") or None,
                bloque.get("numero_hora") or None,
                bloque["horas_clase"],
                curso,
                paralelo,
                bool(
                    contabiliza_asistencia
                )
            ))

            id_horario = cursor.lastrowid

            importados += 1

            # =============================================
            # GENERAR ASISTENCIA AUTOMÁTICA
            #
            # REGLA DEL SISTEMA:
            # TODOS COMIENZAN COMO ASISTE.
            # =============================================

            if contabiliza_asistencia:

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
                    id_horario,
                    fecha,
                    bloque["horas_clase"],
                    bloque["horas_clase"],
                    session.get(
                        "id_usuario"
                    )
                ))

                asistencias_generadas += (
                    cursor.rowcount
                    if cursor.rowcount
                    and cursor.rowcount > 0
                    else 0
                )

        # =================================================
        # TODO CORRECTO
        # =================================================

        conexion.commit()

        session.pop(
            "ultimo_pdf_horario",
            None
        )

        session.pop(
            "ultimo_pdf_horario_original",
            None
        )

        # El PDF ya cumplió su función.
        try:

            if os.path.exists(
                ruta_pdf
            ):

                os.remove(
                    ruta_pdf
                )

        except Exception:

            pass

        return render_template(
            "resultado_importacion_horario.html",
            exito=True,
            mensaje=(
                "El horario fue procesado "
                "correctamente."
            ),
            importados=importados,
            omitidos=omitidos,
            materias_creadas=
                materias_creadas,
            asistencias_generadas=
                asistencias_generadas,
            total_detectados=
                len(bloques),
            total_paginas=
                total_paginas,
            nombre_archivo=
                nombre_original
        )

    except Exception as error:

        conexion.rollback()

        print(
            "ERROR CONFIRMANDO IMPORTACIÓN:",
            error
        )

        return render_template(
            "resultado_importacion_horario.html",
            exito=False,
            mensaje=(
                "No se pudo importar el horario. "
                f"Detalle: {error}"
            ),
            importados=0,
            omitidos=0,
            materias_creadas=0,
            asistencias_generadas=0,
            total_detectados=0,
            nombre_archivo=
                nombre_original
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