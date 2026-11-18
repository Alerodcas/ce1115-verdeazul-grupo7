import base64
import json
import os

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from django.conf import setting


def generate_key_pair()-> tuple[str, str]:
    """ Genera un par de claves criptográficas RSA de 2048 bits. Returns: tuple[str, str]: (private_key_pem, public_key_pem) en formato PEM (UTF-8). """
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    ).decode('utf-8')

    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode('utf-8')

    return private_pem, public_pem


def get_private_key_pem() -> str:
    """
    Obtiene la clave privada de firma desde la variable de entorno VERDEAZUL_CERT_SIGNING_KEY
    o desde la configuración de settings.
    """
    key = os.getenv('VERDEAZUL_CERT_SIGNING_KEY', getattr(setting, 'VERDEAZUL_CERT_SIGNING_KEY', None))
    if not key:
        raise ValueError("No se encontró la clave privada de firma (VERDEAZUL_CERT_SIGNING_KEY).")
    return key.strip().replace('\\n', '\n')

def get_public_from_private_pem_key(private_key_pem: str) -> str:
    """
    Extrae la clave pública en formato PEM correspondiente a la clave privada dada.
    """
    private_key = serialization.load_pem_private_key(
        private_key_pem.encode('utf-8'),
        password=None
    )
    public_key = private_key.public_key()
    return public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode('utf-8')

def sign_data(dict_data: dict, private_key_pem: str) -> str: 
    bytes_content = json.dumps(dict_data, sort_keys=True).encode('utf-8')

    private_key = serialization.load_pem_private_key(private_key_pem.encode('utf-8'), password=None)

    #Se firma con SHA-256 y PSS/PKC1v15
    sign = private_key.sign(bytes_content, 
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256()
    )

    return base64.b64encode(sign).decode('utf-8')

def verify_sign(dict_data: dict, sign_b64: str, public_key_pem: str) -> bool:
    try:
        bytes_content = json.dumps(dict_data, sort_keys=True).encode('utf-8')
        sign = base64.b64decode(sign_b64)

        public_key = serialization.load_pem_public_key(public_key_pem.encode('utf-8'))

        public_key.verify(sign, 
            bytes_content,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
            hashes.SHA256()
        )

        return True
    except Exception:
        return False