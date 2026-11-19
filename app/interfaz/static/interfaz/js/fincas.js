/* Fincas: inscribir, leer la ficha y desactivar. Todo por /api/fincas/... */
(function () {
  'use strict';
  var R = window.Registro, el = R.el;
  var contenedor = document.getElementById('registro');

  var tabla = new R.Tabla(contenedor, {
    vacio: function () {
      return R.sesion.rol === 'Tecnico de campo'
        ? 'No tiene fincas asignadas, y S1 solo le muestra las asignadas.'
        : R.sesion.rol === 'Dueno de finca'
          ? 'No hay fincas a su nombre, y S2 solo le muestra las suyas.'
          : 'No hay fincas inscritas. Un Administrador inscribe la primera con el formulario de arriba.';
    },
    estado: function (f) { return f.activa ? { texto: 'Activa', tono: 'aprobado' } : { texto: 'Inactiva', tono: 'denegado' }; },
    columnas: [
      { titulo: 'Finca', valor: function (f) { return el('span', null, el('code', { text: '#' + f.id }), ' ' + f.nombre); } },
      { titulo: 'Ubicación', valor: function (f) { return f.ubicacion || el('span', { class: 'suave', text: 'sin indicar' }); } },
      { titulo: 'Área (ha)', clase: 'num', valor: function (f) { return f.area_ha; } },
      { titulo: 'Propietario', valor: function (f) { return R.persona(f.propietario); } },
      { titulo: 'Inscrita', clase: 'num', valor: function (f) { return R.fechaHora(f.creada_en); } },
    ],
    acciones: function (f) {
      var base = '/api/fincas/' + f.id + '/';
      var a = [{ verbo: 'Leer ficha', exito: 'Leída', metodo: 'GET', url: base }];
      if (f.activa) a.push({ verbo: 'Desactivar', exito: 'Desactivada', url: base + 'desactivar/', quien: 'Administrador',
        despues: 'La finca queda en el registro, inactiva: no se borra.' });
      return a;
    },
    alCambiar: cargar,
  });

  async function cargar() {
    var res = await R.api('GET', '/api/fincas/');
    if (!res.ok) { R.negacionDeLectura(contenedor, res, 'fincas', 'cualquier rol, dentro de su alcance'); return; }
    tabla.pintar(res.datos);
  }

  R.formulario(document.getElementById('form-nueva'), {
    verbo: 'Inscribir finca', exito: 'Inscrita', url: '/api/fincas/nueva/', quien: 'Administrador',
    datos: function (fd, form) {
      // El propietario se escribe por nombre; la API recibe su número.
      var propietario = R.campoUsuario(form, 'propietario');
      if (propietario && propietario.rechazo) return propietario;
      return { nombre: fd.get('nombre'), ubicacion: fd.get('ubicacion'), area_ha: fd.get('area_ha'), propietario: propietario };
    },
    textoExito: function (f) { return 'Finca #' + f.id + ' inscrita.'; },
    alTerminar: cargar,
  });

  cargar();
})();
