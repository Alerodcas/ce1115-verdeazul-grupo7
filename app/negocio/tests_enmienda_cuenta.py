"""Pruebas de las vistas de Enmienda y Cuenta. Responsable: Daniel."""

from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from auditoria.models import Bitacora, ErrorBitacora
from auditoria.servicio import verificar_cadena

from .models import Cuenta, Enmienda, Medicion
from .tests_vistas import BaseVistas


class EnmiendaTest(BaseVistas):
    def aprobada(self):
        return self.medicion(estado="aprobada")

    def pedir(self, m, valor="8"):
        c = self.cliente(self.tec)
        return c.post("/api/enmiendas/nueva/", {
            "medicion": m.pk, "motivo": "error de captura", "valor_propuesto": valor,
            "solicitante": self.otro.pk, "estado": "aplicada",
        }, format="json")

    def test_solicitar_fija_solicitante_y_estado(self):
        m = self.aprobada()
        r = self.pedir(m)
        self.assertEqual(r.status_code, 201)
        e = Enmienda.objects.get()
        self.assertEqual((e.solicitante, e.estado, e.autorizante), (self.tec, "solicitada", None))
        self.assertEqual(Bitacora.objects.get().accion, "Create")

    def test_atributos_c4_salen_de_la_base(self):
        m = self.aprobada()
        self.pedir(m)
        a = self.pdp.entradas[0].atributos
        self.assertEqual(a["solicitante"], str(self.tec.pk))
        self.assertTrue(a["finca_asignada"])
        self.assertEqual(a["estado_objeto"], "solicitada")

    def test_solo_se_enmienda_una_medicion_aprobada(self):
        self.assertEqual(self.pedir(self.medicion()).status_code, 409)

    def test_no_se_acumulan_enmiendas_pendientes(self):
        m = self.aprobada()
        self.pedir(m)
        self.assertEqual(self.pedir(m).status_code, 409)

    def test_autorizar_crea_version_nueva_sin_tocar_la_anterior(self):
        m = self.aprobada()
        self.pedir(m, "8")
        e = Enmienda.objects.get()
        c = self.cliente(self.otro, "Gerencia de Certificacion")
        self.assertEqual(c.post(f"/api/enmiendas/{e.pk}/autorizar/").status_code, 200)
        m.refresh_from_db()
        e.refresh_from_db()
        self.assertEqual((str(m.valor), m.estado), ("5.000", "aprobada"))  # intacta
        nueva = e.medicion_nueva
        self.assertEqual((nueva.version, str(nueva.valor), nueva.estado, nueva.reemplaza), (2, "8.000", "enviada", m))
        self.assertEqual((e.estado, e.autorizante), ("aplicada", self.otro))
        self.assertTrue(verificar_cadena().ok)

    def test_quien_solicita_no_autoriza(self):
        m = self.aprobada()
        self.pedir(m)
        e = Enmienda.objects.get()
        c = self.cliente(self.tec, "Gerencia de Certificacion")
        self.assertEqual(c.post(f"/api/enmiendas/{e.pk}/autorizar/").status_code, 403)
        e.refresh_from_db()
        self.assertEqual(e.estado, "solicitada")
        ultima = Bitacora.objects.last()
        self.assertEqual((ultima.resultado, ultima.accion), ("denegado", "Authorize"))

    def test_rechazar_no_crea_version(self):
        m = self.aprobada()
        self.pedir(m)
        e = Enmienda.objects.get()
        c = self.cliente(self.otro, "Gerencia de Certificacion")
        self.assertEqual(c.post(f"/api/enmiendas/{e.pk}/rechazar/").status_code, 200)
        e.refresh_from_db()
        self.assertEqual((e.estado, Medicion.objects.count()), ("rechazada", 1))

    def test_no_se_resuelve_dos_veces(self):
        m = self.aprobada()
        self.pedir(m)
        e = Enmienda.objects.get()
        c = self.cliente(self.otro, "Gerencia de Certificacion")
        c.post(f"/api/enmiendas/{e.pk}/autorizar/")
        self.assertEqual(c.post(f"/api/enmiendas/{e.pk}/autorizar/").status_code, 409)
        self.assertEqual(Medicion.objects.count(), 2)

    def test_si_la_bitacora_falla_no_hay_version_nueva(self):
        m = self.aprobada()
        self.pedir(m)
        e = Enmienda.objects.get()
        c = self.cliente(self.otro, "Gerencia de Certificacion")
        with mock.patch("negocio.views.registrar", side_effect=ErrorBitacora("caida")):
            self.assertEqual(c.post(f"/api/enmiendas/{e.pk}/autorizar/").status_code, 503)
        e.refresh_from_db()
        self.assertEqual((e.estado, Medicion.objects.count()), ("solicitada", 1))


class CuentaTest(BaseVistas):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        U = get_user_model()
        cls.admin, cls.aprueba, cls.ejecuta, cls.objetivo = (
            U.objects.create(username=n) for n in ("admin", "aprueba", "ejecuta", "objetivo")
        )
        Group.objects.create(name="Verificador")

    def solicitar(self, **extra):
        c = self.cliente(self.admin, "Administrador")
        datos = {"usuario": self.objetivo.pk, "rol_solicitado": "Verificador",
                 "solicitud": "Oficio 123", "estado": "ejecutada", **extra}
        return c.post("/api/cuentas/nueva/", datos, format="json")

    def test_solicitud_escrita_obligatoria_y_rol_conocido(self):
        self.assertEqual(self.solicitar(solicitud="  ").status_code, 400)
        self.assertEqual(self.solicitar(rol_solicitado="Dios").status_code, 400)
        self.assertEqual(Cuenta.objects.count(), 0)

    def test_flujo_completo_asigna_el_rol(self):
        self.assertEqual(self.solicitar().status_code, 201)
        cu = Cuenta.objects.get()
        self.assertEqual((cu.estado, cu.solicitante), ("solicitada", self.admin))  # el estado no viene del cliente
        self.cliente(self.aprueba, "Administrador").post(f"/api/cuentas/{cu.pk}/aprobar/")
        c = self.cliente(self.ejecuta, "Administrador")
        self.assertEqual(c.post(f"/api/cuentas/{cu.pk}/ejecutar/").status_code, 200)
        cu.refresh_from_db()
        self.assertEqual((cu.estado, cu.aprobador, cu.ejecutor), ("ejecutada", self.aprueba, self.ejecuta))
        self.assertTrue(self.objetivo.groups.filter(name="Verificador").exists())
        self.assertEqual(list(Bitacora.objects.values_list("accion", flat=True)), ["Create", "Approve", "Update"])
        self.assertTrue(verificar_cadena().ok)

    def test_ejecutor_distinto_del_aprobador(self):
        self.solicitar()
        cu = Cuenta.objects.get()
        self.cliente(self.aprueba, "Administrador").post(f"/api/cuentas/{cu.pk}/aprobar/")
        c = self.cliente(self.aprueba, "Administrador")
        self.assertEqual(c.post(f"/api/cuentas/{cu.pk}/ejecutar/").status_code, 403)
        self.assertFalse(self.objetivo.groups.exists())
        self.assertEqual(Bitacora.objects.last().resultado, "denegado")

    def test_nadie_toca_su_propia_cuenta(self):
        self.solicitar()
        cu = Cuenta.objects.get()
        c = self.cliente(self.objetivo, "Administrador")
        self.assertEqual(c.post(f"/api/cuentas/{cu.pk}/aprobar/").status_code, 403)

    def test_no_se_ejecuta_sin_aprobar(self):
        self.solicitar()
        cu = Cuenta.objects.get()
        c = self.cliente(self.ejecuta, "Administrador")
        self.assertEqual(c.post(f"/api/cuentas/{cu.pk}/ejecutar/").status_code, 409)

    def test_desactivar_usa_la_accion_deactivate_y_no_borra(self):
        self.solicitar(tipo="desactivar", rol_solicitado="")
        cu = Cuenta.objects.get()
        self.cliente(self.aprueba, "Administrador").post(f"/api/cuentas/{cu.pk}/aprobar/")
        c = self.cliente(self.ejecuta, "Administrador")
        self.assertEqual(c.post(f"/api/cuentas/{cu.pk}/ejecutar/").status_code, 200)
        self.assertEqual(self.pdp.entradas[0].accion, "Deactivate")
        self.objetivo.refresh_from_db()
        self.assertFalse(self.objetivo.is_active)
        self.assertTrue(get_user_model().objects.filter(pk=self.objetivo.pk).exists())

    def test_rol_inexistente_en_el_sistema_no_deja_a_medias(self):
        self.solicitar(rol_solicitado="Auditor externo")  # el grupo no existe
        cu = Cuenta.objects.get()
        self.cliente(self.aprueba, "Administrador").post(f"/api/cuentas/{cu.pk}/aprobar/")
        c = self.cliente(self.ejecuta, "Administrador")
        self.assertEqual(c.post(f"/api/cuentas/{cu.pk}/ejecutar/").status_code, 409)
        cu.refresh_from_db()
        self.assertEqual(cu.estado, "autorizada")

    def test_si_la_bitacora_falla_no_cambia_nada(self):
        self.solicitar()
        cu = Cuenta.objects.get()
        self.cliente(self.aprueba, "Administrador").post(f"/api/cuentas/{cu.pk}/aprobar/")
        c = self.cliente(self.ejecuta, "Administrador")
        with mock.patch("negocio.views.registrar", side_effect=ErrorBitacora("caida")):
            self.assertEqual(c.post(f"/api/cuentas/{cu.pk}/ejecutar/").status_code, 503)
        self.assertFalse(self.objetivo.groups.exists())
        cu.refresh_from_db()
        self.assertEqual(cu.estado, "autorizada")
