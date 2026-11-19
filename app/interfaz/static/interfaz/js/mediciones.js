/* Mediciones: registrar, enviar, corregir, aprobar y devolver.
   Todo pasa por /api/mediciones/...; la regla que decide la muestra el servidor. */
(function () {
  'use strict';
  var R = window.Registro, el = R.el;

  var ESTADOS = {
    borrador: { texto: 'Borrador', tono: 'borrador' },
    enviada: { texto: 'Enviada', tono: 'ink' },
    devuelta: { texto: 'Devuelta', tono: 'denegado' },
    aprobada: { texto: 'Aprobada', tono: 'aprobado' },
  };

  var fincas = new Map(), periodos = new Map();
  var contenedor = document.getElementById('registro');

  function nombreFinca(id) {
    var f = fincas.get(String(id));
    return f ? f.nombre : el('code', { text: '#' + id });
  }
  function etiquetaPeriodo(id) {
    var p = periodos.get(String(id));
    return p ? el('span', null, el('code', { text: p.etiqueta }), p.abierto ? '' : ' (cerrado)') : el('code', { text: '#' + id });
  }

  // Datos del registro que ayudan a leer una decisión. No la explican por su cuenta.
  function hechos(m) {
    var h = [];
    if (Number(m.creada_por) === R.sesion.usuarioId) h.push('Dato del registro: usted creó esta medición.');
    var p = periodos.get(String(m.periodo));
    if (p && !p.abierto) h.push('Dato del registro: el período ' + p.etiqueta + ' está cerrado.');
    return h;
  }

  var TECNICO = 'Técnico de campo', VERIFICADOR = 'Verificador';
  var tras = {
    enviar: 'un Verificador que no la creó ni editó la aprueba o la devuelve, con segundo factor reciente (C2).',
    devolver: 'el técnico autor la corrige y la vuelve a enviar (C1).',
  };

  // El siguiente paso de cada estado, en palabras. Quién puede darlo lo decide el PEP.
  function siguiente(m) {
    var mia = Number(m.creada_por) === R.sesion.usuarioId;
    switch (m.estado) {
      case 'borrador': return mia ? 'envíela a verificación con «Enviar» (C1).' : 'el técnico autor la envía a verificación (C1).';
      case 'devuelta': return mia ? 'corríjala y vuelva a enviarla (C1).' : tras.devolver;
      case 'enviada': return mia ? 'la aprueba o devuelve un Verificador que no sea usted (C2).' : tras.enviar;
      case 'aprobada': return 'lista para certificar. Para corregirla, Gerencia cierra el período y el técnico pide una enmienda (C4).';
      default: return '';
    }
  }

  var tabla = new R.Tabla(contenedor, {
    vacio: 'Todavía no hay mediciones en su alcance. Cada rol ve solo lo suyo: el técnico, las que registró en sus fincas (C1, S1); el dueño, las de sus fincas (S2). Un técnico registra la primera con el formulario de arriba.',
    siguiente: siguiente,
    estado: function (m) { return ESTADOS[m.estado] || { texto: R.capital(m.estado), tono: 'ink' }; },
    columnas: [
      { titulo: 'Medición', valor: function (m) { return el('span', null, el('code', { text: '#' + m.id }), ' v' + m.version); } },
      { titulo: 'Finca', valor: function (m) { return nombreFinca(m.finca); } },
      { titulo: 'Período', valor: function (m) { return etiquetaPeriodo(m.periodo); } },
      { titulo: 'Valor', clase: 'num', valor: function (m) { return m.valor + ' ' + m.unidad; } },
      { titulo: 'Autor', valor: function (m) { return R.persona(m.creada_por); } },
      { titulo: 'Actualizada', clase: 'num', valor: function (m) { return R.fechaHora(m.actualizada_en); } },
    ],
    acciones: function (m) {
      var base = '/api/mediciones/' + m.id + '/';
      var h = hechos(m);
      if (m.estado === 'borrador' || m.estado === 'devuelta') {
        return [
          { verbo: 'Enviar', exito: 'Enviada', url: base + 'enviar/', hechos: h, quien: TECNICO + ' (quien la creó)', despues: 'Ahora ' + tras.enviar },
          { verbo: 'Corregir', exito: 'Corregida', metodo: 'PATCH', url: base, hechos: h, quien: TECNICO + ' (quien la creó)',
            despues: 'Envíela a verificación con «Enviar».',
            campo: { nombre: 'valor', tipo: 'number', paso: '0.001', valor: m.valor, etiqueta: 'Valor corregido', confirmar: 'Guardar corrección' } },
        ];
      }
      if (m.estado === 'enviada') {
        return [
          { verbo: 'Aprobar', exito: 'Aprobada', url: base + 'aprobar/', hechos: h, quien: VERIFICADOR, despues: 'Queda lista para certificar. Para corregirla después, Gerencia cierra el período y el técnico pide una enmienda (C4).' },
          { verbo: 'Devolver', exito: 'Devuelta', url: base + 'devolver/', hechos: h, quien: VERIFICADOR, despues: 'Ahora ' + tras.devolver },
        ];
      }
      if (m.estado === 'aprobada') {
        return [{ verbo: 'Pedir enmienda', enlace: '/registro/enmiendas/?medicion=' + m.id }];
      }
      return [];
    },
    alCambiar: cargar,
  });

  async function cargar() {
    var res = await R.api('GET', '/api/mediciones/');
    if (!res.ok) { R.negacionDeLectura(contenedor, res, 'mediciones', 'Técnico de campo, Verificador, Auditor externo, Dueño de finca o Gerencia'); return; }
    tabla.pintar(res.datos);
  }

  async function iniciar() {
    // Fincas y períodos solo sirven para mostrar nombres y llenar el formulario.
    // Si el rol no los puede leer, se trabaja con números: la API decide igual.
    var listas = await Promise.all([R.lista('/api/fincas/'), R.lista('/api/periodos/')]);
    fincas = R.porId(listas[0]); periodos = R.porId(listas[1]);
    R.selector(document.getElementById('campo-finca'),
      listas[0] && listas[0].filter(function (f) { return f.activa; }).map(function (f) { return { valor: f.id, texto: f.nombre }; }),
      'No tiene fincas en su alcance');
    R.selector(document.getElementById('campo-periodo'),
      listas[1] && listas[1].map(function (p) { return { valor: p.id, texto: p.etiqueta + (p.abierto ? ' (abierto)' : ' (cerrado)') }; }),
      'No hay períodos');

    R.formulario(document.getElementById('form-nueva'), {
      verbo: 'Registrar medición', exito: 'Registrada', url: '/api/mediciones/nueva/', quien: TECNICO,
      despues: 'Envíela a verificación con «Enviar» en el registro de abajo.',
      siguiente: { C1: 'Elija una finca que tenga asignada y un período abierto. Si el período ya cerró, la corrección va por enmienda (C4).' },
      datos: function (fd) {
        return { finca: fd.get('finca'), periodo: fd.get('periodo'), valor: fd.get('valor'), unidad: fd.get('unidad') };
      },
      hechos: function (res, datos) {
        var p = periodos.get(String(datos.periodo));
        return p && !p.abierto ? ['Dato del registro: el período ' + p.etiqueta + ' está cerrado.'] : [];
      },
      interpretar: function (res, accion, hechos) {
        var c = R.interpretar(res, accion, hechos);
        if (res.estado === 400 && /nico|unique/i.test(JSON.stringify(res.datos || {}))) {
          c.texto = 'Ya hay una medición de esa finca en ese período. Corrija la existente o pida una enmienda: no se registra una segunda.';
        }
        return c;
      },
      textoExito: function (m) { return 'Medición #' + m.id + ' en borrador.'; },
      alTerminar: cargar,
    });

    await cargar();
  }

  iniciar();
})();
