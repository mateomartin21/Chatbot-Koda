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
    resp.ok ? mostrarChat() : mostrarLogin();
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

init();
