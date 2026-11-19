"""Segundo factor por código de un solo uso con tiempo (TOTP, RFC 6238).

`negocio/atributos.py` ya lee `session["mfa_verificado_en"]` para las celdas que
exigen segundo factor reciente (C2, y C5 entre 21 y 60 lecturas), pero nada lo
fijaba: sin este flujo esas celdas quedaban siempre cerradas.

Solo biblioteca estándar. El secreto de cada persona se deriva de SECRET_KEY con
`salted_hmac`, así que no se guarda en la base ni necesita migración. Consecuencias
que se aceptan y quedan escritas:

* Rotar SECRET_KEY cambia todos los secretos: hay que volver a enrolar.
* No se revoca el factor de una sola persona sin rotar la clave.
* El secreto no se muestra en la web. Lo entrega quien administra, fuera de banda,
  con `python manage.py secreto_mfa <usuario>`.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import struct
import time
from urllib.parse import quote

from django.utils.crypto import salted_hmac

PASO_SEGUNDOS = 30
DIGITOS = 6
EMISOR = "Verdeazul Carbono"


def secreto(usuario) -> bytes:
    """20 bytes, estables para la persona mientras no cambie SECRET_KEY."""
    return salted_hmac(
        "interfaz.totp.secreto", f"{usuario.pk}:{usuario.get_username()}", algorithm="sha256"
    ).digest()[:20]


def secreto_base32(usuario) -> str:
    return base64.b32encode(secreto(usuario)).decode("ascii").rstrip("=")


def uri_enrolamiento(usuario) -> str:
    """El texto que entiende cualquier aplicación autenticadora."""
    etiqueta = quote(f"{EMISOR}:{usuario.get_username()}")
    return (
        f"otpauth://totp/{etiqueta}?secret={secreto_base32(usuario)}"
        f"&issuer={quote(EMISOR)}&algorithm=SHA1&digits={DIGITOS}&period={PASO_SEGUNDOS}"
    )


def codigo(clave: bytes, paso: int, digitos: int = DIGITOS) -> str:
    """HOTP (RFC 4226) sobre el número de paso. SHA-1 es lo que exige el estándar."""
    resumen = hmac.new(clave, struct.pack(">Q", paso), hashlib.sha1).digest()
    desplazamiento = resumen[-1] & 0x0F
    numero = struct.unpack(">I", resumen[desplazamiento:desplazamiento + 4])[0] & 0x7FFFFFFF
    return str(numero % (10**digitos)).zfill(digitos)


def paso_actual(ahora: float | None = None) -> int:
    return int((time.time() if ahora is None else ahora) // PASO_SEGUNDOS)


def verificar(usuario, texto: str, *, ahora: float | None = None, ventana: int = 1) -> int | None:
    """Devuelve el paso que coincidió, o None.

    Acepta un paso antes y uno después (reloj del teléfono desfasado). Quien llama
    guarda el paso usado para no aceptar dos veces el mismo código.
    """
    texto = (texto or "").strip().replace(" ", "")
    if len(texto) != DIGITOS or not texto.isdigit():
        return None
    clave, base = secreto(usuario), paso_actual(ahora)
    for paso in range(base - ventana, base + ventana + 1):
        if hmac.compare_digest(codigo(clave, paso), texto):
            return paso
    return None
