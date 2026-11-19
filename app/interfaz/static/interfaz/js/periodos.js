/* Períodos: abrir y cerrar. Todo por /api/periodos/... */
(function () {
  'use strict';
  var R = window.Registro, el = R.el;
  var contenedor = document.getElementById('registro');

  var tabla = new R.Tabla(contenedor, {
    vacio: 'Todavía no hay períodos de medición en el registro.',
    siguiente: function (p) {
      return p.abierto
        ? 'mientras siga abierto, el técnico registra y corrige mediciones (C1). Solo Gerencia lo cierra.'
        : 'sus mediciones quedan fijas; una corrección se pide como enmienda (C4). Solo Gerencia lo vuelve a abrir.';
    },
    estado: function (p) { return p.abierto ? { texto: 'Abierto', tono: 'aprobado' } : { texto: 'Cerrado', tono: 'denegado' }; },
    columnas: [
      { titulo: 'Período', valor: function (p) { return el('code', { text: p.etiqueta }); } },
      { titulo: 'Inicio', clase: 'num', valor: function (p) { return p.inicio; } },
      { titulo: 'Fin', clase: 'num', valor: function (p) { return p.fin; } },
    ],
    acciones: function (p) {
      var base = '/api/periodos/' + p.id + '/';
      return p.abierto
        ? [{ verbo: 'Cerrar', exito: 'Cerrado', url: base + 'cerrar/', quien: 'Gerencia de Certificación',
             despues: 'Ya no se registran ni corrigen mediciones en él; el técnico puede pedir enmiendas (C4).' }]
        : [{ verbo: 'Abrir', exito: 'Abierto', url: base + 'abrir/', quien: 'Gerencia de Certificación',
             despues: 'Se vuelven a registrar y corregir mediciones en él (C1).' }];
    },
    alCambiar: cargar,
  });

  async function cargar() {
    var res = await R.api('GET', '/api/periodos/');
    if (!res.ok) { R.negacionDeLectura(contenedor, res, 'períodos', 'cualquier rol'); return; }
    tabla.pintar(res.datos);
  }

  cargar();
})();
