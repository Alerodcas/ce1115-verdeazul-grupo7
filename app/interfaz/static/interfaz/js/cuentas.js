/* Cuentas: registrar solicitud, aprobar y ejecutar. Todo por /api/cuentas/... */
(function () {
  'use strict';
  var R = window.Registro, el = R.el;
  var contenedor = document.getElementById('registro');

  var ESTADOS = {
    solicitada: { texto: 'Solicitada', tono: 'ink' },
    autorizada: { texto: 'Aprobada', tono: 'aprobado' },
    ejecutada: { texto: 'Ejecutada', tono: 'aprobado' },
    revocada: { texto: 'Revocada', tono: 'denegado' },
  };
  var NOMBRES_ROL = {
    'Tecnico de campo': 'Técnico de campo', 'Dueno de finca': 'Dueño de finca',
    'Gerencia de Certificacion': 'Gerencia de Certificación',
  };

  function hechos(c) {
    var h = [], yo = R.sesion.usuarioId;
    if (Number(c.usuario) === yo) h.push('Dato del registro: la solicitud es sobre su propia cuenta.');
    if (Number(c.aprobador) === yo) h.push('Dato del registro: usted aprobó esta solicitud.');
    return h;
  }

  var ADMIN = 'Administrador', GERENCIA = 'Gerencia de Certificación';

  // Si la solicitud no se puede ejecutar todavía: el Administrador no lee el registro
  // (la matriz no se lo da), así que el consejo no puede ser «revise el registro».
  function sinCambioEjecutar(id) {
    return function (datos) {
      var detalle = (datos && datos.detail) || '';
      if (/autorizada/i.test(detalle)) {
        return 'Pida a Gerencia que apruebe primero la solicitud #' + id + '; cuando esté aprobada, ejecútela aquí con ese número. Si ya se ejecutó, no hay nada más que hacer.';
      }
      return 'Avise a Gerencia con el número de solicitud #' + id + ' y el mensaje de arriba.';
    };
  }

  // El flujo de C6: solicitar (Administrador) → aprobar (Gerencia) → ejecutar (otro Administrador).
  function siguiente(c) {
    switch (c.estado) {
      case 'solicitada': return 'Gerencia la aprueba (C6). Nadie aprueba cambios sobre su propia cuenta.';
      case 'autorizada': return 'un Administrador que no sea la persona afectada la ejecuta con el número #' + c.id + ' (C6).';
      case 'ejecutada': return c.tipo === 'desactivar' ? 'la cuenta quedó desactivada.'
        : 'la persona ya tiene el rol; lo elige con «Cambiar de rol» la próxima vez que entre o desde el panel.';
      default: return '';
    }
  }

  var tabla = new R.Tabla(contenedor, {
    vacio: 'No hay solicitudes de cuenta. Un Administrador registra la primera con el formulario de arriba.',
    siguiente: siguiente,
    estado: function (c) { return ESTADOS[c.estado] || { texto: R.capital(c.estado), tono: 'ink' }; },
    columnas: [
      { titulo: 'Solicitud', valor: function (c) { return el('code', { text: '#' + c.id }); } },
      { titulo: 'Cambio', valor: function (c) {
        return c.tipo === 'desactivar' ? 'Desactivar cuenta' : 'Asignar ' + (NOMBRES_ROL[c.rol_solicitado] || c.rol_solicitado);
      } },
      { titulo: 'Sobre', valor: function (c) { return R.persona(c.usuario); } },
      { titulo: 'Texto de la solicitud', clase: 'ancho', valor: function (c) { return c.solicitud; } },
      { titulo: 'Pidió', valor: function (c) { return R.persona(c.solicitante); } },
      { titulo: 'Aprobó', valor: function (c) { return R.persona(c.aprobador); } },
      { titulo: 'Ejecutó', valor: function (c) { return R.persona(c.ejecutor); } },
    ],
    acciones: function (c) {
      var base = '/api/cuentas/' + c.id + '/';
      if (c.estado === 'solicitada') return [{ verbo: 'Aprobar', exito: 'Aprobada', url: base + 'aprobar/', hechos: hechos(c), quien: GERENCIA,
        despues: 'Un Administrador que no sea la persona afectada la ejecuta con el número #' + c.id + '.' }];
      if (c.estado === 'autorizada') return [{ verbo: 'Ejecutar', exito: 'Ejecutada', url: base + 'ejecutar/', hechos: hechos(c), quien: ADMIN,
        despues: 'El cambio ya está aplicado a la cuenta.', sinCambio: sinCambioEjecutar(c.id) }];
      return [];
    },
    alCambiar: cargar,
  });

  async function cargar() {
    var res = await R.api('GET', '/api/cuentas/');
    if (!res.ok) {
      R.negacionDeLectura(contenedor, res, 'cuentas', GERENCIA);
      // El Administrador no lee el registro (la matriz no se lo da), pero sí ejecuta por número.
      if (R.sesion.rol === 'Administrador') {
        contenedor.querySelector('.negacion, .vacio').append(R.el('p', { class: 'nota',
          text: 'Como Administrador, ejecute una solicitud aprobada con su número en «Actuar sobre una solicitud por número», arriba.' }));
      }
      return;
    }
    tabla.pintar(res.datos);
  }

  var tipo = document.getElementById('campo-tipo');
  tipo.addEventListener('change', function () {
    document.getElementById('envoltura-rol').classList.toggle('oculto', tipo.value === 'desactivar');
  });

  R.formulario(document.getElementById('form-nueva'), {
    verbo: 'Registrar solicitud', exito: 'Registrada', url: '/api/cuentas/nueva/', quien: ADMIN,
    datos: function (fd, form) {
      // La persona se escribe por nombre; la API recibe su número.
      var usuario = R.campoUsuario(form, 'usuario');
      if (usuario && usuario.rechazo) return usuario;
      var d = { tipo: fd.get('tipo'), usuario: usuario, solicitud: fd.get('solicitud') };
      d.rol_solicitado = d.tipo === 'desactivar' ? '' : fd.get('rol_solicitado');
      return d;
    },
    hechos: function (res, datos) {
      return Number(datos.usuario) === R.sesion.usuarioId ? ['Dato de la solicitud: es sobre su propia cuenta.'] : [];
    },
    textoExito: function (c) { return 'Solicitud #' + c.id + ' en espera de aprobación.'; },
    // Deja el número listo en «Actuar sobre una solicitud por número»: no hay que copiarlo.
    alTerminar: function (c) {
      document.querySelector('#form-numero input[name="id"]').value = c.id;
      return cargar();
    },
    despues: function (c) { return 'Gerencia aprueba la solicitud #' + c.id + '; después, un Administrador la ejecuta con ese número.'; },
  });

  // Actuar por número: para quien ejecuta sin poder leer el registro.
  var formNumero = document.getElementById('form-numero');
  var listaNumero = formNumero.querySelector('ol.constancias');
  formNumero.addEventListener('submit', async function (ev) {
    ev.preventDefault();
    var boton = ev.submitter;
    var botones = Array.prototype.slice.call(formNumero.querySelectorAll('button[type="submit"]'));
    if (botones.some(function (b) { return b.disabled; })) return; // ya hay un envío en curso
    var id = Number(new FormData(formNumero).get('id'));
    if (!id) return;
    var ejecutar = boton && boton.value === 'ejecutar';
    var accion = ejecutar
      ? { verbo: 'Ejecutar #' + id, exito: 'Ejecutada', quien: ADMIN, despues: 'El cambio ya está aplicado a la cuenta.', sinCambio: sinCambioEjecutar(id) }
      : { verbo: 'Aprobar #' + id, exito: 'Aprobada', quien: GERENCIA, despues: 'Un Administrador que no sea la persona afectada la ejecuta con el número #' + id + '.',
          sinCambio: 'La solicitud #' + id + ' ya no espera aprobación. Si ya está aprobada, la ejecuta un Administrador con ese número.' };
    R.ocupado(botones, true);
    var res = await R.api('POST', '/api/cuentas/' + id + '/' + (ejecutar ? 'ejecutar/' : 'aprobar/'));
    R.ocupado(botones, false);
    var li = R.constancia(listaNumero, R.interpretar(res, accion));
    if (res.ok) await cargar();
    R.enfocar(li);
  });

  cargar();
})();
