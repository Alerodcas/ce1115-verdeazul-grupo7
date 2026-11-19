"""Nombres para mostrar, color de cada rol y el menú lateral.

ESTO ES NAVEGACIÓN, NO CONTROL DE ACCESO. Ocultar un enlace no protege nada
(Parte 1, «Dónde vive la decisión de autorización»). El menú agrupa primero lo
que la matriz le abre a cada rol y deja el resto visible más abajo, a propósito:
así se puede intentar y ver en pantalla qué regla del PEP lo niega.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Rol:
    valor: str  # ortografía exacta que espera la política
    nombre: str  # para mostrar
    clase: str  # sufijo de la clase CSS que fija el color del rol
    resumen: str  # qué hace en la matriz, en una línea


@dataclass(frozen=True)
class Pantalla:
    clave: str
    nombre: str
    objeto: str  # tipo de objeto de la matriz


PANTALLAS = {
    p.clave: p
    for p in (
        Pantalla("mediciones", "Mediciones", "Medicion"),
        Pantalla("fincas", "Fincas", "Finca"),
        Pantalla("periodos", "Períodos", "Periodo"),
        Pantalla("certificados", "Certificados", "Certificado"),
        Pantalla("enmiendas", "Enmiendas", "Enmienda"),
        Pantalla("cuentas", "Cuentas", "Cuenta"),
        Pantalla("bitacora", "Bitácora", "Bitacora"),
    )
}

_ROLES = (
    Rol("Tecnico de campo", "Técnico de campo", "tecnico",
        "Registra mediciones en las fincas que tiene asignadas y pide enmiendas."),
    Rol("Verificador", "Verificador", "verificador",
        "Aprueba o devuelve mediciones que no creó ni editó, y emite certificados."),
    Rol("Administrador", "Administrador", "administrador",
        "Da de alta fincas y ejecuta cambios de cuenta con solicitud escrita."),
    Rol("Auditor externo", "Auditor externo", "auditor",
        "Lee el registro completo y la bitácora. No modifica nada."),
    Rol("Dueno de finca", "Dueño de finca", "dueno",
        "Consulta las mediciones y certificados de sus propias fincas."),
    Rol("Gerencia de Certificacion", "Gerencia de Certificación", "gerencia",
        "Abre y cierra períodos, autoriza enmiendas y aprueba cambios de cuenta."),
)
ROL_POR_VALOR = {r.valor: r for r in _ROLES}  # las pruebas comprueban que coincide con ROLES

# Lo que la matriz le abre a cada rol, en el orden en que lo usa.
ALCANCE = {
    "Tecnico de campo": ("mediciones", "enmiendas", "fincas", "periodos"),
    "Verificador": ("mediciones", "certificados", "enmiendas", "fincas", "periodos"),
    "Administrador": ("fincas", "cuentas", "periodos"),
    "Auditor externo": ("bitacora", "mediciones", "certificados", "enmiendas", "fincas", "periodos"),
    "Dueno de finca": ("fincas", "mediciones", "certificados", "enmiendas", "periodos"),
    "Gerencia de Certificacion": (
        "periodos", "mediciones", "enmiendas", "cuentas", "certificados", "fincas", "bitacora",
    ),
}


@dataclass(frozen=True)
class Guia:
    """Qué puede y qué no puede hacer el rol activo en una pantalla, en una línea cada cosa.

    Es TEXTO DE AYUDA escrito a partir de opa/policies/authz.rego. No decide nada: si el
    texto y la política no coinciden, manda la política, y la constancia lo mostrará.
    """

    puede: str
    no_puede: str


_NOTA_CERTIFICADOS = (
    " Este módulo todavía no consulta la matriz, así que hoy la pantalla no lo impide"
    " (vea la nota de abajo)."
)

_GUIAS = {
    "Tecnico de campo": {
        "mediciones": Guia(
            "Registrar mediciones en las fincas que tiene asignadas, corregirlas y enviarlas"
            " a verificación mientras el período esté abierto (C1). Solo ve las suyas.",
            "Aprobar ni devolver: eso le toca al Verificador (DENY_DEFAULT). Con el período"
            " cerrado, C1 niega registrar o corregir; la corrección va por enmienda."),
        "enmiendas": Guia(
            "Pedir una enmienda sobre una medición aprobada de una finca suya, con motivo"
            " escrito y con el período ya cerrado (C4). Ve solo las que usted pidió.",
            "Autorizar ni rechazar enmiendas: eso le toca a Gerencia (DENY_DEFAULT). Con el"
            " período abierto, C4 niega pedirla."),
        "fincas": Guia(
            "Leer las fincas que tiene asignadas (S1). Pasadas 20 lecturas en 24 horas se pide"
            " segundo factor, y pasadas 60 se bloquea (C5).",
            "Leer fincas que no tiene asignadas (S1), ni inscribir o desactivar fincas"
            " (DENY_DEFAULT)."),
        "periodos": Guia(
            "Consultar qué períodos están abiertos (MATRIZ_SIMPLE).",
            "Abrirlos ni cerrarlos: solo Gerencia lo hace (DENY_DEFAULT)."),
    },
    "Verificador": {
        "mediciones": Guia(
            "Leer las mediciones, y aprobar o devolver las enviadas que usted no creó ni"
            " editó, con el segundo factor confirmado en los últimos 5 minutos (C2).",
            "Registrar, corregir ni enviar mediciones: eso le toca al técnico (DENY_DEFAULT)."
            " Aprobar una medición suya: C2 lo niega aunque tenga segundo factor."),
        "certificados": Guia(
            "Según la matriz: emitir certificados sobre mediciones aprobadas que usted no"
            " creó (C3), y leerlos y descargarlos.",
            "Según la matriz, revocarlos le toca a Gerencia." + _NOTA_CERTIFICADOS),
        "enmiendas": Guia(
            "Leer las enmiendas (MATRIZ_SIMPLE). Cuando Gerencia autoriza una, la versión"
            " nueva de la medición vuelve a verificación y la aprueba usted.",
            "Pedir enmiendas, autorizarlas o rechazarlas (DENY_DEFAULT)."),
        "fincas": Guia("Leer las fincas (MATRIZ_SIMPLE).",
                       "Inscribirlas ni desactivarlas (DENY_DEFAULT)."),
        "periodos": Guia("Consultar los períodos (MATRIZ_SIMPLE).",
                         "Abrirlos ni cerrarlos: solo Gerencia lo hace (DENY_DEFAULT)."),
    },
    "Administrador": {
        "fincas": Guia(
            "Inscribir fincas, leerlas y desactivarlas (MATRIZ_SIMPLE).",
            "Borrar fincas: esa acción no existe, una finca solo se desactiva."),
        "cuentas": Guia(
            "Registrar solicitudes escritas de cambio de cuenta y ejecutar las que Gerencia"
            " ya aprobó, siempre sobre la cuenta de otra persona (C6).",
            "Leer el registro de solicitudes (la matriz no se lo da: DENY_DEFAULT); por eso"
            " ejecuta con el número de la solicitud. Pedir o ejecutar un cambio sobre su"
            " propia cuenta: C6 lo niega. Aprobar: le toca a Gerencia (DENY_DEFAULT)."),
        "periodos": Guia("Consultar los períodos (MATRIZ_SIMPLE).",
                         "Abrirlos ni cerrarlos: solo Gerencia lo hace (DENY_DEFAULT)."),
    },
    "Auditor externo": {
        "bitacora": Guia(
            "Leer la bitácora completa y verificar la integridad de su cadena de hashes."
            " Leerla también deja una entrada.",
            "Modificar o borrar entradas: esa acción no existe y la base de datos lo impide."),
        "mediciones": Guia("Leer todas las mediciones (MATRIZ_SIMPLE).",
                           "Cambiar nada: el auditor solo lee (DENY_DEFAULT)."),
        "certificados": Guia(
            "Según la matriz: leer y descargar certificados.",
            "Según la matriz, emitir o revocar no le corresponde." + _NOTA_CERTIFICADOS),
        "enmiendas": Guia("Leer las enmiendas (MATRIZ_SIMPLE).",
                          "Pedirlas, autorizarlas o rechazarlas (DENY_DEFAULT)."),
        "fincas": Guia("Leer las fincas (MATRIZ_SIMPLE).",
                       "Inscribirlas ni desactivarlas (DENY_DEFAULT)."),
        "periodos": Guia("Consultar los períodos (MATRIZ_SIMPLE).",
                         "Abrirlos ni cerrarlos (DENY_DEFAULT)."),
    },
    "Dueno de finca": {
        "fincas": Guia("Leer las fincas que son suyas (S2).",
                       "Ver fincas de otras personas (S2), ni inscribir o desactivar (DENY_DEFAULT)."),
        "mediciones": Guia("Leer las mediciones de sus fincas (S2).",
                           "Ver las de fincas ajenas (S2), ni registrar o aprobar (DENY_DEFAULT)."),
        "certificados": Guia(
            "Según la matriz: leer y descargar los certificados de sus fincas (S2).",
            "Según la matriz, emitir o revocar no le corresponde." + _NOTA_CERTIFICADOS),
        "enmiendas": Guia("Leer las enmiendas de sus fincas (S2).",
                          "Pedirlas, autorizarlas o rechazarlas (DENY_DEFAULT)."),
        "periodos": Guia("Consultar los períodos (S2).",
                         "Abrirlos ni cerrarlos (DENY_DEFAULT)."),
    },
    "Gerencia de Certificacion": {
        "periodos": Guia(
            "Abrir y cerrar períodos (MATRIZ_SIMPLE). Cerrar uno bloquea las escrituras sobre"
            " sus mediciones (C1) y abre la vía de enmienda (C4).",
            "Borrar períodos: esa acción no existe."),
        "mediciones": Guia("Leer todas las mediciones (MATRIZ_SIMPLE).",
                           "Registrarlas, aprobarlas o devolverlas (DENY_DEFAULT)."),
        "enmiendas": Guia(
            "Leer las enmiendas, y autorizarlas o rechazarlas con el período cerrado si no"
            " fue usted quien la pidió (C4).",
            "Pedir enmiendas: eso le toca al técnico (DENY_DEFAULT)."),
        "cuentas": Guia(
            "Leer las solicitudes de cuenta y aprobarlas (C6). Nadie aprueba cambios sobre"
            " su propia cuenta.",
            "Registrarlas ni ejecutarlas: eso le toca al Administrador (DENY_DEFAULT)."),
        "certificados": Guia(
            "Según la matriz: leer y revocar certificados.",
            "Según la matriz, emitir le toca al Verificador." + _NOTA_CERTIFICADOS),
        "fincas": Guia("Leer las fincas (MATRIZ_SIMPLE).",
                       "Inscribirlas ni desactivarlas (DENY_DEFAULT)."),
        "bitacora": Guia("Leer la bitácora y verificar su cadena de hashes.",
                         "Modificar o borrar entradas: esa acción no existe."),
    },
}


def guia(rol: str, pantalla: str) -> Guia:
    """La ayuda de la pantalla para el rol. Fuera de su alcance, lo dice tal cual."""
    propia = _GUIAS.get(rol, {}).get(pantalla)
    if propia:
        return propia
    if pantalla == "certificados":
        return Guia("Según la matriz, nada: este rol no tiene acciones sobre certificados.",
                    _NOTA_CERTIFICADOS.strip())
    objeto = PANTALLAS[pantalla].objeto
    return Guia(
        f"Nada: la matriz no le da a este rol ninguna acción sobre {objeto}.",
        "Leer o actuar aquí se le niega con DENY_DEFAULT. La pantalla queda abierta a"
        " propósito para que lo compruebe.")


# Roles que ven nombres de usuario en lugar de números (/registro/directorio/). Son los
# que trabajan con personas ajenas en pantalla: cuentas, bitácora, autor de mediciones.
# Técnico y Dueño siguen viendo «#id»; su propia cuenta igual aparece como «(usted)».
ROLES_CON_DIRECTORIO = frozenset({
    "Administrador", "Gerencia de Certificacion", "Auditor externo", "Verificador",
})


def roles_de(usuario) -> list[Rol]:
    """Roles vigentes de la persona, leídos de la base en cada llamada."""
    nombres = set(usuario.groups.values_list("name", flat=True))
    return [r for r in _ROLES if r.valor in nombres]


def menu(rol: str) -> tuple[list[Pantalla], list[Pantalla]]:
    """(lo que la matriz le abre al rol, el resto)."""
    propias = [PANTALLAS[c] for c in ALCANCE.get(rol, ())]
    resto = [p for p in PANTALLAS.values() if p not in propias]
    return propias, resto
