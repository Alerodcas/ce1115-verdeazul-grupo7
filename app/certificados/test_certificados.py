import os
import uuid

import django
from django.contrib.auth import get_user_model

from certificados.crypto import generate_key_pair, sign_data, verify_sign
from certificados.models import PeriodoMedida

# Configurar el entorno de Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()




User = get_user_model()

def ejecutar_pruebas():
    print("=" * 60)
    print("  INICIANDO PRUEBAS DEL MÓDULO DE CERTIFICACIÓN DIGITAL")
    print("=" * 60)

    # 1. Preparar Usuario y Período
    user, _ = User.objects.get_or_create(
        username="auditor_test", 
        defaults={"is_staff": True, "email": "auditor@verdeazul.com"}
    )
    period, _ = PeriodoMedida.objects.get_or_create(
        name="Período 2026-I Test Script", 
        year=2026, 
        defaults={"status": "ABIERTO", "modified_by": user}
    )

    print(f"\n[+] Período de medición: '{period.name}' (Estado: {period.status})")

    # 2. Generar Par de Claves RSA
    print("[+] Generando par de claves criptográficas RSA-256 de prueba...")
    priv_key, pub_key = generate_key_pair()

    # 3. Datos del Certificado (Payload Canónico)
    finca_id = str(uuid.uuid4())
    parcela_id = "PARCELA-NORTE-01"
    payload = {
        "finca_id": finca_id,
        "parcela_id": parcela_id,
        "toneladas_co2": 245.80,
        "periodo": period.name
    }

    # 4. Firmar los datos
    print("[+] Generando firma digital RSA-SHA256...")
    sign_b64 = sign_data(payload, priv_key)
    print(f"    Firma (Base64 truncado): {sign_b64[:45]}...")

    # -------------------------------------------------------------
    # PRUEBA 1: Verificación de Certificado Auténtico
    # -------------------------------------------------------------
    print("\n" + "-" * 50)
    print("PRUEBA 1: Verificación de Certificado Auténtico (Sin alterar)")
    print("-" * 50)
    es_valida_original = verify_sign(payload, sign_b64, pub_key)
    print(f"Resultado de Verificación: {es_valida_original}")
    if es_valida_original:
        print(" SUCCESS: El certificado es auténtico e íntegro.")
    else:
        print(" FAILED: La firma válida fue rechazada por error.")

    # -------------------------------------------------------------
    # PRUEBA 2: Verificación de Certificado Alterado (Fraude / Manipulación)
    # -------------------------------------------------------------
    print("\n" + "-" * 50)
    print("PRUEBA 2: Verificación de Certificado ALTERADO (Manipulado)")
    print("-" * 50)
    payload_alterado = payload.copy()
    payload_alterado["toneladas_co2"] = 9999.99  # Intento de alteración de datos

    es_valida_alterado = verify_sign(payload_alterado, sign_b64, pub_key)
    print(f"Resultado de Verificación: {es_valida_alterado}")
    if not es_valida_alterado:
        print(" SUCCESS: El sistema detectó la alteración y RECHAZÓ el certificado.")
    else:
        print(" FAILED: El sistema aceptó un certificado manipulado.")

    print("\n" + "=" * 60)
    print("  PRUEBAS COMPLETADAS EXITOSAMENTE")
    print("=" * 60 + "\n")

if __name__ == '__main__':
    ejecutar_pruebas()
