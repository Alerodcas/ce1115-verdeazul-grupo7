/* Enmiendas: pedir, autorizar y rechazar. Todo por /api/enmiendas/... */
(function () {
  'use strict';
  var R = window.Registro, el = R.el;
  var contenedor = document.getElementById('registro');
  var mediciones = new Map();

  var ESTADOS = {
    solicitada: { texto: 'Solicitada', tono: 'ink' },
    autorizada: { texto: 'Autorizada', tono: 'aprobado' },
    aplicada: { texto: 'Aplicada', tono: 'aprobado' },
    rechazada: { texto: 'Rechazada', tono: 'denegado' },
  };

  function hechos(e) {
    var h = [];
    if (Number(e.solicitante) === R.sesion.usuarioId) h.push('Dato del registro: usted pidió esta enmienda.');
    return h;
  }

  var tabla = new R.Tabla(contenedor, {
    vacio: 'No hay enmiendas en su alcance. Un técnico la pide sobre una medición aprobada, con el período ya cerrado, desde el formulario de arriba.',
    siguiente: function (e) {
      switch (e.estado) {
        case 'solicitada': return 'alguien de Gerencia que no la haya pedido la autoriza o la rechaza, con el período cerrado (C4).';
        case 'autorizada':
        case 'aplicada': return e.medicion_nueva
          ? 'la medición #' + e.medicion_nueva + ' es la versión nueva: vuelve a verificación y la aprueba un Verificador (C2).'
          : 'la versión nueva de la medición vuelve a verificación (C2).';
        case 'rechazada': return 'la medición queda como estaba.';
        default: return '';
      }
    },
    estado: function (e) { return ESTADOS[e.estado] || { texto: R.capital(e.estado), tono: 'ink' }; },
    columnas: [
      { titulo: 'Enmienda', valor: function (e) { return el('code', { text: '#' + e.id }); } },
      { titulo: 'Medición', valor: function (e) { return el('code', { text: '#' + e.medicion }); } },
      { titulo: 'Valor propuesto', clase: 'num', valor: function (e) { return e.valor_propuesto; } },
      { titulo: 'Motivo', clase: 'ancho', valor: function (e) { return e.motivo; } },
      { titulo: 'Pidió', valor: function (e) { return R.persona(e.solicitante); } },
      { titulo: 'Resolvió', valor: function (e) { return R.persona(e.autorizante); } },
      { titulo: 'Versión nueva', valor: function (e) { return e.medicion_nueva ? el('code', { text: '#' + e.medicion_nueva }) : ''; } },
    ],
    acciones: function (e) {
      if (e.estado !== 'solicitada') return [];
      var base = '/api/enmiendas/' + e.id + '/';
      return [
        { verbo: 'Autorizar', exito: 'Autorizada', url: base + 'autorizar/', hechos: hechos(e), quien: 'Gerencia de Certificación',
          despues: 'La versión nueva de la medición queda enviada: la aprueba un Verificador en Mediciones (C2).' },
        { verbo: 'Rechazar', exito: 'Rechazada', url: base + 'rechazar/', hechos: hechos(e), quien: 'Gerencia de Certificación',
          despues: 'La medición queda como estaba.' },
      ];
    },
    alCambiar: cargar,
  });

  async function cargar() {
    var res = await R.api('GET', '/api/enmiendas/');
    if (!res.ok) { R.negacionDeLectura(contenedor, res, 'enmiendas', 'Técnico de campo (las suyas), Verificador, Auditor externo, Dueño de finca o Gerencia'); return; }
    tabla.pintar(res.datos);
  }

  async function cargarMediciones() {
    var lista = await R.lista('/api/mediciones/');
    var aprobadas = lista && lista.filter(function (m) { return m.estado === 'aprobada'; });
    mediciones = R.porId(aprobadas);
    var select = R.selector(document.getElementById('campo-medicion'),
      aprobadas && aprobadas.map(function (m) { return { valor: m.id, texto: '#' + m.id + ' v' + m.version + ', ' + m.valor + ' ' + m.unidad }; }),
      'No hay mediciones aprobadas en su alcance');
    var pedida = new URLSearchParams(location.search).get('medicion');
    if (pedida) select.value = pedida;
  }

  R.formulario(document.getElementById('form-nueva'), {
    verbo: 'Pedir enmienda', exito: 'Solicitada', url: '/api/enmiendas/nueva/', quien: 'Técnico de campo',
    despues: 'Alguien de Gerencia que no sea usted la autoriza o la rechaza en esta misma pantalla.',
    siguiente: { C4: 'El período de la medición tiene que estar cerrado (lo cierra Gerencia en Períodos), el motivo escrito y la finca asignada a usted.' },
    datos: function (fd) { return { medicion: fd.get('medicion'), motivo: fd.get('motivo'), valor_propuesto: fd.get('valor_propuesto') }; },
    textoExito: function (e) { return 'Enmienda #' + e.id + ' en espera de Gerencia.'; },
    alTerminar: cargar,
  });

  cargarMediciones();
  cargar();
})();
