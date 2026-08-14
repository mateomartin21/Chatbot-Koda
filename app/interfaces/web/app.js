const pantallaLogin = document.getElementById("pantalla-login");
const pantallaChat = document.getElementById("pantalla-chat");

function mostrarLogin() {
  pantallaLogin.hidden = false;
  pantallaChat.hidden = true;
}

function mostrarChat() {
  pantallaLogin.hidden = true;
  pantallaChat.hidden = false;
}

async function init() {
  // La cookie de sesion es httpOnly a proposito: el frontend no puede leerla,
  // asi que pregunta al backend si hay sesion valida.
  try {
    const resp = await fetch("/api/auth/sesion");
    if (!resp.ok) {
      mostrarLogin();
      return;
    }
    mostrarChat();
    await avisarDeLaZonaHoraria();
    // Correo -> perfil -> chat. Un runner del que no se sabe nada solo puede recibir
    // ritmos estimados, y de los ritmos sale el plan entero: preguntarlo despues es
    // preguntarlo tarde.
    await pedirPerfilSiHaceFalta();
  } catch {
    mostrarLogin();
  }
}

// --- Login ---

const formSolicitar = document.getElementById("form-solicitar");
const mensajeLogin = document.getElementById("mensaje-login");

function mostrarMensajeLogin(texto) {
  mensajeLogin.textContent = texto;
  mensajeLogin.hidden = false;
}

formSolicitar.addEventListener("submit", async (evento) => {
  evento.preventDefault();
  const email = document.getElementById("email").value.trim();
  const boton = formSolicitar.querySelector("button");
  boton.disabled = true;

  try {
    const resp = await fetch("/api/auth/solicitar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    });
    if (!resp.ok) {
      mostrarMensajeLogin("No pudimos enviar el correo. Intenta de nuevo en unos segundos.");
      return;
    }
    mostrarMensajeLogin("Revisa tu bandeja de entrada — te mandamos un enlace para entrar.");
    formSolicitar.reset();
  } catch {
    mostrarMensajeLogin("No pudimos enviar el correo. Intenta de nuevo en unos segundos.");
  } finally {
    boton.disabled = false;
  }
});

// --- Chat ---

const burbujas = document.getElementById("burbujas");
const formMensaje = document.getElementById("form-mensaje");
const inputTexto = document.getElementById("texto");
const botonMic = document.getElementById("boton-mic");
const reproductor = document.getElementById("reproductor");

function agregarBurbuja(texto, rol) {
  const burbuja = document.createElement("div");
  burbuja.className = `burbuja burbuja-${rol}`;
  burbuja.textContent = texto;
  burbujas.appendChild(burbuja);
  burbujas.scrollTop = burbujas.scrollHeight;
  return burbuja;
}

// El pipeline es en cascada (STT -> LLM -> TTS), asi que tarda unos segundos de
// verdad — ver docs/adr/ADR-001-pipeline-cascada.md. No hay streaming real (esta
// descartado a proposito en el plan), pero mostrar la etapa aproximada evita que
// se sienta como que la app se congelo.
function iniciarEtapasDeEspera(burbuja, huboAudio) {
  const etapas = huboAudio
    ? ["Escuchando tu audio…", "Pensando…", "Preparando la respuesta…"]
    : ["Pensando…", "Preparando la respuesta…"];
  let indice = 0;
  burbuja.textContent = etapas[0];
  const intervalo = setInterval(() => {
    indice += 1;
    if (indice < etapas.length) burbuja.textContent = etapas[indice];
  }, 1500);
  return () => clearInterval(intervalo);
}

async function enviarMensaje({ texto, audioBlob, burbujaUsuarioYaAgregada = false }) {
  const formData = new FormData();
  if (texto) formData.append("texto", texto);
  if (audioBlob) formData.append("audio", audioBlob, "mensaje.webm");

  if (!burbujaUsuarioYaAgregada) {
    agregarBurbuja(texto || "🎙️ (mensaje de voz)", "usuario");
  }
  const burbujaEspera = agregarBurbuja("", "coach");
  const detenerEtapas = iniciarEtapasDeEspera(burbujaEspera, Boolean(audioBlob));

  try {
    const resp = await fetch("/api/mensajes", { method: "POST", body: formData });
    detenerEtapas();
    if (!resp.ok) {
      burbujaEspera.textContent = "Algo falló al mandar tu mensaje. Intenta de nuevo.";
      return;
    }
    const data = await resp.json();
    burbujaEspera.textContent = data.texto;
    if (data.audio_base64) {
      reproductor.src = `data:audio/mpeg;base64,${data.audio_base64}`;
      reproductor.play().catch(() => {
        // Algunos navegadores bloquean el autoplay si pasa mucho tiempo desde el
        // clic original. Mostramos los controles nativos para que el usuario le
        // de play el mismo, en vez de fallar en silencio.
        reproductor.hidden = false;
        reproductor.controls = true;
      });
    }
  } catch {
    detenerEtapas();
    burbujaEspera.textContent = "No pudimos conectar con Koda. Revisa tu conexión.";
  }
}

formMensaje.addEventListener("submit", async (evento) => {
  evento.preventDefault();
  const texto = inputTexto.value.trim();
  if (!texto || sesionVoz) return; // sesionVoz: ya hay un turno de voz/texto en curso
  inputTexto.value = "";
  await enviarTexto(texto);
});

let mediaRecorder = null;
let fragmentosAudio = [];

async function iniciarGrabacionCascada() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    fragmentosAudio = [];
    mediaRecorder = new MediaRecorder(stream);
    mediaRecorder.ondataavailable = (evento) => fragmentosAudio.push(evento.data);
    mediaRecorder.onstop = () => {
      stream.getTracks().forEach((pista) => pista.stop());
      botonMic.classList.remove("grabando");
      const audioBlob = new Blob(fragmentosAudio, { type: "audio/webm" });
      enviarMensaje({ audioBlob });
    };
    mediaRecorder.start();
    botonMic.classList.add("grabando");
  } catch {
    botonMic.classList.remove("grabando");
    agregarBurbuja("No pude acceder al micrófono. Revisa los permisos del navegador.", "coach");
  }
}

// --- Voz en tiempo real (Nova Sonic) con fallback automatico a la cascada ---
// docs/adr/ADR-011-nova-sonic-y-gateway-de-modelos.md: si el WS no llega a conectar o
// Nova Sonic no abre sesion, cae en silencio a iniciarGrabacionCascada() (arriba), el
// flujo de siempre. Si la sesion se cae A MEDIA conversacion, NO hay handoff a la
// cascada (recuperar el audio a medio grabar es mas riesgo del que vale para esta
// version) — se avisa al usuario y que reintente.

const MUESTREO_ENTRADA = 16000;
const MUESTREO_SALIDA = 24000;
const CODIGO_CIERRE_FALLBACK = 4500;

let sesionVoz = null;
// Si Nova Sonic ya fallo una vez en esta pagina (ej. el modelo no esta habilitado en
// Bedrock -> Model access de esta cuenta), no tiene sentido perder tiempo intentando
// de nuevo en cada clic -- se va directo a la cascada hasta que se recargue la pagina.
let vozRealtimeDeshabilitada = false;

function estaGrabandoTiempoReal() {
  return sesionVoz !== null;
}

async function abrirSesionVoz() {
  const protocolo = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${protocolo}://${location.host}/ws/voz`);
  ws.binaryType = "arraybuffer";

  const conectado = await new Promise((resolve) => {
    ws.addEventListener("open", () => resolve(true), { once: true });
    ws.addEventListener("close", () => resolve(false), { once: true });
    ws.addEventListener("error", () => resolve(false), { once: true });
  });
  if (!conectado) return null;

  ws.addEventListener("message", manejarMensajeVoz);
  ws.addEventListener("close", (evento) => finalizarSesionVoz(evento.code));
  ws.addEventListener("error", () => finalizarSesionVoz(null));
  return ws;
}

async function iniciarVozTiempoReal() {
  const ws = await abrirSesionVoz();
  if (!ws) return false;

  let streamMic;
  let audioContextEntrada;
  try {
    streamMic = await navigator.mediaDevices.getUserMedia({ audio: true });
    audioContextEntrada = new AudioContext({ sampleRate: MUESTREO_ENTRADA });
    await audioContextEntrada.audioWorklet.addModule("/pcm-worklet.js");
  } catch {
    ws.close();
    return false;
  }

  const fuente = audioContextEntrada.createMediaStreamSource(streamMic);
  const nodoCaptura = new AudioWorkletNode(audioContextEntrada, "pcm-capturador");
  nodoCaptura.port.onmessage = (evento) => {
    if (ws.readyState === WebSocket.OPEN) ws.send(evento.data);
  };
  fuente.connect(nodoCaptura);

  sesionVoz = {
    modo: "voz",
    ws,
    streamMic,
    audioContextEntrada,
    nodoCaptura,
    audioContextSalida: new AudioContext({ sampleRate: MUESTREO_SALIDA }),
    siguienteInicio: 0,
    burbujaActual: null,
    rolActual: null,
    grabando: true,
    recibioRespuesta: false,
  };
  reiniciarWatchdog();
  return true;
}

// Nova Sonic acepta texto ademas de audio en la misma sesion ("cross-modal input"),
// asi que el mensaje escrito tambien intenta pasar por ahi primero -- misma voz, misma
// latencia, un solo camino de audio para mantener. Si falla, cae a la cascada de
// siempre (POST /api/mensajes) sin que el usuario tenga que hacer nada distinto.
async function enviarTexto(texto) {
  if (!vozRealtimeDeshabilitada) {
    const ws = await abrirSesionVoz();
    if (ws) {
      sesionVoz = {
        modo: "texto",
        ws,
        streamMic: null,
        audioContextEntrada: null,
        nodoCaptura: null,
        audioContextSalida: new AudioContext({ sampleRate: MUESTREO_SALIDA }),
        siguienteInicio: 0,
        burbujaActual: null,
        rolActual: null,
        grabando: false,
        recibioRespuesta: false,
        textoOriginal: texto,
      };
      agregarBurbuja(texto, "usuario");
      ws.send(JSON.stringify({ tipo: "mensaje_texto", texto }));
      reiniciarWatchdog();
      return;
    }
  }
  await enviarMensaje({ texto });
}

function manejarMensajeVoz(evento) {
  if (!sesionVoz) return;
  reiniciarWatchdog();

  if (typeof evento.data === "string") {
    const datos = JSON.parse(evento.data);
    if (datos.tipo === "transcripcion") {
      // En modo texto, Nova Sonic tambien manda un "eco" de lo que mandamos como si
      // fuera una transcripcion del usuario -- ya mostramos ese texto nosotros mismos
      // al enviarlo, mostrarlo de nuevo lo duplicaria.
      if (sesionVoz.modo === "texto" && datos.rol === "usuario") return;
      if (datos.rol !== "usuario") sesionVoz.recibioRespuesta = true;

      // Nova Sonic manda primero un adelanto de lo que va a decir y, DESPUES Y NO
      // SIEMPRE, la transcripcion confirmada. Se muestra el adelanto enseguida (si se
      // esperara a la confirmada, en los turnos de voz el chat se quedaria mudo) y se
      // sustituye en cuanto llega la confirmada, que es la fiel a lo que se escucho.
      if (sesionVoz.rolActual !== datos.rol) {
        sesionVoz.burbujaActual = agregarBurbuja("", datos.rol === "usuario" ? "usuario" : "coach");
        sesionVoz.rolActual = datos.rol;
        sesionVoz.textoAdelanto = "";
        sesionVoz.textoDefinitivo = "";
      }
      if (datos.definitiva) sesionVoz.textoDefinitivo += datos.texto;
      else sesionVoz.textoAdelanto += datos.texto;

      // Se muestra la version mas completa de las dos, nunca menos de lo que ya se
      // veia: la confirmada llega frase por frase y el turno puede cerrarse antes de
      // que lleguen todas, asi que sustituirla a ciegas recortaba el mensaje.
      sesionVoz.burbujaActual.textContent =
        sesionVoz.textoDefinitivo.length >= sesionVoz.textoAdelanto.length
          ? sesionVoz.textoDefinitivo
          : sesionVoz.textoAdelanto;
      burbujas.scrollTop = burbujas.scrollHeight;
    } else if (datos.tipo === "turno_terminado") {
      sesionVoz.rolActual = null;
      sesionVoz.burbujaActual = null;
      // Un turno por sesion en esta version -- cerramos aqui, no al soltar el boton.
      // El audio ya agendado sigue sonando: finalizarSesionVoz() espera a que termine
      // antes de cerrar el AudioContext.
      if (sesionVoz.ws.readyState === WebSocket.OPEN) sesionVoz.ws.close();
    }
    return;
  }

  sesionVoz.recibioRespuesta = true;
  reproducirFragmentoPCM(evento.data);
}

function reproducirFragmentoPCM(arrayBuffer) {
  const contexto = sesionVoz.audioContextSalida;
  const pcm16 = new Int16Array(arrayBuffer);
  const flotante = new Float32Array(pcm16.length);
  for (let i = 0; i < pcm16.length; i++) flotante[i] = pcm16[i] / 0x8000;

  const buffer = contexto.createBuffer(1, flotante.length, MUESTREO_SALIDA);
  buffer.copyToChannel(flotante, 0);

  const fuente = contexto.createBufferSource();
  fuente.buffer = buffer;
  fuente.connect(contexto.destination);

  const inicio = Math.max(contexto.currentTime, sesionVoz.siguienteInicio);
  fuente.start(inicio);
  sesionVoz.siguienteInicio = inicio + buffer.duration;
}

// Watchdog de INACTIVIDAD, no un plazo fijo: se reinicia con cada mensaje que llega.
// Un plazo fijo desde que sueltas el boton corta las respuestas largas a media frase
// (Nova Sonic puede hablar mas de 20s seguidos) -- ese fue un bug real en pruebas.
const TIMEOUT_INACTIVIDAD_MS = 20000;

function reiniciarWatchdog() {
  if (!sesionVoz) return;
  clearTimeout(sesionVoz.timeoutRespuesta);
  sesionVoz.timeoutRespuesta = setTimeout(() => {
    if (!sesionVoz) return;
    if (!sesionVoz.recibioRespuesta) {
      agregarBurbuja("Koda tardó demasiado en responder. Intenta de nuevo.", "coach");
    }
    if (sesionVoz.ws.readyState === WebSocket.OPEN) {
      sesionVoz.ws.close();
    } else {
      finalizarSesionVoz(null);
    }
  }, TIMEOUT_INACTIVIDAD_MS);
}

function detenerCapturaVoz() {
  // Suelta el boton: deja de mandar audio nuevo y avisa "fin_de_audio", pero NO cierra
  // el socket -- si lo cerraramos aqui, matariamos la sesion antes de que el modelo
  // responda (ese fue el bug que reporto el usuario en la primera prueba).
  if (!sesionVoz || !sesionVoz.grabando) return;
  sesionVoz.grabando = false;
  sesionVoz.nodoCaptura.port.onmessage = null;
  sesionVoz.streamMic.getTracks().forEach((pista) => pista.stop());
  botonMic.classList.remove("grabando");
  botonMic.disabled = true; // evita un segundo clic mientras se espera la respuesta
  if (sesionVoz.ws.readyState === WebSocket.OPEN) {
    sesionVoz.ws.send(JSON.stringify({ tipo: "fin_de_audio" }));
  }
  reiniciarWatchdog();
}

function finalizarSesionVoz(codigo) {
  if (!sesionVoz) return;
  const { modo, textoOriginal, audioContextSalida, siguienteInicio, recibioRespuesta } = sesionVoz;
  const habiaTurnoActivo = sesionVoz.rolActual !== null;
  clearTimeout(sesionVoz.timeoutRespuesta);

  if (sesionVoz.nodoCaptura) sesionVoz.nodoCaptura.port.onmessage = null;
  if (sesionVoz.streamMic) sesionVoz.streamMic.getTracks().forEach((pista) => pista.stop());
  if (sesionVoz.audioContextEntrada) sesionVoz.audioContextEntrada.close().catch(() => {});
  sesionVoz = null;
  botonMic.classList.remove("grabando");

  // CLAVE: Nova Sonic genera el audio mucho mas rapido que en tiempo real, asi que
  // cuando el turno "termina" del lado del servidor todavia quedan segundos de audio
  // agendados sonando en el navegador. Cerrar el AudioContext aqui los destruiria y la
  // respuesta se cortaria a media frase -- ese fue el bug que se veia como "se corta
  // mientras seguia hablando". Esperamos a que termine de sonar.
  const segundosRestantes = Math.max(0, siguienteInicio - audioContextSalida.currentTime);
  setTimeout(
    () => {
      audioContextSalida.close().catch(() => {});
      botonMic.disabled = false;
    },
    (segundosRestantes + 0.3) * 1000
  );

  if (codigo === CODIGO_CIERRE_FALLBACK) {
    vozRealtimeDeshabilitada = true;
    if (habiaTurnoActivo) {
      agregarBurbuja("Se perdió la conexión de voz en tiempo real. Intenta de nuevo.", "coach");
      return;
    }
  }

  // Si la sesion termino sin una sola respuesta (Nova Sonic mudo, cierre inesperado...),
  // el usuario no puede quedarse sin contestacion: se reintenta por la cascada de
  // siempre, que ya trae su propio gateway de modelos por dentro.
  if (!recibioRespuesta) {
    if (modo === "texto") {
      enviarMensaje({ texto: textoOriginal, burbujaUsuarioYaAgregada: true });
    } else if (codigo === CODIGO_CIERRE_FALLBACK) {
      // Nova Sonic no llego ni a abrir sesion: grabamos por la via normal.
      iniciarGrabacionCascada();
    }
  }
}

botonMic.addEventListener("click", async () => {
  if (mediaRecorder && mediaRecorder.state === "recording") {
    mediaRecorder.stop();
    return;
  }
  if (estaGrabandoTiempoReal()) {
    detenerCapturaVoz();
    return;
  }

  botonMic.classList.add("grabando");
  if (!vozRealtimeDeshabilitada) {
    const conectado = await iniciarVozTiempoReal().catch(() => false);
    if (conectado) return;
  }

  botonMic.classList.remove("grabando");
  await iniciarGrabacionCascada();
});

// --- Paneles de plan y perfil ---

const DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"];
const panelPlan = document.getElementById("panel-plan");
const panelPerfil = document.getElementById("panel-perfil");
const contenidoPlan = document.getElementById("contenido-plan");
const formPerfil = document.getElementById("form-perfil");
const mensajePerfil = document.getElementById("mensaje-perfil");

function abrirPanel(panel) {
  panel.hidden = false;
}

document.querySelectorAll(".cerrar-panel").forEach((boton) => {
  boton.addEventListener("click", () => (boton.closest(".panel").hidden = true));
});

function crear(etiqueta, clase, texto) {
  const nodo = document.createElement(etiqueta);
  if (clase) nodo.className = clase;
  if (texto !== undefined) nodo.textContent = texto;
  return nodo;
}

function fechaCorta(iso) {
  // El backend manda YYYY-MM-DD. new Date("2026-11-08") se interpreta como UTC y en
  // husos al oeste retrocede un dia: se construye a mano para que el domingo no
  // aparezca como sabado.
  const [anio, mes, dia] = iso.split("-").map(Number);
  return new Date(anio, mes - 1, dia).toLocaleDateString("es-MX", { day: "numeric", month: "short" });
}

function nodoSesion(sesion) {
  const fila = crear("div", "sesion");
  fila.appendChild(crear("span", "sesion-dia", DIAS[sesion.dia_semana]));
  if (sesion.tipo === "descanso") {
    fila.appendChild(crear("span", "sesion-descanso", "Descanso"));
    return fila;
  }
  fila.appendChild(crear("span", null, sesion.descripcion));
  return fila;
}

function nodoSemana(semana, esPrimeraAbierta) {
  const detalle = crear("details", "semana");
  detalle.open = esPrimeraAbierta;
  const resumen = crear("summary");
  resumen.appendChild(crear("span", null, `Semana ${semana.numero}`));
  const derecha = crear("span", null);
  if (semana.es_taper) derecha.appendChild(crear("span", "etiqueta etiqueta-taper", "taper"));
  else if (semana.es_descarga) derecha.appendChild(crear("span", "etiqueta etiqueta-descarga", "descarga"));
  derecha.appendChild(crear("span", null, ` ${semana.volumen_km} km`));
  resumen.appendChild(derecha);
  detalle.appendChild(resumen);
  semana.sesiones.forEach((sesion) => detalle.appendChild(nodoSesion(sesion)));
  return detalle;
}

function pintarPlan(plan) {
  contenidoPlan.replaceChildren();

  if (!plan) {
    const vacio = crear("p", "vacio");
    vacio.textContent =
      "Todavía no tienes un plan. Dile a Koda qué carrera quieres correr y para cuándo, y te lo arma.";
    contenidoPlan.appendChild(vacio);
    return;
  }

  const resumen = crear("div", "resumen-plan");
  resumen.appendChild(crear("h3", null, plan.nombre_carrera || `Tu ${plan.distancia}`));
  resumen.appendChild(
    crear(
      "p",
      "aviso",
      `${plan.distancia} el ${fechaCorta(plan.fecha_carrera)} · ${plan.semanas.length} semanas · ` +
        `${plan.volumen_total_km} km en total`,
    ),
  );

  // El plan se cuenta hacia atras desde la carrera, asi que su arranque suele caer
  // unos dias por delante. Decirlo evita que parezca un error de fechas.
  const hoy = new Date().toISOString().slice(0, 10);
  if (plan.fecha_inicio > hoy) {
    const nota = crear("p", "aviso");
    nota.appendChild(crear("span", "destacado", `Arranca el ${fechaCorta(plan.fecha_inicio)}. `));
    nota.appendChild(
      document.createTextNode(
        "El plan se cuenta hacia atrás desde la carrera para que la bajada de carga " +
          "caiga justo antes. Hasta entonces, rodajes suaves y sin prisa.",
      ),
    );
    resumen.appendChild(nota);
  }

  if (plan.proxima_sesion) {
    const proxima = crear("p", null);
    proxima.appendChild(crear("span", "destacado", "Lo siguiente: "));
    proxima.appendChild(
      document.createTextNode(
        `${DIAS[plan.proxima_sesion.dia_semana]} ${fechaCorta(plan.proxima_sesion.fecha)} — ` +
          plan.proxima_sesion.descripcion,
      ),
    );
    resumen.appendChild(proxima);
  }

  const zonas = crear("ul", "zonas");
  Object.entries(plan.zonas).forEach(([nombre, ritmo]) => {
    const item = crear("li");
    item.appendChild(crear("span", null, nombre));
    item.appendChild(document.createTextNode(ritmo));
    zonas.appendChild(item);
  });
  resumen.appendChild(zonas);

  if (plan.ritmos_estimados) {
    resumen.appendChild(
      crear("p", "aviso", "Ritmos estimados: en cuanto registres una marca real, los ajusto."),
    );
  }
  plan.notas.forEach((nota) => resumen.appendChild(crear("p", "aviso", nota)));
  contenidoPlan.appendChild(resumen);

  const semanaDeLaProxima = plan.proxima_sesion
    ? plan.semanas.find((s) => s.sesiones.some((x) => x.fecha === plan.proxima_sesion.fecha))
    : null;
  plan.semanas.forEach((semana) =>
    contenidoPlan.appendChild(nodoSemana(semana, semana === semanaDeLaProxima)),
  );
}

async function cargarPlan() {
  abrirPanel(panelPlan);
  contenidoPlan.replaceChildren(crear("p", "vacio", "Cargando…"));
  try {
    const resp = await fetch("/api/plan");
    pintarPlan(resp.ok ? await resp.json() : null);
  } catch {
    contenidoPlan.replaceChildren(crear("p", "vacio", "No pudimos cargar tu plan. Intenta otra vez."));
  }
}

document.getElementById("boton-plan").addEventListener("click", cargarPlan);

// El tiempo se teclea como se dice ("25:00", "1:42:30"); la API trabaja en segundos.
function aSegundos(texto) {
  if (!texto || !texto.trim()) return null;
  const partes = texto.trim().split(":").map(Number);
  if (partes.some(Number.isNaN)) return null;
  return partes.reduce((total, parte) => total * 60 + parte, 0);
}

function deSegundos(segundos) {
  if (!segundos) return "";
  const horas = Math.floor(segundos / 3600);
  const minutos = Math.floor((segundos % 3600) / 60);
  const resto = Math.round(segundos % 60);
  const dosDigitos = (n) => String(n).padStart(2, "0");
  return horas
    ? `${horas}:${dosDigitos(minutos)}:${dosDigitos(resto)}`
    : `${minutos}:${dosDigitos(resto)}`;
}

const camposPerfil = {
  nombre: document.getElementById("perfil-nombre"),
  edad: document.getElementById("perfil-edad"),
  nivel: document.getElementById("perfil-nivel"),
  dias_disponibles: document.getElementById("perfil-dias"),
  marca_distancia_km: document.getElementById("perfil-marca-km"),
};
const campoMarcaTiempo = document.getElementById("perfil-marca-tiempo");

const introPerfil = document.getElementById("intro-perfil");
const saltarPerfil = document.getElementById("saltar-perfil");

async function rellenarPerfil() {
  const resp = await fetch("/api/perfil");
  if (!resp.ok) return null;
  const perfil = await resp.json();
  Object.entries(camposPerfil).forEach(([campo, input]) => {
    input.value = perfil[campo] ?? "";
  });
  campoMarcaTiempo.value = deSegundos(perfil.marca_tiempo_seg);
  return perfil;
}

function modoBienvenida(activo) {
  panelPerfil.classList.toggle("modo-bienvenida", activo);
  introPerfil.hidden = !activo;
  saltarPerfil.hidden = !activo;
  // En la bienvenida no se enseñan: primero lo minimo para poder entrenar.
  if (activo) seccionAvisos.hidden = true;
}

function cerrarPerfil() {
  panelPerfil.hidden = true;
  modoBienvenida(false);
}

saltarPerfil.addEventListener("click", cerrarPerfil);

// El navegador ya sabe en qué huso estás; preguntarlo en un desplegable sería hacerte
// trabajo que no hace falta. De este dato depende que un aviso de las 6 llegue a las 6.
async function avisarDeLaZonaHoraria() {
  try {
    const zona = Intl.DateTimeFormat().resolvedOptions().timeZone;
    if (!zona) return;
    const perfil = await (await fetch("/api/perfil")).json();
    if (perfil.zona_horaria === zona) return;
    await fetch("/api/perfil", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ zona_horaria: zona }),
    });
  } catch {
    /* sin zona horaria los avisos usan la de México: molesto, no roto */
  }
}

// --- Recordatorios ---

const seccionAvisos = document.getElementById("seccion-avisos");
const listaAvisos = document.getElementById("lista-avisos");
const mensajeAvisos = document.getElementById("mensaje-avisos");

const NOMBRE_DEL_AVISO = {
  diario: "Qué me toca hoy",
  checkin: "¿Saliste hoy?",
  semanal: "Resumen del domingo",
};

async function guardarAviso(tipo, hora, activo) {
  mensajeAvisos.hidden = true;
  try {
    const resp = await fetch("/api/recordatorios", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tipo, hora_local: hora, activo }),
    });
    mensajeAvisos.textContent = resp.ok ? "Guardado." : "No pudimos guardarlo.";
  } catch {
    mensajeAvisos.textContent = "No pudimos guardarlo.";
  }
  mensajeAvisos.hidden = false;
}

function nodoAviso(aviso) {
  const fila = crear("div", "aviso");

  const activo = document.createElement("input");
  activo.type = "checkbox";
  activo.checked = aviso.activo;
  activo.id = `aviso-${aviso.tipo}`;

  const etiqueta = document.createElement("label");
  etiqueta.htmlFor = activo.id;
  etiqueta.textContent = NOMBRE_DEL_AVISO[aviso.tipo] || aviso.tipo;

  const hora = document.createElement("input");
  hora.type = "time";
  hora.value = aviso.hora_local;
  hora.disabled = !aviso.activo;

  activo.addEventListener("change", () => {
    hora.disabled = !activo.checked;
    guardarAviso(aviso.tipo, hora.value, activo.checked);
  });
  hora.addEventListener("change", () => guardarAviso(aviso.tipo, hora.value, activo.checked));

  fila.append(activo, etiqueta, hora);
  return fila;
}

async function cargarAvisos() {
  try {
    const resp = await fetch("/api/recordatorios");
    if (!resp.ok) return;
    const avisos = await resp.json();
    listaAvisos.replaceChildren(...avisos.map(nodoAviso));
    seccionAvisos.hidden = avisos.length === 0;
  } catch {
    seccionAvisos.hidden = true;
  }
}

async function pedirPerfilSiHaceFalta() {
  try {
    const perfil = await rellenarPerfil();
    // Sin nivel ni dias disponibles no se puede generar nada util. El nombre y la edad
    // son bonitos de tener; estos dos son los que entran en el calculo.
    if (!perfil || perfil.nivel || perfil.dias_disponibles) return;
    mensajePerfil.hidden = true;
    modoBienvenida(true);
    abrirPanel(panelPerfil);
  } catch {
    /* si no se puede consultar el perfil, se entra al chat sin mas */
  }
}

document.getElementById("boton-perfil").addEventListener("click", async () => {
  modoBienvenida(false);
  abrirPanel(panelPerfil);
  mensajePerfil.hidden = true;
  try {
    await rellenarPerfil();
    await cargarAvisos();
  } catch {
    /* el formulario se queda vacio: se puede rellenar igual */
  }
});

formPerfil.addEventListener("submit", async (evento) => {
  evento.preventDefault();
  const boton = formPerfil.querySelector("button[type=submit]");
  boton.disabled = true;

  // Solo se mandan los campos con valor: null en la API significa "no me lo has
  // dicho", nunca "borralo".
  const cuerpo = {};
  Object.entries(camposPerfil).forEach(([campo, input]) => {
    const valor = input.value.trim();
    if (valor) cuerpo[campo] = input.type === "number" ? Number(valor) : valor;
  });
  // Una marca a medias no sirve para nada: el ritmo sale de dividir tiempo entre
  // distancia, asi que con una sola de las dos el plan seguiria con ritmos estimados
  // y el runner creeria que ya dio su dato.
  const segundos = aSegundos(campoMarcaTiempo.value);
  const hayDistancia = Boolean(cuerpo.marca_distancia_km);
  if (hayDistancia !== Boolean(segundos)) {
    mensajePerfil.textContent = hayDistancia
      ? "Falta el tiempo de esa marca: sin él no puedo calcular tus ritmos."
      : "¿Sobre qué distancia es ese tiempo?";
    mensajePerfil.hidden = false;
    boton.disabled = false;
    return;
  }
  if (segundos) cuerpo.marca_tiempo_seg = segundos;

  try {
    const resp = await fetch("/api/perfil", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(cuerpo),
    });
    mensajePerfil.textContent = resp.ok
      ? "Guardado. Con esto te ajusto mejor los ritmos."
      : "No pudimos guardarlo. Revisa los datos e intenta otra vez.";
    // En la bienvenida, guardar es la puerta al chat: se deja leer el mensaje y se pasa.
    if (resp.ok && panelPerfil.classList.contains("modo-bienvenida")) {
      setTimeout(cerrarPerfil, 900);
    }
  } catch {
    mensajePerfil.textContent = "No pudimos guardarlo. Intenta otra vez.";
  } finally {
    mensajePerfil.hidden = false;
    boton.disabled = false;
  }
});

init();
