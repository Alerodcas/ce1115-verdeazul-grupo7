/* Bitácora: lectura con filtros y verificación de la cadena. Solo lectura. */
(function () {
  'use strict';
  var R = window.Registro, el = R.el;
  var contenedor = document.getElementById('registro');
  var LIMITE = 50;
  var desplazamiento = 0, total = 0, filtros = {};

  var RESULTADOS = {
    exito: { texto: 'Éxito', tono: 'aprobado' },
    denegado: { texto: 'Denegado', tono: 'denegado' },
    fallo: { texto: 'Fallo', tono: 'denegado' },
  };

  function corto(h) { return String(h || '').slice(0, 12); }

  var siguientes = new Map(); // id -> hash de la entrada inmediatamente anterior en la página

  var tabla = new R.Tabla(contenedor, {
    vacio: 'Ninguna entrada coincide con esos filtros. Quite alguno para ver más.',
    estado: function (e) { return RESULTADOS[e.resultado] || { texto: e.resultado, tono: 'ink' }; },
    columnas: [
      { titulo: 'Entrada', valor: function (e) { return el('code', { text: '#' + e.id }); } },
      // Hora local, como las constancias de esta misma página; el valor UTC queda en el título.
      { titulo: 'Ocurrió (hora local)', clase: 'num', valor: function (e) {
        return el('time', { datetime: e.ocurrido_en, title: R.fechaHoraUtc(e.ocurrido_en), text: R.fechaHora(e.ocurrido_en, true) });
      } },
      { titulo: 'Actor', valor: function (e) { return e.actor === 'anonimo' ? 'anónimo' : R.persona(e.actor); } },
      { titulo: 'Rol activo', valor: function (e) { return e.rol_activo || el('span', { class: 'suave', text: 'ninguno' }); } },
      { titulo: 'Acción', valor: function (e) { return el('code', { text: e.accion }); } },
      { titulo: 'Objeto', valor: function (e) { return e.objeto_tipo ? el('span', null, e.objeto_tipo + ' ', e.objeto_id ? el('code', { text: '#' + e.objeto_id }) : '') : ''; } },
      { titulo: 'Regla', valor: function (e) { return e.rule_id ? R.chipRegla(e.rule_id, e.rule_ver) : el('span', { class: 'suave', text: 'sin regla' }); } },
      { titulo: 'Cadena', valor: function (e) {
        var anterior = siguientes.get(e.id);
        var marca = anterior === undefined ? null
          : (anterior === e.hash_previo ? el('span', { class: 'encadena', text: 'Enlaza' }) : el('span', { class: 'no-encadena', text: 'No enlaza' }));
        return el('div', null,
          el('div', { class: 'hash', title: e.hash_previo }, 'previo ', corto(e.hash_previo)),
          el('div', { class: 'hash', title: e.hash }, 'propio ', corto(e.hash)),
          marca);
      } },
    ],
  });

  async function cargar() {
    var q = new URLSearchParams(Object.assign({ limite: LIMITE, desplazamiento: desplazamiento }, filtros));
    var res = await R.api('GET', '/bitacora/?' + q.toString());
    if (!res.ok) { R.negacionDeLectura(contenedor, res, 'la bitácora', 'Auditor externo o Gerencia de Certificación'); actualizarPaginacion(); return; }
    total = res.datos.total;
    var filas = res.datos.resultados;
    // Orden descendente: la entrada anterior de la fila i es la fila i+1, si es consecutiva.
    siguientes = new Map();
    for (var i = 0; i + 1 < filas.length; i++) {
      if (filas[i + 1].id === filas[i].id - 1) siguientes.set(filas[i].id, filas[i + 1].hash);
    }
    tabla.pintar(filas);
    actualizarPaginacion();
  }

  function actualizarPaginacion() {
    var hasta = Math.min(desplazamiento + LIMITE, total);
    document.getElementById('pagina').textContent = total ? (desplazamiento + 1) + ' a ' + hasta + ' de ' + total : '';
    document.getElementById('mas-recientes').disabled = desplazamiento === 0;
    document.getElementById('mas-antiguas').disabled = hasta >= total;
  }

  document.getElementById('mas-recientes').addEventListener('click', function () { desplazamiento = Math.max(0, desplazamiento - LIMITE); cargar(); });
  document.getElementById('mas-antiguas').addEventListener('click', function () { desplazamiento += LIMITE; cargar(); });

  document.getElementById('filtros').addEventListener('submit', function (ev) {
    ev.preventDefault();
    filtros = {};
    var malo = null;
    new FormData(ev.target).forEach(function (v, k) {
      var t = String(v).trim();
      if (!t) return;
      if (k === 'actor') {
        // Se escribe el nombre; la bitácora guarda el número.
        var id = R.idDeUsuario(t);
        if (id === null) { malo = t; return; }
        t = String(id);
      }
      filtros[k] = t;
    });
    var campoActor = ev.target.querySelector('[name="actor"]');
    if (malo !== null) {
      campoActor.setAttribute('aria-invalid', 'true');
      R.constancia(document.getElementById('constancias-filtros'), { tipo: 'error', accion: 'Filtrar', veredicto: 'No se filtró', marca: 'formulario',
        texto: 'No hay una cuenta activa llamada «' + malo + '». Elija un nombre de la lista o escriba el número de usuario.' });
      campoActor.focus();
      return;
    }
    campoActor.removeAttribute('aria-invalid');
    desplazamiento = 0;
    cargar();
  });

  document.getElementById('verificar-cadena').addEventListener('click', async function (ev) {
    var boton = ev.currentTarget;
    if (boton.disabled) return;
    R.ocupado([boton], true);
    var res = await R.api('GET', '/bitacora/verificar/');
    R.ocupado([boton], false);
    var lista = document.getElementById('constancias-cadena');
    var accion = { verbo: 'Verificar cadena', exito: 'Íntegra' };
    var c;
    if (res.datos && res.datos.ok === true) {
      c = R.interpretar(res, accion);
      c.marca = 'SHA-256'; c.regla = null;
      c.texto = 'Se revisaron ' + res.datos.revisadas + ' entradas: cada hash coincide con su contenido y con la entrada anterior.';
    } else if (res.estado === 409 && res.datos) {
      c = { tipo: 'denegada', accion: accion.verbo, veredicto: 'Rota', marca: 'SHA-256',
            texto: 'La cadena se rompe en la entrada #' + res.datos.primera_rota + ': ' + res.datos.motivo + '. Revisadas: ' + res.datos.revisadas + '.' };
    } else {
      c = R.interpretar(res, accion);
    }
    var li = R.constancia(lista, c);
    await cargar();
    R.enfocar(li);
  });

  cargar();
})();
