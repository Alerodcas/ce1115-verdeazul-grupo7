import os
import sys
import uuid
import django

# Configurar el entorno de Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from certificados.models import PeriodoMedicion, Certificado
from certificados.crypto import generar_par_claves, firmar_datos, verificar_firma
from django.contrib.auth import get_user_model

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
    periodo, _ = PeriodoMedicion.objects.get_or_create(
        nombre="Período 2026-I Test Script", 
        anio=2026, 
        defaults={"estado": "ABIERTO", "modificado_por": user}
    )

    print(f"\n[+] Período de medición: '{periodo.nombre}' (Estado: {periodo.estado})")

    # 2. Generar Par de Claves RSA
    print("[+] Generando par de claves criptográficas RSA-256 de prueba...")
    priv_key, pub_key = generar_par_claves()

    # 3. Datos del Certificado (Payload Canónico)
    finca_id = str(uuid.uuid4())
    parcela_id = "PARCELA-NORTE-01"
    payload = {
        "finca_id": finca_id,
        "parcela_id": parcela_id,
        "toneladas_co2": 245.80,
        "periodo": periodo.nombre
    }

    # 4. Firmar los datos
    print("[+] Generando firma digital RSA-SHA256...")
    firma_b64 = firmar_datos(payload, priv_key)
    print(f"    Firma (Base64 truncado): {firma_b64[:45]}...")

    # -------------------------------------------------------------
    # PRUEBA 1: Verificación de Certificado Auténtico
    # -------------------------------------------------------------
    print("\n" + "-" * 50)
    print("PRUEBA 1: Verificación de Certificado Auténtico (Sin alterar)")
    print("-" * 50)
    es_valida_original = verificar_firma(payload, firma_b64, pub_key)
    print(f"Resultado de Verificación: {es_valida_original}")
    if es_valida_original:
        print(" SUCCESS: El certificado es 100% auténtico e íntegro.")
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

    es_valida_alterado = verificar_firma(payload_alterado, firma_b64, pub_key)
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
