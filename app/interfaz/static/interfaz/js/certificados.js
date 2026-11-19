/* Certificados: emitir, verificar y verificar con un dato alterado.
   Todo por /certificados/...; la verificación la hace el servidor, no el navegador. */
(function () {
  'use strict';
  var R = window.Registro, el = R.el;
  var contenedor = document.getElementById('registro');
  var SIN_PEP = 'Este servicio no consulta la matriz: solo exige una sesión iniciada.';
  var ALGORITMO = 'RSA-PSS SHA-256';
  var periodos = new Map();
  var mediciones = new Map();
  var fincas = new Map();

  function uuidDeFinca(id) { return '00000000-0000-0000-0000-' + String(id).padStart(12, '0'); }

  /** Del UUID del módulo de certificados al número de finca del registro, si sigue el patrón. */
  function fincaDeUuid(uuid) {
    var m = /^0{8}-0{4}-0{4}-0{4}-(\d{12})$/.exec(String(uuid || ''));
    return m ? String(Number(m[1])) : null;
  }

  /** Nombre de la finca para mostrar; el UUID queda en el título, nunca como texto a leer. */
  function nombreFinca(uuid) {
    var id = fincaDeUuid(uuid);
    var f = id && fincas.get(id);
    var texto = f ? f.nombre : (id ? 'Finca #' + id : 'Finca externa');
    return el('span', { title: 'Identificador del módulo de certificados: ' + uuid, text: texto });
  }

  function paqueteDe(c) {
    return { canonical_data: c.canonical_data, sign_digital: c.sign_digital, public_key_pem: c.public_key_pem };
  }

  /** La verificación responde 200 (válido) o 400 (rechazado): no es una decisión de la matriz. */
  function interpretarVerificacion(res, accion, hechos) {
    var c = { accion: accion.verbo, hechos: hechos || [], marca: ALGORITMO };
    if (res.datos && res.datos.valido === true) {
      c.tipo = 'exito'; c.veredicto = 'Válido';
      c.texto = 'La firma coincide con el contenido: el certificado no fue alterado.';
    } else if (res.datos && res.datos.valido === false) {
      c.tipo = 'denegada'; c.veredicto = 'Rechazado';
      c.texto = 'La firma no coincide con el contenido: el certificado fue alterado o no lo emitió este sistema.';
    } else {
      return R.interpretar(res, accion, hechos);
    }
    return c;
  }

  function alterar(c) {
    var copia = JSON.parse(JSON.stringify(c.canonical_data || {}));
    var antes = copia.tons_co2;
    var despues = Math.round((Number(antes) + 1) * 100) / 100;
    // Mismo tipo que el firmado (texto con dos decimales): solo cambia el valor.
    copia.tons_co2 = typeof antes === 'string' ? despues.toFixed(2) : despues;
    return { datos: { canonical_data: copia, sign_digital: c.sign_digital, public_key_pem: c.public_key_pem },
             hecho: 'Dato alterado antes de verificar: tons_co2 pasó de ' + antes + ' a ' + copia.tons_co2 + '.' };
  }

  var tabla = new R.Tabla(contenedor, {
    vacio: 'Todavía no hay certificados emitidos. Emita el primero a partir de una medición aprobada.',
    estado: function (c) { return c.status === 'VIGENTE' ? { texto: 'Vigente', tono: 'aprobado' } : { texto: R.capital(String(c.status).toLowerCase()), tono: 'denegado' }; },
    columnas: [
      { titulo: 'Certificado', valor: function (c) { return el('code', { title: c.id, text: String(c.id).slice(0, 8) }); } },
      { titulo: 'Período', valor: function (c) { return c.period_name || el('code', { text: String(c.period).slice(0, 8) }); } },
      { titulo: 'Finca', valor: function (c) { return nombreFinca(c.finca_id); } },
      { titulo: 'Parcela', valor: function (c) { return el('code', { text: c.parcela_id }); } },
      { titulo: 'tCO2', clase: 'num', valor: function (c) { return c.tons_co2; } },
      { titulo: 'Emitido por', valor: function (c) { return R.persona(c.emitted_by); } },
      { titulo: 'Emitido', clase: 'num', valor: function (c) { return R.fechaHora(c.emitted_date); } },
    ],
    acciones: function (c) {
      var alterado = alterar(c);
      return [
        { verbo: 'Verificar', exito: 'Válido', url: '/certificados/verificar/', datos: paqueteDe(c), interpretar: interpretarVerificacion },
        { verbo: 'Verificar alterado', exito: 'Válido', url: '/certificados/verificar/', datos: alterado.datos, hechos: [alterado.hecho], interpretar: interpretarVerificacion },
        { verbo: 'Llevar al verificador', enlace: '#t-verificar', paquete: paqueteDe(c) },
      ];
    },
  });

  // «Llevar al verificador» copia el certificado al panel, listo para editarlo.
  contenedor.addEventListener('click', function (ev) {
    var a = ev.target.closest('a[href="#t-verificar"]');
    if (!a) return;
    ev.preventDefault();
    var id = a.closest('tbody').querySelector('td:nth-child(2) code').title;
    var c = certificados.get(id);
    if (!c) return;
    document.getElementById('campo-certificado').value = JSON.stringify(paqueteDe(c), null, 2);
    document.getElementById('t-verificar').scrollIntoView();
    document.getElementById('campo-certificado').focus();
  });

  var certificados = new Map();

  async function cargar() {
    var res = await R.api('GET', '/certificados/certificados/');
    if (!res.ok) { R.negacionDeLectura(contenedor, res, 'certificados'); return; }
    var filas = Array.isArray(res.datos) ? res.datos : (res.datos.results || []);
    certificados = new Map(filas.map(function (c) { return [String(c.id), c]; }));
    tabla.pintar(filas);
  }

  async function cargarPeriodos() {
    var lista = await R.lista('/certificados/periodos/');
    var abiertos = (lista || []).filter(function (p) { return p.status === 'ABIERTO'; });
    periodos = R.porId(lista);
    document.getElementById('form-periodo').classList.toggle('oculto', !!abiertos.length || lista === null);
    R.selector(document.getElementById('campo-period'),
      lista && abiertos.map(function (p) { return { valor: p.id, texto: p.name + ' (' + p.year + ')' }; }),
      'No hay períodos de certificación abiertos');
  }

  async function cargarMediciones() {
    var lista = await R.lista('/api/mediciones/');
    var aprobadas = (lista || []).filter(function (m) { return m.estado === 'aprobada'; });
    mediciones = R.porId(aprobadas);
    var select = document.getElementById('campo-medicion');
    R.vaciar(select).append(el('option', { value: '', text: aprobadas.length ? 'Elija una medición' : 'No hay mediciones aprobadas en su alcance' }));
    aprobadas.forEach(function (m) {
      var f = fincas.get(String(m.finca));
      select.append(el('option', { value: m.id, text: '#' + m.id + ' v' + m.version + ', ' + (f ? f.nombre : 'finca #' + m.finca) + ', ' + m.valor + ' ' + m.unidad }));
    });
  }

  document.getElementById('campo-medicion').addEventListener('change', function (ev) {
    var m = mediciones.get(ev.target.value);
    var salida = document.getElementById('finca-elegida');
    if (!m) { document.getElementById('campo-finca-id').value = ''; salida.textContent = 'Se toma de la medición que elija.'; return; }
    var f = fincas.get(String(m.finca));
    document.getElementById('campo-finca-id').value = uuidDeFinca(m.finca);
    salida.textContent = f ? f.nombre : 'Finca #' + m.finca;
    document.getElementById('campo-tons').value = Number(m.valor).toFixed(2);
  });

  R.formulario(document.getElementById('form-periodo'), {
    verbo: 'Abrir período de certificación', exito: 'Abierto', url: '/certificados/periodos/', sinPep: SIN_PEP,
    datos: function (fd) { return { name: fd.get('name'), year: fd.get('year'), status: 'ABIERTO' }; },
    alTerminar: cargarPeriodos,
  });

  R.formulario(document.getElementById('form-emitir'), {
    verbo: 'Emitir certificado', exito: 'Emitido', url: '/certificados/emitir/', sinPep: SIN_PEP,
    datos: function (fd) {
      // El campo de la finca es oculto: si no hay medición elegida, se dice aquí y no se envía.
      if (!fd.get('finca_id')) return R.rechazo(document.getElementById('campo-medicion'), 'Elija una medición aprobada: la finca se toma de ella.');
      return { period: fd.get('period'), finca_id: fd.get('finca_id'), parcela_id: fd.get('parcela_id'), tons_co2: fd.get('tons_co2') };
    },
    textoExito: function (c) { return 'Certificado ' + String(c.id).slice(0, 8) + ' firmado.'; },
    alTerminar: cargar,
  });

  R.formulario(document.getElementById('form-verificar'), {
    verbo: 'Verificar', exito: 'Válido', url: '/certificados/verificar/', interpretar: interpretarVerificacion,
    datos: function (fd) {
      try { return JSON.parse(fd.get('certificado')); } catch (e) { return { canonical_data: null }; }
    },
  });

  // Los nombres de finca primero: los usan el selector de mediciones y el registro.
  R.lista('/api/fincas/').then(function (lista) {
    fincas = R.porId(lista);
    cargarPeriodos();
    cargarMediciones();
    cargar();
  });
})();
