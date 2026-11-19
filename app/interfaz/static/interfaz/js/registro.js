/* =============================================================================
   Registro: utilidades comunes de la interfaz. Sin dependencias externas.

   Tres reglas de este archivo:
   1. Todo dato se pinta con textContent, nunca con innerHTML.
   2. Toda acción y todo listado va a la API existente con la cookie de sesión.
      La interfaz no decide nada: muestra lo que decidió el PEP.
   3. El token CSRF se lee del formulario renderizado ({% csrf_token %}), nunca
      de una cookie por nombre (en producción se llama __Host-csrftoken).
   ============================================================================= */
(function () {
  'use strict';

  var cuerpo = document.body;
  var sesion = {
    usuarioId: Number(cuerpo.dataset.usuarioId || 0),
    usuario: cuerpo.dataset.usuario || '',
    rol: cuerpo.dataset.rol || '',
    urlEntrar: cuerpo.dataset.urlEntrar || '/entrar/',
    urlMfa: cuerpo.dataset.urlMfa || '/segundo-factor/',
    urlRol: cuerpo.dataset.urlRol || '/rol/',
    urlDirectorio: cuerpo.dataset.directorio || '',
    otrosRoles: cuerpo.dataset.otrosRoles === '1',
    ruta: cuerpo.dataset.ruta || location.pathname,
    mfaHasta: Date.now() + Number(cuerpo.dataset.mfaRestante || 0) * 1000,
  };

  function mfaVigente() { return Date.now() < sesion.mfaHasta; }

  // ------------------------------------------------------------------ DOM --
  function el(etiqueta, props) {
    var n = document.createElement(etiqueta);
    if (props) {
      Object.keys(props).forEach(function (k) {
        var v = props[k];
        if (v === null || v === undefined || v === false) return;
        if (k === 'class') n.className = v;
        else if (k === 'text') n.textContent = v;
        else if (k.slice(0, 2) === 'on') n.addEventListener(k.slice(2), v);
        else n.setAttribute(k, v === true ? '' : String(v));
      });
    }
    for (var i = 2; i < arguments.length; i++) agregar(n, arguments[i]);
    return n;
  }

  function agregar(n, hijo) {
    if (hijo === null || hijo === undefined || hijo === false) return;
    if (Array.isArray(hijo)) { hijo.forEach(function (h) { agregar(n, h); }); return; }
    n.append(hijo instanceof Node ? hijo : document.createTextNode(String(hijo)));
  }

  function vaciar(n) { while (n.firstChild) n.removeChild(n.firstChild); return n; }

  // ------------------------------------------------------------------ API --
  function tokenCsrf() {
    var campo = document.querySelector('input[name="csrfmiddlewaretoken"]');
    return campo ? campo.value : '';
  }

  /** Llama a la API. Nunca lanza: devuelve {ok, estado, datos, decision, red}. */
  async function api(metodo, url, datos) {
    var opciones = { method: metodo, credentials: 'same-origin', headers: { Accept: 'application/json' } };
    if (metodo !== 'GET' && metodo !== 'HEAD') {
      opciones.headers['Content-Type'] = 'application/json';
      opciones.headers['X-CSRFToken'] = tokenCsrf();
      opciones.body = JSON.stringify(datos || {});
    }
    var r;
    try {
      r = await fetch(url, opciones);
    } catch (e) {
      return { ok: false, estado: 0, datos: null, decision: null, red: true };
    }
    var cuerpoRespuesta = null;
    var tipo = r.headers.get('Content-Type') || '';
    try {
      cuerpoRespuesta = tipo.indexOf('json') >= 0 ? await r.json() : { detail: (await r.text()).slice(0, 300) };
    } catch (e) { cuerpoRespuesta = null; }
    var regla = r.headers.get('X-Authz-Regla');
    var decision = regla ? {
      permitido: r.headers.get('X-Authz-Permitido') === '1',
      regla: regla,
      version: r.headers.get('X-Authz-Version') || '',
      obligaciones: (r.headers.get('X-Authz-Obligaciones') || '').split(',').filter(Boolean),
    } : null;
    return { ok: r.ok, estado: r.status, datos: cuerpoRespuesta, decision: decision, red: false };
  }

  // -------------------------------------------------------------- reglas --
  // Una línea por regla, en el lenguaje de la matriz de la Parte 1. «niega» se usa
  // cuando la regla negó; «permite» cuando concedió.
  var REGLAS = {
    MATRIZ_SIMPLE: {
      permite: 'Celda incondicional de la matriz: el rol activo tiene esta acción sobre este objeto.',
      niega: 'Celda incondicional de la matriz.',
    },
    DENY_DEFAULT: {
      niega: 'Ninguna celda de la matriz le da esta acción al rol activo, así que se niega por omisión.',
    },
    FAIL_CLOSED: {
      niega: 'El motor de decisión no respondió, y sin respuesta el sistema niega (falla cerrada).',
    },
    C1: {
      permite: 'C1: el técnico trabaja sus propias mediciones, en una finca asignada y con el período abierto.',
      niega: 'C1: el técnico solo crea o edita sus propias mediciones, en una finca que tenga asignada (S1), con el período abierto y en borrador o devuelta.',
    },
    C2: {
      permite: 'C2: medición enviada, que este verificador no creó ni editó, con segundo factor reciente.',
      niega: 'C2: el verificador solo aprueba o devuelve mediciones enviadas que no creó ni editó, y con el segundo factor confirmado en los últimos 5 minutos.',
    },
    C3: {
      permite: 'C3: medición aprobada, sin certificado vigente previo, emitido por alguien que no es su autor.',
      niega: 'C3: el certificado se emite sobre una medición aprobada, sin otro vigente para la misma parcela y período, y no lo emite su autor.',
    },
    C4: {
      permite: 'C4: enmienda con motivo escrito sobre un período cerrado, resuelta por alguien distinto de quien la pidió.',
      niega: 'C4: la enmienda la pide el técnico con motivo escrito y con el período cerrado; la autoriza Gerencia, que no puede ser quien la pidió.',
    },
    C5: {
      permite: 'C5: finca asignada al técnico (S1), dentro del límite de lecturas de 24 horas.',
      niega: 'C5: el técnico solo lee fincas que tiene asignadas (S1); pasadas 20 lecturas en 24 horas pide segundo factor y pasadas 60 se bloquea.',
    },
    C6: {
      permite: 'C6: cambio de cuenta con solicitud escrita, sobre la cuenta de otra persona.',
      niega: 'C6: todo cambio de cuenta exige solicitud escrita; el Administrador ejecuta, nunca sobre su propia cuenta, y Gerencia aprueba si no es quien ejecuta.',
    },
    S1: {
      permite: 'S1: finca asignada al técnico.',
      niega: 'S1: el técnico solo ve las fincas que tiene asignadas.',
    },
    S2: {
      permite: 'S2: el dueño ve lo de sus propias fincas.',
      niega: 'S2: el dueño solo ve lo de las fincas que son suyas.',
    },
  };

  /**
   * Qué hacer después de una negación, cuando se puede saber.
   *
   * No adivina la causa. Solo nombra una condición concreta cuando la decisión o la
   * sesión la demuestran: el segundo factor se menciona únicamente si la decisión trae
   * la obligación «mfa_reciente» Y la sesión no lo tiene confirmado. En cualquier otro
   * caso enumera las condiciones de la regla, sin elegir una como la causa.
   */
  function siguientePaso(regla, accion, c, d) {
    // Una acción puede afinar el texto de una regla: {siguiente: {C4: '…'}}.
    if (accion.siguiente && accion.siguiente[regla]) return accion.siguiente[regla];
    var obligaciones = (d && d.obligaciones) || [];
    var faltaMfa = obligaciones.indexOf('mfa_reciente') >= 0 && !mfaVigente();
    if (faltaMfa) c.enlaceMfa = true;
    switch (regla) {
      case 'DENY_DEFAULT':
        if (sesion.otrosRoles) c.enlaceRol = true;
        return accion.quien
          ? 'Esta acción le corresponde a ' + accion.quien + '. Si usted tiene ese rol, cámbielo y repita la acción.'
          : 'Ningún permiso de su rol activo cubre esta acción. Si tiene otro rol, cámbielo y repita.';
      case 'C1':
        return 'C1 exige todas estas condiciones: la finca está asignada a usted, el período está abierto, y la medición es suya y está en borrador o devuelta. Con el período cerrado, la corrección se pide como enmienda.';
      case 'C2':
        return 'C2 exige todas estas condiciones: la medición está enviada, usted no la creó ni la editó, y confirmó el segundo factor en los últimos 5 minutos.'
          + (faltaMfa ? ' Su segundo factor no está confirmado ahora: confírmelo y repita.' : '')
          + ' Si usted la creó o la editó, la tiene que aprobar otro verificador.';
      case 'C4':
        return 'C4 exige: para pedirla, el período cerrado (lo cierra Gerencia en Períodos), el motivo escrito y la finca asignada a usted; para autorizarla, alguien de Gerencia distinto de quien la pidió.';
      case 'C5':
        if (faltaMfa) {
          return 'La decisión pide segundo factor reciente porque hubo más de 20 lecturas de fincas en 24 horas: confírmelo y repita. Además, la finca tiene que estar asignada a usted (S1).';
        }
        if (obligaciones.indexOf('alerta_frecuencia_c5') >= 0 && obligaciones.indexOf('mfa_reciente') < 0) {
          return 'La decisión marca más de 60 lecturas de fincas en 24 horas: C5 bloquea la lectura hasta que pase el plazo, y el segundo factor no lo cambia.';
        }
        return 'C5 exige ambas condiciones: que la finca esté asignada a usted (S1) y que no se pase el límite de lecturas en 24 horas (hasta 20, sin más; de 21 a 60, con segundo factor reciente; más de 60, bloqueada). Si no tiene la finca asignada, pida que se la asignen.';
      case 'C6':
        return 'C6 exige una solicitud escrita y que el cambio sea sobre la cuenta de otra persona: nadie pide, aprueba ni ejecuta cambios sobre su propia cuenta.';
      case 'S1':
        return 'Solo verá las fincas que tiene asignadas. Si le falta una, pida que se la asignen.';
      case 'S2':
        return 'Solo verá lo de las fincas que son suyas.';
      case 'FAIL_CLOSED':
        return 'Intente de nuevo en un momento. Si se repite, avise a soporte con la hora de esta constancia.';
      case 'VISTA':
        return 'Esta separación de funciones exige otra persona: pídale a alguien con ese rol que lo haga.';
      default:
        return '';
    }
  }

  function explicar(regla, permitido) {
    var r = REGLAS[regla];
    if (!r) return permitido ? 'Permitida por la regla ' + regla + '.' : 'Negada por la regla ' + regla + '.';
    return (permitido ? r.permite : r.niega) || r.niega || r.permite;
  }

  var CAMPOS = {
    finca: 'Finca', periodo: 'Período', valor: 'Valor', unidad: 'Unidad', nombre: 'Nombre',
    ubicacion: 'Ubicación', area_ha: 'Área', propietario: 'Propietario', medicion: 'Medición',
    motivo: 'Motivo', valor_propuesto: 'Valor propuesto', usuario: 'Usuario', tipo: 'Tipo',
    rol_solicitado: 'Rol solicitado', solicitud: 'Solicitud escrita', period: 'Período de certificación',
    finca_id: 'Finca', parcela_id: 'Parcela', tons_co2: 'Toneladas de CO2', name: 'Nombre', year: 'Año',
    status: 'Estado', canonical_data: 'Contenido', sign_digital: 'Firma', public_key_pem: 'Clave pública',
  };

  function aplanarErrores(datos) {
    if (!datos || typeof datos !== 'object') return '';
    if (typeof datos.detail === 'string') return datos.detail;
    return Object.keys(datos).map(function (campo) {
      var v = datos[campo];
      var texto = Array.isArray(v) ? v.join(' ') : (typeof v === 'object' ? aplanarErrores(v) : String(v));
      return campo === 'non_field_errors' ? texto : (CAMPOS[campo] || campo) + ': ' + texto;
    }).join(' ');
  }

  /**
   * Traduce la respuesta de la API en una constancia.
   * accion = {verbo: 'Aprobar', exito: 'Aprobada'}; hechos = datos del registro y de
   * la sesión que ayudan a leer la decisión (no la explican por su cuenta).
   */
  function interpretar(res, accion, hechos) {
    var c = { accion: accion.verbo, hechos: (hechos || []).slice() };
    var d = res.decision;
    if (res.ok) {
      c.tipo = 'exito';
      c.veredicto = accion.exito;
      if (d) { c.regla = d.regla; c.version = d.version; c.texto = explicar(d.regla, true); }
      else { c.texto = accion.sinPep || 'Hecho.'; }
      if (accion.despues) c.siguiente = typeof accion.despues === 'function' ? accion.despues(res.datos) : accion.despues;
      return c;
    }
    var detalle = (res.datos && typeof res.datos.detail === 'string') ? res.datos.detail : '';
    if (res.red) {
      c.tipo = 'error'; c.veredicto = 'Sin respuesta';
      c.texto = 'No hubo conexión con el servidor. Revise la red e intente de nuevo; la acción no se hizo.';
      return c;
    }
    if (res.estado === 403 || res.estado === 401) {
      if (d && !d.permitido) {
        c.tipo = 'denegada'; c.veredicto = 'Denegada';
        c.regla = d.regla; c.version = d.version;
        c.texto = explicar(d.regla, false);
        // El estado del segundo factor solo se cuenta cuando la decisión lo exige.
        if (d.obligaciones.indexOf('mfa_reciente') >= 0) {
          c.hechos.push(mfaVigente() ? 'Dato de la sesión: segundo factor confirmado.' : 'Dato de la sesión: segundo factor sin confirmar.');
        }
        c.siguiente = siguientePaso(d.regla, accion, c, d);
        return c;
      }
      if (d && d.permitido) {
        // La matriz concedió, pero la vista aplicó una regla del sistema (separación de
        // funciones). Se muestran las dos cosas: quién negó y qué decía la matriz.
        c.tipo = 'sistema'; c.veredicto = 'Denegada';
        c.sistema = true; c.regla = d.regla; c.version = d.version; c.matrizPermitia = true;
        c.texto = (detalle || 'La vista negó la acción.') + ' La matriz lo permitía (' + d.regla + ' v' + d.version + '); lo negó una regla del sistema, no la matriz.';
        c.siguiente = siguientePaso('VISTA', accion, c, d);
        return c;
      }
      if (/credencial|credential|autentica/i.test(detalle)) {
        c.tipo = 'sesion'; c.veredicto = 'Sesión terminada';
        c.texto = 'La sesión ya no está abierta. Entre de nuevo y repita la acción.';
        c.enlaceEntrar = true;
        return c;
      }
      c.tipo = 'denegada'; c.veredicto = 'Denegada';
      c.texto = detalle || 'El servidor negó la acción sin indicar la regla.';
      return c;
    }
    if (res.estado === 404) {
      c.tipo = 'conflicto'; c.veredicto = 'No encontrada';
      c.texto = 'El registro no existe o no está en su alcance: con este rol la consulta solo devuelve lo suyo (S1, S2).';
      return c;
    }
    // 409 y 400: los rechaza una regla del sistema (estado, unicidad, validación), no la
    // matriz. Llevan su propia etiqueta y estilo para que no se confundan con una negación.
    if (res.estado === 409) {
      c.tipo = 'sistema'; c.sistema = true; c.veredicto = 'Sin cambio';
      c.texto = detalle || 'El estado del registro no admite esta acción.';
      // Quien llama puede dar un consejo que el rol pueda seguir (p. ej. si no lee el registro).
      if (accion.sinCambio) c.siguiente = typeof accion.sinCambio === 'function' ? accion.sinCambio(res.datos) : accion.sinCambio;
      else c.texto += ' Actualice el registro y revise su estado.';
      return c;
    }
    if (res.estado === 400) {
      c.tipo = 'sistema'; c.sistema = true; c.veredicto = 'Rechazada';
      c.texto = (aplanarErrores(res.datos) || 'Los datos no son válidos.') + ' Corrija el formulario y vuelva a intentarlo.';
      return c;
    }
    if (res.estado === 503) {
      c.tipo = 'error'; c.veredicto = 'No se hizo';
      c.texto = (detalle || 'Servicio no disponible.') + ' Intente de nuevo en unos minutos.';
      return c;
    }
    c.tipo = 'error'; c.veredicto = 'Error ' + res.estado;
    c.texto = 'El servidor no pudo completar la acción. Intente de nuevo; si se repite, avise a soporte con la hora de esta constancia.';
    return c;
  }

  function hora() {
    var d = new Date();
    return [d.getHours(), d.getMinutes(), d.getSeconds()].map(function (n) { return String(n).padStart(2, '0'); }).join(':');
  }

  /** Chip con la regla de la matriz. fuente y nota son opcionales («Matriz», «permitía»). */
  function chipRegla(regla, version, fuente, nota) {
    return el('span', { class: 'regla', title: nota ? 'Regla de la matriz: ' + nota : 'Regla de la política que decidió' },
      fuente ? el('span', { class: 'regla__fuente', text: fuente }) : null,
      el('code', { text: regla }),
      version ? el('span', { class: 'regla__ver', text: 'v' + version }) : null,
      nota ? el('span', { class: 'regla__ver', text: nota }) : null);
  }

  /** Quién decidió, a la vista: la matriz (con su regla) o una regla del sistema. */
  function origen(c) {
    if (c.sistema) {
      return el('span', { class: 'origen' },
        el('span', { class: 'regla regla--sistema', title: 'Lo rechazó una regla del sistema (estado, unicidad, separación de funciones), no la matriz de acceso', text: 'Regla del sistema' }),
        c.regla ? chipRegla(c.regla, c.version, 'Matriz', c.matrizPermitia ? 'permitía' : '') : null);
    }
    if (c.regla) return chipRegla(c.regla, c.version, 'Matriz');
    if (c.marca) return el('span', { class: 'regla', text: c.marca });
    return el('span', { class: 'suave', text: 'sin regla' });
  }

  /**
   * Agrega una constancia a una lista <ol class="constancias">. No se borra sola.
   * Además de la regla y su explicación puede llevar «Qué hacer» (negaciones) o
   * «Siguiente» (éxitos), con enlaces al segundo factor, a cambiar de rol o a entrar.
   */
  function constancia(lista, c) {
    var li = el('li', { class: 'constancia constancia--' + c.tipo + ' nueva', tabindex: '-1' },
      el('time', { text: hora() }),
      el('span', { class: 'constancia__accion', text: c.accion }),
      el('strong', { class: 'constancia__veredicto', text: c.veredicto }),
      origen(c),
      el('span', { class: 'constancia__texto', text: c.texto }));
    var enlaces = [];
    if (c.enlaceMfa) enlaces.push(el('a', { href: sesion.urlMfa + '?next=' + encodeURIComponent(sesion.ruta), text: 'Confirmar segundo factor' }));
    if (c.enlaceRol) enlaces.push(el('a', { href: sesion.urlRol + '?cambiar=1&next=' + encodeURIComponent(sesion.ruta), text: 'Cambiar de rol' }));
    if (c.enlaceEntrar) enlaces.push(el('a', { href: sesion.urlEntrar + '?aviso=sesion&next=' + encodeURIComponent(sesion.ruta), text: 'Entrar de nuevo' }));
    if (c.siguiente || enlaces.length) {
      li.append(el('span', { class: 'constancia__siguiente' },
        el('strong', { text: c.tipo === 'exito' ? 'Siguiente: ' : 'Qué hacer: ' }),
        c.siguiente ? c.siguiente + ' ' : '',
        enlaces.map(function (a, i) { return i ? [' · ', a] : a; })));
    }
    if ((c.hechos || []).length) li.append(el('span', { class: 'constancia__datos', text: c.hechos.join(' ') }));
    lista.append(li);
    var fila = lista.closest('tbody');
    if (fila) { fila.classList.add('con-constancias'); lista.closest('tr').classList.remove('vacia'); }
    setTimeout(function () { li.classList.remove('nueva'); }, 50);
    return li;
  }

  /** Lleva el foco (y la vista) a la constancia recién escrita. */
  function enfocar(li) {
    if (li && li.isConnected) li.focus();
  }

  /** Marca botones como ocupados mientras va la petición: evita el doble envío. */
  function ocupado(botones, si) {
    botones.forEach(function (b) {
      if (!b) return;
      b.disabled = si;
      if (si) { b.setAttribute('aria-busy', 'true'); b.dataset.texto = b.textContent; b.textContent = b.textContent + '…'; }
      else { b.removeAttribute('aria-busy'); if (b.dataset.texto) b.textContent = b.dataset.texto; }
    });
  }

  /** Mientras se recarga un registro: atenuado y anunciado como ocupado. */
  async function recargando(contenedor, fn) {
    contenedor.setAttribute('aria-busy', 'true');
    contenedor.classList.add('recargando');
    try { await fn(); } finally {
      contenedor.removeAttribute('aria-busy');
      contenedor.classList.remove('recargando');
    }
  }

  /** Cuando se niega leer la colección entera: lo dice en grande, con su regla. */
  function negacionDeLectura(contenedor, res, que, quien) {
    var c = interpretar(res, { verbo: 'Leer ' + que, exito: 'Leída', quien: quien });
    var bloque = el('div', { class: c.tipo === 'denegada' ? 'negacion' : 'vacio', role: 'status' },
      el('h2', { text: c.tipo === 'denegada' ? 'Su rol activo no puede leer ' + que : 'No se pudo leer ' + que }));
    var lista = el('ol', { class: 'constancias' });
    bloque.append(lista);
    constancia(lista, c);
    if (c.tipo === 'denegada') {
      bloque.append(el('p', { class: 'nota', text: 'La decisión depende del rol activo: con otro rol, el mismo servidor puede responder distinto.' }));
    }
    vaciar(contenedor).append(bloque);
  }

  // -------------------------------------------------------- directorio --
  // id → nombre de usuario, para mostrar personas. Solo lo piden los roles que lo usan
  // (data-directorio); si no hay, se muestra «#id». No decide nada.
  var directorio = new Map();
  var porNombre = new Map();
  var directorioListo = !sesion.urlDirectorio ? Promise.resolve() : api('GET', sesion.urlDirectorio).then(function (res) {
    if (!res.ok || !Array.isArray(res.datos)) return;
    var lista = document.getElementById('lista-usuarios');
    res.datos.forEach(function (u) {
      directorio.set(String(u.id), u.username);
      porNombre.set(String(u.username).toLowerCase(), Number(u.id));
      if (lista) lista.append(el('option', { value: u.username }));
    });
  });

  /**
   * Traduce lo que escribió la persona a un número de usuario.
   * Acepta un nombre del directorio, su propio nombre, o un número («5» o «#5»).
   * Devuelve null si no lo reconoce: entonces no se envía nada.
   */
  function idDeUsuario(texto) {
    var t = String(texto || '').trim();
    if (!t) return null;
    if (/^#?\d+$/.test(t)) return Number(t.replace('#', ''));
    if (t.toLowerCase() === sesion.usuario.toLowerCase()) return sesion.usuarioId;
    return porNombre.has(t.toLowerCase()) ? porNombre.get(t.toLowerCase()) : null;
  }

  /** Lo que devuelve opciones.datos cuando un campo no sirve: no se llama a la API. */
  function rechazo(campo, texto) { return { rechazo: true, campo: campo, texto: texto }; }

  /** Resuelve un campo «persona» del formulario; rechazo() si no existe. */
  function campoUsuario(form, nombre) {
    var campo = form.querySelector('[name="' + nombre + '"]');
    var id = idDeUsuario(campo && campo.value);
    if (id === null) {
      var visto = campo ? campo.value.trim() : '';
      return rechazo(campo, visto
        ? 'No hay una cuenta activa llamada «' + visto + '». Elija un nombre de la lista o escriba el número de usuario.'
        : 'Indique la persona: su nombre de usuario o su número.');
    }
    return id;
  }

  // ---------------------------------------------------------- formateo --
  /** Fecha y hora LOCALES del navegador (como las constancias). conSegundos para la bitácora. */
  function fechaHora(iso, conSegundos) {
    if (!iso) return '';
    var d = new Date(iso);
    if (isNaN(d)) return String(iso);
    var p = function (n) { return String(n).padStart(2, '0'); };
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()) + ' ' + p(d.getHours()) + ':' + p(d.getMinutes())
      + (conSegundos ? ':' + p(d.getSeconds()) : '');
  }

  /** La misma marca en UTC, para el título (tooltip). */
  function fechaHoraUtc(iso) {
    var d = new Date(iso);
    return isNaN(d) ? String(iso || '') : d.toISOString().replace('T', ' ').slice(0, 19) + ' UTC';
  }

  /** Muestra a una persona por su nombre de usuario (o «#id» si no se sabe); si es quien mira, lo dice. */
  function persona(id) {
    if (id === null || id === undefined || id === '') return el('span', { class: 'suave', text: 'nadie' });
    var mismo = Number(id) === sesion.usuarioId;
    var nodo = el('span', { class: mismo ? 'usted' : '' });
    function pintar() {
      vaciar(nodo);
      var nombre = directorio.get(String(id)) || (mismo ? sesion.usuario : '');
      agregar(nodo, nombre ? el('span', { title: 'Usuario #' + id, text: nombre }) : el('code', { text: '#' + id }));
      if (mismo) agregar(nodo, ' (usted)');
    }
    pintar();
    if (!directorio.has(String(id))) directorioListo.then(pintar);
    return nodo;
  }

  function capital(t) { t = String(t || ''); return t.charAt(0).toUpperCase() + t.slice(1); }

  // ------------------------------------------------------------- tabla --
  /**
   * Tabla de registro. La primera columna es el ESTADO.
   * opciones = {
   *   columnas: [{titulo, clase, valor(fila) -> texto|Node}],
   *   estado(fila) -> {texto, tono: 'aprobado'|'denegado'|'borrador'|'ink'},
   *   acciones(fila) -> [{verbo, exito, metodo, url, datos, campo, hechos}],
   *   vacio: texto, alCambiar(): recargar
   * }
   * Las constancias de cada registro sobreviven a la recarga de la tabla.
   */
  function Tabla(contenedor, opciones) {
    this.contenedor = contenedor;
    this.o = opciones;
    this.constancias = new Map();
  }

  Tabla.prototype.listaDe = function (id) {
    if (!this.constancias.has(id)) this.constancias.set(id, el('ol', { class: 'constancias', 'aria-live': 'polite' }));
    return this.constancias.get(id);
  };

  Tabla.prototype.pintar = function (filas) {
    var o = this.o, yo = this;
    if (!filas.length) {
      vaciar(this.contenedor).append(el('p', { class: 'vacio', text: typeof o.vacio === 'function' ? o.vacio() : o.vacio }));
      return;
    }
    var cols = o.columnas;
    var tabla = el('table', { class: 'registro' },
      el('thead', null, el('tr', null,
        el('th', { scope: 'col', text: 'Estado' }),
        cols.map(function (c) { return el('th', { scope: 'col', class: c.clase || null, text: c.titulo }); }),
        o.acciones ? el('th', { scope: 'col', text: 'Acciones' }) : null)));
    filas.forEach(function (f) {
      var est = o.estado(f);
      var lista = yo.listaDe(o.clave ? o.clave(f) : f.id);
      // El paso que sigue en el flujo, en palabras. Es ayuda: quién puede darlo lo decide el PEP.
      var paso = o.siguiente ? o.siguiente(f) : '';
      var abierta = lista.children.length || paso;
      var celdaAcciones = o.acciones ? el('td', { class: 'acciones', 'data-etiqueta': 'Acciones' }) : null;
      var tbody = el('tbody', { class: 'tono-' + (est.tono || 'ink') + (abierta ? ' con-constancias' : '') },
        el('tr', { class: 'fila' },
          el('td', { class: 'estado', text: est.texto }),
          cols.map(function (c) {
            var v = c.valor(f);
            return el('td', { class: c.clase || null, 'data-etiqueta': c.titulo }, v === null || v === undefined ? '' : v);
          }),
          celdaAcciones),
        el('tr', { class: 'fila-constancias' + (abierta ? '' : ' vacia') },
          el('td', { colspan: String(cols.length + (o.acciones ? 2 : 1)) },
            paso ? el('p', { class: 'paso' }, el('strong', { text: 'Siguiente paso: ' }), paso) : null,
            lista)));
      if (celdaAcciones) yo.pintarAcciones(celdaAcciones, f, lista);
      tabla.append(tbody);
    });
    vaciar(this.contenedor).append(tabla);
  };

  Tabla.prototype.pintarAcciones = function (celda, fila, lista) {
    var yo = this;
    var acciones = this.o.acciones(fila) || [];
    if (!acciones.length) { celda.append(el('span', { class: 'suave', text: 'Ninguna' })); return; }
    acciones.forEach(function (a) {
      if (a.enlace) { celda.append(el('a', { class: 'boton boton--discreto', href: a.enlace, text: a.verbo })); return; }
      var boton = el('button', { class: 'boton', type: 'button', text: a.verbo });
      if (a.campo) {
        // Acción que pide un dato: el botón despliega el campo y la confirmación.
        boton.addEventListener('click', function () {
          var entrada = el('input', { type: a.campo.tipo || 'text', name: a.campo.nombre, value: a.campo.valor || '', step: a.campo.paso || null, required: true, 'aria-label': a.campo.etiqueta });
          var confirmar = el('button', { class: 'boton boton--principal', type: 'submit', text: a.campo.confirmar || a.verbo });
          var form = el('form', { class: 'campos' }, entrada, confirmar);
          form.addEventListener('submit', async function (ev) {
            ev.preventDefault();
            var datos = {}; datos[a.campo.nombre] = entrada.value;
            await yo.ejecutar(a, datos, lista, confirmar);
          });
          boton.replaceWith(form);
          entrada.focus();
        });
      } else {
        boton.addEventListener('click', function () { yo.ejecutar(a, a.datos, lista, boton); });
      }
      celda.append(boton);
    });
  };

  Tabla.prototype.ejecutar = async function (a, datos, lista, boton) {
    if (boton.disabled) return;
    ocupado([boton], true);
    var res = await api(a.metodo || 'POST', a.url, datos);
    ocupado([boton], false);
    var hechos = typeof a.hechos === 'function' ? a.hechos(res) : (a.hechos || []);
    var c = a.interpretar ? a.interpretar(res, a, hechos) : interpretar(res, a, hechos);
    var li = constancia(lista, c);
    var fila = lista.closest('tbody');
    if (fila) fila.classList.add('con-constancias');
    if (res.ok && this.o.alCambiar) {
      var yo = this;
      await recargando(this.contenedor, function () { return yo.o.alCambiar(); });
    }
    // Después de recargar: el botón ya no existe, la constancia sí (sobrevive a la recarga).
    enfocar(li);
  };

  // ------------------------------------------------------- formularios --
  /**
   * Conecta un formulario de acción a la API. El resultado queda como constancia
   * dentro del propio formulario (en su <ol class="constancias">).
   */
  function formulario(form, opciones) {
    var lista = form.querySelector('ol.constancias') || form.appendChild(el('ol', { class: 'constancias' }));
    form.addEventListener('input', function (ev) {
      if (ev.target.getAttribute('aria-invalid')) ev.target.removeAttribute('aria-invalid');
    });
    form.addEventListener('submit', async function (ev) {
      ev.preventDefault();
      var botones = Array.prototype.slice.call(form.querySelectorAll('button[type="submit"]'));
      if (botones.some(function (b) { return b.disabled; })) return; // ya hay un envío en curso
      var datos = opciones.datos(new FormData(form), form);
      if (datos && datos.rechazo) {
        // El dato no sirve: se dice aquí mismo y no se llama a la API.
        constancia(lista, { tipo: 'error', accion: opciones.verbo, veredicto: 'No se envió', marca: 'formulario', texto: datos.texto });
        if (datos.campo) { datos.campo.setAttribute('aria-invalid', 'true'); datos.campo.focus(); }
        return;
      }
      ocupado(botones, true);
      var res = await api(opciones.metodo || 'POST', opciones.url, datos);
      ocupado(botones, false);
      var hechos = opciones.hechos ? opciones.hechos(res, datos) : [];
      var c = opciones.interpretar ? opciones.interpretar(res, opciones, hechos) : interpretar(res, opciones, hechos);
      if (res.ok && opciones.textoExito) c.texto = opciones.textoExito(res.datos) + ' ' + (c.texto || '');
      var li = constancia(lista, c);
      if (res.ok && opciones.alTerminar) await opciones.alTerminar(res.datos, datos);
      enfocar(li);
    });
    return lista;
  }

  /** Llena un <select> con opciones; si no hay de dónde, lo cambia por un campo numérico. */
  function selector(select, opciones, textoVacio) {
    if (!opciones) {
      var entrada = el('input', { type: 'number', name: select.name, min: '1', required: true, inputmode: 'numeric', placeholder: 'número' });
      select.replaceWith(entrada);
      return entrada;
    }
    vaciar(select);
    if (!opciones.length) select.append(el('option', { value: '', text: textoVacio || 'No hay opciones' }));
    opciones.forEach(function (op) { select.append(el('option', { value: op.valor, text: op.texto })); });
    return select;
  }

  /** Pide una colección; devuelve el arreglo, o null si no se pudo (sin ruido). */
  async function lista(url) {
    var res = await api('GET', url);
    if (!res.ok) return null;
    return Array.isArray(res.datos) ? res.datos : (res.datos && res.datos.results) || null;
  }

  function porId(arreglo) {
    var m = new Map();
    (arreglo || []).forEach(function (x) { m.set(String(x.id), x); });
    return m;
  }

  // Cuenta regresiva del segundo factor en el riel.
  (function () {
    var marca = document.getElementById('mfa-minutos');
    if (!marca) return;
    setInterval(function () {
      var s = Math.max(0, Math.round((sesion.mfaHasta - Date.now()) / 1000));
      if (s === 0) {
        var p = document.getElementById('estado-mfa');
        if (p) { p.classList.remove('riel__mfa--vigente'); var f = p.querySelector('strong'); if (f) f.textContent = 'vencido'; marca.textContent = 'ya'; }
        return;
      }
      marca.textContent = Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0') + ' min';
    }, 1000);
  })();

  window.Registro = {
    sesion: sesion, mfaVigente: mfaVigente,
    el: el, vaciar: vaciar, api: api, lista: lista, porId: porId,
    interpretar: interpretar, constancia: constancia, negacionDeLectura: negacionDeLectura,
    explicar: explicar, chipRegla: chipRegla, enfocar: enfocar, ocupado: ocupado,
    Tabla: Tabla, formulario: formulario, selector: selector,
    fechaHora: fechaHora, fechaHoraUtc: fechaHoraUtc, persona: persona, capital: capital,
    idDeUsuario: idDeUsuario, campoUsuario: campoUsuario, rechazo: rechazo,
  };
})();
