/* =============================================================================
   Koda — interfaz web

   Sin framework a proposito (ver docs/adr/ADR-002-python-fastapi.md): la app es
   una sola pantalla con una conversacion y dos paneles. Lo que sigue esta
   ordenado por capas: utilidades, el hilo de mensajes, la voz, y los paneles.
   ============================================================================= */

const ICONOS = "/iconos.svg";

// --- Utilidades de DOM -------------------------------------------------------

function crear(etiqueta, clase, texto) {
  const nodo = document.createElement(etiqueta);
  if (clase) nodo.className = clase;
  if (texto !== undefined) nodo.textContent = texto;
  return nodo;
}

function icono(nombre, clase) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  if (clase) svg.setAttribute("class", clase);
  svg.setAttribute("aria-hidden", "true");
  const uso = document.createElementNS("http://www.w3.org/2000/svg", "use");
  uso.setAttribute("href", `${ICONOS}#i-${nombre}`);
  svg.appendChild(uso);
  return svg;
}

function conCargador(boton, cargando) {
  boton.dataset.cargando = cargando ? "si" : "no";
  boton.disabled = cargando;
}

// --- Formato del texto de Koda ----------------------------------------------
//
// El modelo contesta en texto plano con guiones, listas numeradas y **negritas**.
// Volcarlo tal cual en un solo bloque satura la vista; interpretarlo con innerHTML
// seria meter en el DOM lo que escriba un LLM. Asi que se construye nodo a nodo:
// nada de lo que devuelva el modelo puede convertirse en HTML.

// Cualquier medida se pasa a la tipografia de datos: 5:30/km, 12 km, 45 min, 21K.
const MEDIDAS = /(\d+(?:[.,]\d+)?\s?(?:km\/h|km|k|m|min|h)\b(?:\/km)?|\d{1,2}:\d{2}(?::\d{2})?(?:\s?\/\s?km)?)/gi;

function conMedidas(destino, texto) {
  for (const trozo of texto.split(MEDIDAS)) {
    if (!trozo) continue;
    MEDIDAS.lastIndex = 0;
    if (MEDIDAS.test(trozo)) destino.appendChild(crear("span", "dato", trozo));
    else destino.appendChild(document.createTextNode(trozo));
  }
}

function conNegritas(destino, texto) {
  // Se parte por **...**; los trozos impares son lo que va en negrita.
  texto.split(/\*\*(.+?)\*\*/g).forEach((trozo, indice) => {
    if (!trozo) return;
    if (indice % 2 === 1) {
      const fuerte = crear("strong");
      conMedidas(fuerte, trozo);
      destino.appendChild(fuerte);
    } else {
      conMedidas(destino, trozo);
    }
  });
}

const VINETA = /^\s*[-*•]\s+/;
const NUMERADA = /^\s*\d+[.)]\s+/;

function pintarTexto(destino, texto) {
  destino.replaceChildren();
  const bloques = String(texto ?? "")
    .replace(/\r/g, "")
    .split(/\n{2,}/);

  for (const bloque of bloques) {
    const lineas = bloque.split("\n").filter((linea) => linea.trim());
    if (!lineas.length) continue;

    const vinetas = lineas.every((linea) => VINETA.test(linea));
    const numeradas = !vinetas && lineas.every((linea) => NUMERADA.test(linea));

    if (vinetas || numeradas) {
      const lista = crear(numeradas ? "ol" : "ul");
      for (const linea of lineas) {
        const item = crear("li");
        conNegritas(item, linea.replace(vinetas ? VINETA : NUMERADA, ""));
        lista.appendChild(item);
      }
      destino.appendChild(lista);
      continue;
    }

    // Un salto suelto dentro de un parrafo es un salto de linea, no un parrafo
    // nuevo: partirlos separaria frases que el modelo escribio juntas.
    const parrafo = crear("p");
    lineas.forEach((linea, indice) => {
      if (indice) parrafo.appendChild(crear("br"));
      conNegritas(parrafo, linea);
    });
    destino.appendChild(parrafo);
  }
}

// --- Pantallas ---------------------------------------------------------------

const pantallaLogin = document.getElementById("pantalla-login");
const pantallaChat = document.getElementById("pantalla-chat");

function mostrarLogin() {
  pantallaLogin.hidden = false;
  pantallaChat.hidden = true;
}

function mostrarChat() {
  pantallaLogin.hidden = true;
  pantallaChat.hidden = false;
  sincronizarAnclaje();
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
    // El hilo, antes que nada: si hay conversación anterior, la bienvenida sobra y
    // enseñarla un instante para quitarla después es un parpadeo feo.
    await cargarHistorial();
    // Correo -> perfil -> chat. De un runner del que no se sabe nada solo salen
    // ritmos estimados, y de los ritmos sale el plan entero: preguntarlo despues
    // es preguntarlo tarde.
    await pedirPerfilSiHaceFalta();
  } catch {
    mostrarLogin();
  }
}

// --- Entrar ------------------------------------------------------------------

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
  conCargador(boton, true);

  try {
    const resp = await fetch("/api/auth/solicitar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    });
    if (!resp.ok) {
      mostrarMensajeLogin("No pudimos enviar el correo. Inténtalo de nuevo en unos segundos.");
      return;
    }
    mostrarMensajeLogin("Revisa tu bandeja: te mandamos un enlace para entrar.");
    formSolicitar.reset();
  } catch {
    mostrarMensajeLogin("No pudimos enviar el correo. Inténtalo de nuevo en unos segundos.");
  } finally {
    conCargador(boton, false);
  }
});

// =============================================================================
// El hilo de la conversacion
// =============================================================================

const burbujas = document.getElementById("burbujas");
const bienvenida = document.getElementById("bienvenida");
const formMensaje = document.getElementById("form-mensaje");
const inputTexto = document.getElementById("texto");
const botonMic = document.getElementById("boton-mic");
const botonParar = document.getElementById("boton-parar");
const estadoKoda = document.getElementById("estado-koda");
const compositor = document.getElementById("form-mensaje");

const ESTADO_EN_REPOSO = "Entrenador de running";

function estado(texto) {
  estadoKoda.textContent = texto || ESTADO_EN_REPOSO;
}

/* La cara de la cabecera cambia de gesto y vuelve sola. Solo dos cosas lo disparan,
   y las dos son hechos, no estados de ánimo:

   - algo falló — la queja de siempre de un chat es que un error se lee igual que
     una respuesta normal; el gesto lo hace visible sin un cartel rojo;
   - acabas de tener un plan que antes no tenías.

   Un personaje que reacciona a cada mensaje deja de significar nada. Las caras se
   precargan al arrancar; sin eso el cambio empieza con el hueco en blanco y se lee
   como un fallo de carga, justo cuando a lo mejor ya hubo uno de verdad. */
const CARAS = {
  normal: "/koda/cara.webp",
  duda: "/koda/cara-duda.webp",
  celebra: "/koda/cara-rie.webp",
};
const caraKoda = document.getElementById("cara-koda");
let vueltaAlaCalma = null;

Object.values(CARAS).forEach((ruta) => {
  new Image().src = ruta;
});

function gesto(cual, duracionMs = 3200) {
  if (!caraKoda || !CARAS[cual]) return;
  clearTimeout(vueltaAlaCalma);
  caraKoda.src = CARAS[cual];
  caraKoda.classList.remove("gesticula");
  void caraKoda.offsetWidth; // reinicia la animacion si ya estaba puesta
  caraKoda.classList.add("gesticula");
  if (cual !== "normal") vueltaAlaCalma = setTimeout(() => gesto("normal"), duracionMs);
}

function alFinal() {
  burbujas.scrollTop = burbujas.scrollHeight;
}

/* Lo que os dijisteis la última vez.

   El hilo ya se guardaba — es de donde sale la memoria del coach — pero solo lo leía
   el modelo. Cerrabas la pestaña, volvías, y Koda te recibía con "Hola, soy Koda"
   como si no os conocierais, mientras por dentro se acordaba de todo. Esa
   contradicción es peor que no tener memoria: parece que se le olvidó.

   Si falla, no se dice nada y se enseña la bienvenida: perder el historial es
   molesto, no poder escribir es descalificante. */
async function cargarHistorial() {
  let turnos = [];
  try {
    const resp = await fetch("/api/conversacion");
    if (!resp.ok) return;
    turnos = await resp.json();
  } catch {
    return;
  }
  if (!turnos.length) return;

  let diaPintado = null;
  turnos.forEach((turno) => {
    const dia = turno.creado_en.slice(0, 10);
    if (dia !== diaPintado) {
      burbujas.appendChild(separadorDeDia(turno.creado_en));
      diaPintado = dia;
    }
    // Los turnos con foto se pintan como texto: la foto no se guarda en ningún
    // sitio (ADR-017), así que no hay nada que volver a enseñar.
    agregarMensaje(turno.rol === "usuario" ? "usuario" : "coach", {
      voz: turno.modalidad === "voz",
    }).escribir(turno.contenido);
  });

  // Sin animación y directo al final: esto no está "llegando" ahora, ya estaba.
  burbujas.classList.add("sin-entrada");
  requestAnimationFrame(() => {
    burbujas.scrollTop = burbujas.scrollHeight;
    burbujas.classList.remove("sin-entrada");
  });
}

/* "Hoy", "Ayer" o la fecha. Sin esto, una conversación de hace tres semanas se lee
   como si acabara de pasar — y el "te veo el martes" de entonces confunde. */
function separadorDeDia(iso) {
  const cuando = new Date(iso);
  const hoy = new Date();
  const soloDia = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const dias = Math.round((soloDia(hoy) - soloDia(cuando)) / 86400000);

  let etiqueta;
  if (dias === 0) etiqueta = "Hoy";
  else if (dias === 1) etiqueta = "Ayer";
  else if (dias < 7) etiqueta = cuando.toLocaleDateString("es-MX", { weekday: "long" });
  else etiqueta = fechaCorta(iso.slice(0, 10));

  const separador = crear("div", "separador-dia");
  separador.appendChild(crear("span", null, etiqueta));
  return separador;
}

/* Un mensaje del hilo. Devuelve un mando en vez del nodo pelado: quien lo usa no
   deberia saber si por dentro hay un parrafo, una lista o tres puntos animados. */
function agregarMensaje(rol, { voz = false } = {}) {
  bienvenida?.remove();

  const fila = crear("div", `mensaje mensaje-${rol}`);
  if (rol === "coach") {
    const avatar = crear("div", "avatar");
    // El icono de la aplicacion, el mismo que el logotipo y el de la pantalla de
    // inicio. Es la unica marca que aparece dentro de la conversacion, asi que si
    // fuera distinta de la de la cabecera se leeria como otra cosa.
    avatar.appendChild(
      Object.assign(new Image(192, 192), { src: "/iconos-app/icono-192.png", alt: "" }),
    );
    // Tres barras que solo se ven mientras suena su voz. El anillo de antes decía
    // "algo pasa"; esto dice "está hablando", que es lo único que necesitas saber
    // si el móvil va en el bolsillo y solo lo miras de reojo.
    const ecualizador = crear("span", "ecualizador");
    ecualizador.append(crear("i"), crear("i"), crear("i"));
    avatar.appendChild(ecualizador);
    fila.appendChild(avatar);
  }

  const burbuja = crear("div", "burbuja");
  if (voz) {
    const etiqueta = crear("span", "etiqueta-voz");
    etiqueta.append(icono("micro"), crear("span", null, "voz"));
    burbuja.appendChild(etiqueta);
  }
  const cuerpo = crear("div");
  burbuja.appendChild(cuerpo);
  fila.appendChild(burbuja);
  burbujas.appendChild(fila);
  alFinal();

  let asentado = false;
  let temporizador = null;

  return {
    fila,
    escribir(texto) {
      clearInterval(temporizador);
      // Si estaba esperando, los tres puntos y la respuesta se cruzan con un
      // desenfoque. Un cambio seco deja ver dos cosas superpuestas durante un
      // fotograma; así el ojo lee una sola que se convierte en otra.
      if (cuerpo.querySelector(".pensando")) {
        cuerpo.classList.add("cambiando");
        setTimeout(() => {
          pintarTexto(cuerpo, texto);
          cuerpo.classList.remove("cambiando", "provisional");
          alFinal();
        }, 160);
        return;
      }
      pintarTexto(cuerpo, texto);
      cuerpo.classList.remove("provisional");
      alFinal();
    },

    // Transcripcion en curso: se ve distinta del texto confirmado a proposito.
    // Al confirmarse, los dos textos se cruzan con un desenfoque de 2px — sin el
    // se ven dos frases superpuestas; con el, el ojo lee una sola que se afina.
    escribirParcial(texto, definitiva) {
      if (definitiva && !asentado) {
        asentado = true;
        cuerpo.classList.add("asentando");
        setTimeout(() => {
          pintarTexto(cuerpo, texto);
          cuerpo.classList.remove("asentando", "provisional");
          alFinal();
        }, 170);
        return;
      }
      pintarTexto(cuerpo, texto);
      cuerpo.classList.toggle("provisional", !asentado);
      alFinal();
    },

    // El pipeline en cascada tarda segundos de verdad y no hay streaming (esta
    // descartado a proposito). Decir en que va evita que parezca colgado.
    esperar(etapas) {
      const caja = crear("div", "pensando");
      const puntos = crear("div", "puntos");
      puntos.append(crear("span"), crear("span"), crear("span"));
      const rotulo = crear("span", null, etapas[0]);
      caja.append(puntos, rotulo);
      cuerpo.replaceChildren(caja);
      estado(etapas[0]);
      alFinal();

      let indice = 0;
      temporizador = setInterval(() => {
        indice += 1;
        if (indice < etapas.length) {
          rotulo.textContent = etapas[indice];
          estado(etapas[indice]);
        }
      }, 1600);
      return () => {
        clearInterval(temporizador);
        estado(null);
      };
    },

    hablando(activo) {
      fila.querySelector(".avatar")?.classList.toggle("hablando", activo);
    },

    // La foto se ve en el hilo como la mandaste. Sin esto, el turno del runner
    // queda vacío y Koda contesta a algo que no está a la vista.
    conFoto(url) {
      const miniatura = document.createElement("img");
      miniatura.className = "foto-enviada";
      miniatura.src = url;
      miniatura.alt = "Foto que mandaste";
      miniatura.addEventListener("load", () => URL.revokeObjectURL(url), { once: true });
      burbuja.insertBefore(miniatura, cuerpo);
      alFinal();
    },
  };
}

// --- Cascada (POST /api/mensajes) --------------------------------------------

async function enviarMensaje({ texto, audioBlob, foto, mensajeUsuarioYaPuesto = false }) {
  const formData = new FormData();
  if (texto) formData.append("texto", texto);
  if (audioBlob) formData.append("audio", audioBlob, "mensaje.webm");
  if (foto) formData.append("foto", foto, foto.name || "foto.jpg");

  if (!mensajeUsuarioYaPuesto) {
    const mio = agregarMensaje("usuario", { voz: Boolean(audioBlob) });
    if (foto) mio.conFoto(URL.createObjectURL(foto));
    mio.escribir(texto || (foto ? "" : "Mensaje de voz"));
  }

  const respuesta = agregarMensaje("coach");
  const dejarDeEsperar = respuesta.esperar(
    audioBlob
      ? ["Escuchando tu audio", "Pensando", "Preparando la respuesta"]
      : ["Pensando", "Preparando la respuesta"],
  );

  try {
    const resp = await fetch("/api/mensajes", { method: "POST", body: formData });
    dejarDeEsperar();
    if (!resp.ok) {
      gesto("duda");
      respuesta.escribir("No pude procesar tu mensaje. Inténtalo otra vez.");
      return;
    }
    const data = await resp.json();
    respuesta.escribir(data.texto);
    refrescarPlanTrasElTurno();
    if (data.audio_base64) reproducirMp3(data.audio_base64, respuesta);
  } catch {
    dejarDeEsperar();
    gesto("duda");
    respuesta.escribir("No hay conexión con Koda. Revisa tu red e inténtalo otra vez.");
  }
}

function reproducirMp3(base64, mensaje) {
  const audio = new Audio(`data:audio/mpeg;base64,${base64}`);
  mensaje.hablando(true);
  estado("Hablando");
  const terminar = () => {
    mensaje.hablando(false);
    estado(null);
  };
  audio.addEventListener("ended", terminar, { once: true });
  audio.play().catch(() => {
    // Algunos navegadores bloquean el autoplay si pasa mucho tiempo desde el clic
    // original. Se ofrece el control nativo en vez de fallar en silencio.
    terminar();
    audio.controls = true;
    mensaje.fila.querySelector(".burbuja").appendChild(audio);
  });
}

formMensaje.addEventListener("submit", async (evento) => {
  evento.preventDefault();
  const texto = inputTexto.value.trim();
  if (sesionVoz) return; // ya hay un turno en curso

  // Con foto siempre va por la cascada: Nova Sonic es audio a audio y no ve.
  if (fotoElegida) {
    const foto = fotoElegida;
    quitarFoto();
    inputTexto.value = "";
    await enviarMensaje({ texto, foto });
    return;
  }
  if (!texto) return;
  inputTexto.value = "";
  await enviarTexto(texto);
});

// --- Foto -------------------------------------------------------------------

const campoFoto = document.getElementById("foto");
const botonFoto = document.getElementById("boton-foto");
const previaFoto = document.getElementById("previa-foto");
const previaImagen = document.getElementById("previa-imagen");

let fotoElegida = null;

function quitarFoto() {
  if (previaImagen.src.startsWith("blob:")) URL.revokeObjectURL(previaImagen.src);
  fotoElegida = null;
  campoFoto.value = "";
  previaFoto.hidden = true;
  previaImagen.removeAttribute("src");
}

botonFoto.addEventListener("click", () => campoFoto.click());

campoFoto.addEventListener("change", () => {
  const archivo = campoFoto.files?.[0];
  if (!archivo) return;
  // No se manda al elegirla: primero se ve, por si la cámara pilló otra cosa. Y
  // así se le puede añadir un texto ("¿qué tal me quedó?") antes de enviarla.
  fotoElegida = archivo;
  previaImagen.src = URL.createObjectURL(archivo);
  previaFoto.hidden = false;
  inputTexto.focus();
});

document.getElementById("quitar-foto").addEventListener("click", quitarFoto);

document.querySelectorAll(".chip").forEach((chip) => {
  chip.addEventListener("click", () => {
    if (sesionVoz) return;
    enviarTexto(chip.dataset.sugerencia);
  });
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
      mostrarBarraGrabacion(false);
      enviarMensaje({ audioBlob: new Blob(fragmentosAudio, { type: "audio/webm" }) });
    };
    mediaRecorder.start();
    mostrarBarraGrabacion(true);
  } catch {
    mostrarBarraGrabacion(false);
    const aviso = agregarMensaje("coach");
    aviso.escribir("No puedo acceder al micrófono. Revisa los permisos del navegador.");
  }
}

// =============================================================================
// Barra de grabacion
// =============================================================================

const barraGrabacion = document.getElementById("barra-grabacion");
const contenedorOndas = document.getElementById("ondas");
const cronometro = document.getElementById("cronometro");
const BARRAS = 18;

const ondas = Array.from({ length: BARRAS }, () => {
  const barra = crear("span");
  contenedorOndas.appendChild(barra);
  return barra;
});

let cronoInicio = 0;
let cronoTemporizador = null;

function mostrarBarraGrabacion(activo) {
  barraGrabacion.hidden = !activo;
  compositor.classList.toggle("grabando", activo);
  botonMic.disabled = false;

  if (!activo) {
    clearInterval(cronoTemporizador);
    ondas.forEach((barra) => (barra.style.transform = "scaleY(0.16)"));
    estado(null);
    return;
  }

  estado("Escuchando");
  cronoInicio = Date.now();
  cronometro.textContent = "0:00";
  cronoTemporizador = setInterval(() => {
    const s = Math.floor((Date.now() - cronoInicio) / 1000);
    cronometro.textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  }, 500);
}

/* Las barras son el volumen real del micro, desplazandose como un rollo de papel.
   Se escribe el transform en cada barra en vez de una variable CSS en el padre:
   cambiar una variable heredada recalcula el estilo de todos los hijos. */
function empujarNivel(nivel) {
  const alto = Math.min(1, Math.sqrt(nivel) * 2.6);
  for (let i = 0; i < ondas.length - 1; i++) {
    ondas[i].style.transform = ondas[i + 1].style.transform;
  }
  ondas[ondas.length - 1].style.transform = `scaleY(${Math.max(0.16, alto).toFixed(3)})`;
}

// =============================================================================
// Voz en tiempo real (Nova Sonic) con caida automatica a la cascada
// docs/adr/ADR-011-nova-sonic-y-gateway-de-modelos.md: si el WS no llega a
// conectar o Nova Sonic no abre sesion, se cae en silencio a la cascada. Si la
// sesion se corta A MEDIA conversacion NO hay traspaso (recuperar el audio a
// medio grabar es mas riesgo del que vale): se avisa y se reintenta.
// =============================================================================

const MUESTREO_ENTRADA = 16000;
const MUESTREO_SALIDA = 24000;
const CODIGO_CIERRE_FALLBACK = 4500;
const TIMEOUT_INACTIVIDAD_MS = 20000;

let sesionVoz = null;

/* Cuantos intentos seguidos pueden fallar antes de rendirse y quedarse en la
   cascada hasta recargar la pagina.

   Antes bastaba UNO. El razonamiento era bueno para la causa permanente — si el
   modelo no esta habilitado en Bedrock, reintentar en cada clic solo hace perder
   dos segundos por mensaje — pero trataba igual un corte de red de un segundo. Y
   eso se nota: se cae un turno a mitad, y el resto de la conversacion se queda en
   la cascada, mas lenta, sin que nadie diga por que.

   Con dos, una causa permanente sigue rindiendose casi al momento (falla dos veces
   seguidas y ya) y un tropiezo suelto cuesta un reintento. El contador se pone a
   cero en cuanto un turno responde: lo que descalifica es fallar SEGUIDO, no haber
   fallado alguna vez. */
const FALLOS_ANTES_DE_RENDIRSE = 2;
let fallosDeVozSeguidos = 0;

function vozRealtimeDisponible() {
  return fallosDeVozSeguidos < FALLOS_ANTES_DE_RENDIRSE;
}

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
    if (evento.data instanceof ArrayBuffer) {
      if (ws.readyState === WebSocket.OPEN) ws.send(evento.data);
    } else if (evento.data?.nivel !== undefined) {
      empujarNivel(evento.data.nivel);
    }
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
    mensajeActual: null,
    rolActual: null,
    grabando: true,
    recibioRespuesta: false,
  };
  mostrarBarraGrabacion(true);
  reiniciarWatchdog();
  return true;
}

// Nova Sonic acepta texto ademas de audio en la misma sesion ("cross-modal
// input"), asi que el mensaje escrito tambien pasa por ahi primero: misma voz,
// misma latencia, un solo camino de audio que mantener. Si falla, cae a la
// cascada sin que el usuario tenga que hacer nada distinto.
async function enviarTexto(texto) {
  if (vozRealtimeDisponible()) {
    const ws = await abrirSesionVoz();
    if (ws) {
      const mio = agregarMensaje("usuario");
      mio.escribir(texto);
      sesionVoz = {
        modo: "texto",
        ws,
        streamMic: null,
        audioContextEntrada: null,
        nodoCaptura: null,
        audioContextSalida: new AudioContext({ sampleRate: MUESTREO_SALIDA }),
        siguienteInicio: 0,
        mensajeActual: null,
        rolActual: null,
        grabando: false,
        recibioRespuesta: false,
        textoOriginal: texto,
      };
      ws.send(JSON.stringify({ tipo: "mensaje_texto", texto }));
      estado("Pensando");
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
      // En modo texto, Nova Sonic devuelve un "eco" de lo que mandamos como si
      // fuera una transcripcion del usuario: ya lo pintamos al enviarlo.
      if (sesionVoz.modo === "texto" && datos.rol === "usuario") return;
      if (datos.rol !== "usuario") sesionVoz.recibioRespuesta = true;

      // Manda primero un adelanto de lo que va a decir y, DESPUES Y NO SIEMPRE,
      // la transcripcion confirmada. Se muestra el adelanto enseguida (esperar a
      // la confirmada dejaria el chat mudo en los turnos de voz) y se sustituye
      // en cuanto llega la definitiva, que es la fiel a lo que se escucho.
      if (sesionVoz.rolActual !== datos.rol) {
        sesionVoz.mensajeActual = agregarMensaje(datos.rol === "usuario" ? "usuario" : "coach", {
          voz: true,
        });
        sesionVoz.rolActual = datos.rol;
        sesionVoz.adelanto = "";
        sesionVoz.definitivo = "";
        if (datos.rol !== "usuario") {
          sesionVoz.mensajeActual.hablando(true);
          estado("Hablando");
        }
      }
      if (datos.definitiva) sesionVoz.definitivo += datos.texto;
      else sesionVoz.adelanto += datos.texto;

      // Se muestra la version mas completa de las dos, nunca menos de lo que ya
      // se veia: la confirmada llega frase por frase y el turno puede cerrarse
      // antes de que lleguen todas, asi que sustituirla a ciegas recortaba.
      const hayDefinitivo = sesionVoz.definitivo.length >= sesionVoz.adelanto.length;
      sesionVoz.mensajeActual.escribirParcial(
        hayDefinitivo ? sesionVoz.definitivo : sesionVoz.adelanto,
        hayDefinitivo && Boolean(sesionVoz.definitivo),
      );
    } else if (datos.tipo === "turno_terminado") {
      // Un turno completo borra el historial de tropiezos: lo que descalifica a la
      // voz en tiempo real es fallar seguido, no haber fallado alguna vez.
      fallosDeVozSeguidos = 0;
      sesionVoz.mensajeActual?.hablando(false);
      sesionVoz.rolActual = null;
      sesionVoz.mensajeActual = null;
      refrescarPlanTrasElTurno();
      // Un turno por sesion en esta version: se cierra aqui, no al soltar el
      // boton. El audio ya agendado sigue sonando — finalizarSesionVoz() espera
      // a que termine antes de cerrar el AudioContext.
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

// Watchdog de INACTIVIDAD, no un plazo fijo: se reinicia con cada mensaje que
// llega. Un plazo fijo desde que sueltas el boton corta las respuestas largas a
// media frase (Nova Sonic puede hablar mas de 20s seguidos) — fue un bug real.
function reiniciarWatchdog() {
  if (!sesionVoz) return;
  clearTimeout(sesionVoz.timeoutRespuesta);
  sesionVoz.timeoutRespuesta = setTimeout(() => {
    if (!sesionVoz) return;
    if (!sesionVoz.recibioRespuesta) {
      gesto("duda");
      agregarMensaje("coach").escribir("Koda tardó demasiado en responder. Inténtalo otra vez.");
    }
    if (sesionVoz.ws.readyState === WebSocket.OPEN) sesionVoz.ws.close();
    else finalizarSesionVoz(null);
  }, TIMEOUT_INACTIVIDAD_MS);
}

function detenerCapturaVoz() {
  // Sueltas el boton: deja de mandar audio nuevo y avisa "fin_de_audio", pero NO
  // cierra el socket — cerrarlo aqui mataria la sesion antes de que el modelo
  // responda (fue el bug de la primera prueba en navegador).
  if (!sesionVoz || !sesionVoz.grabando) return;
  sesionVoz.grabando = false;
  sesionVoz.nodoCaptura.port.onmessage = null;
  sesionVoz.streamMic.getTracks().forEach((pista) => pista.stop());
  mostrarBarraGrabacion(false);
  botonMic.disabled = true; // evita un segundo clic mientras llega la respuesta
  estado("Pensando");
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
  sesionVoz.mensajeActual?.hablando(false);
  sesionVoz = null;
  mostrarBarraGrabacion(false);

  // CLAVE: Nova Sonic genera el audio mucho mas rapido que en tiempo real, asi
  // que cuando el turno "termina" del lado del servidor todavia quedan segundos
  // agendados sonando en el navegador. Cerrar el AudioContext aqui los destruye
  // y la respuesta se corta a media frase — fue el bug de "se corta mientras
  // seguia hablando". Se espera a que acabe de sonar.
  const segundosRestantes = Math.max(0, siguienteInicio - audioContextSalida.currentTime);
  setTimeout(
    () => {
      audioContextSalida.close().catch(() => {});
      botonMic.disabled = false;
      estado(null);
    },
    (segundosRestantes + 0.3) * 1000,
  );

  if (codigo === CODIGO_CIERRE_FALLBACK) {
    fallosDeVozSeguidos += 1;
    // Al log del navegador y no a la cara del runner: para diagnosticar por que se
    // cayo hay que mirar tambien el servidor, y este numero dice cual de los dos
    // intentos fue. En pantalla, un aviso por cada tropiezo seria peor que el
    // tropiezo.
    console.warn(
      `Voz en tiempo real caida (${fallosDeVozSeguidos}/${FALLOS_ANTES_DE_RENDIRSE}). ` +
        "Si se repite, mira el log del servidor: 'No se pudo abrir sesion de Nova Sonic'.",
    );
    if (habiaTurnoActivo) {
      gesto("duda");
      agregarMensaje("coach").escribir(
        "Se cortó la conexión de voz en tiempo real. Inténtalo otra vez.",
      );
      return;
    }
  }

  // Si la sesion termino sin una sola respuesta (Nova Sonic mudo, cierre
  // inesperado...), el usuario no puede quedarse sin contestacion: se reintenta
  // por la cascada, que trae su propio gateway de modelos por dentro.
  if (!recibioRespuesta) {
    if (modo === "texto") {
      enviarMensaje({ texto: textoOriginal, mensajeUsuarioYaPuesto: true });
    } else if (codigo === CODIGO_CIERRE_FALLBACK) {
      iniciarGrabacionCascada();
    }
  }
}

async function alternarMicrofono() {
  if (mediaRecorder && mediaRecorder.state === "recording") {
    mediaRecorder.stop();
    return;
  }
  if (estaGrabandoTiempoReal()) {
    detenerCapturaVoz();
    return;
  }

  if (vozRealtimeDisponible()) {
    botonMic.disabled = true;
    const conectado = await iniciarVozTiempoReal().catch(() => false);
    botonMic.disabled = false;
    if (conectado) return;
  }
  await iniciarGrabacionCascada();
}

botonMic.addEventListener("click", alternarMicrofono);
botonParar.addEventListener("click", alternarMicrofono);

// =============================================================================
// Paneles
// =============================================================================

const DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"];
const DIAS_CORTOS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"];
// "Tu 42K" encima de una etiqueta que ya dice 42K era decir lo mismo dos veces.
const NOMBRE_DISTANCIA = {
  "5K": "Tu 5K",
  "10K": "Tu 10K",
  "21K": "Media maratón",
  "42K": "Maratón",
};
const ICONO_SESION = {
  facil: "zapatilla",
  largo: "ruta",
  series: "rayo",
  tempo: "crono",
  cruzado: "pulso",
  descanso: "descanso",
};

const app = document.getElementById("pantalla-chat");
const velo = document.getElementById("velo");
const panelPlan = document.getElementById("panel-plan");
const panelPerfil = document.getElementById("panel-perfil");
const contenidoPlan = document.getElementById("contenido-plan");
const formPerfil = document.getElementById("form-perfil");
const mensajePerfil = document.getElementById("mensaje-perfil");

// A partir de 1200px el plan cabe al lado sin apretar la conversacion, asi que
// deja de ser un cajon que tapa y pasa a ser una columna fija.
const anchoParaAnclar = window.matchMedia("(min-width: 1200px)");

function planAnclado() {
  return anchoParaAnclar.matches;
}

function abrirPanel(panel) {
  panel.hidden = false;
  if (panel === panelPlan && planAnclado()) return;
  velo.hidden = false;
  // Dos fotogramas: el navegador tiene que pintar el estado cerrado antes de que
  // la clase lo abra, o no hay transicion que animar.
  requestAnimationFrame(() =>
    requestAnimationFrame(() => {
      panel.classList.add("abierto");
      velo.classList.add("abierto");
    }),
  );
}

function cerrarPanel(panel) {
  if (panel === panelPlan && planAnclado()) return;
  panel.classList.remove("abierto");
  velo.classList.remove("abierto");
  const alTerminar = () => {
    if (!panel.classList.contains("abierto")) {
      panel.hidden = true;
      velo.hidden = true;
    }
  };
  panel.addEventListener("transitionend", alTerminar, { once: true });
  setTimeout(alTerminar, 500); // por si la transicion no llega a dispararse
  if (panel === panelPerfil) modoBienvenida(false);
}

const EASE_OUT = "cubic-bezier(0.23, 1, 0.32, 1)";
const menosMovimiento = window.matchMedia("(prefers-reduced-motion: reduce)");
const esHoja = window.matchMedia("(max-width: 759px)");

/* Arrastrar la hoja para cerrarla. En móvil el panel sube desde abajo y enseña un
   asa: el asa promete que se puede empujar hacia abajo, así que tiene que cumplirlo.
   Se arrastra solo desde la cabecera — desde el contenido pelearía con el scroll. */
function hacerArrastrable(panel) {
  const asa = panel.querySelector(".cabecera-panel");
  let origenY = null;
  let origenTiempo = 0;
  let recorrido = 0;

  asa.addEventListener("pointerdown", (evento) => {
    if (!esHoja.matches || panel.classList.contains("modo-bienvenida")) return;
    origenY = evento.clientY;
    origenTiempo = Date.now();
    recorrido = 0;
    // Captura del puntero: si el dedo se sale del asa, el arrastre sigue siendo suyo.
    asa.setPointerCapture(evento.pointerId);
    panel.classList.add("arrastrando");
  });

  asa.addEventListener("pointermove", (evento) => {
    if (origenY === null) return;
    const delta = evento.clientY - origenY;
    // Hacia arriba no hay a dónde ir, pero en vez de un tope seco se deja avanzar
    // con rozamiento: en la vida real las cosas frenan, no chocan.
    recorrido = delta > 0 ? delta : delta / 4;
    panel.style.transform = `translateY(${recorrido}px)`;
  });

  const soltar = () => {
    if (origenY === null) return;
    const velocidad = Math.abs(recorrido) / Math.max(Date.now() - origenTiempo, 1);
    origenY = null;
    panel.classList.remove("arrastrando");
    panel.style.transform = "";
    // Un golpe rápido basta; no hay que arrastrar media pantalla para cerrar.
    if (recorrido > panel.offsetHeight * 0.28 || (recorrido > 40 && velocidad > 0.11)) {
      cerrarPanel(panel);
    }
  };

  asa.addEventListener("pointerup", soltar);
  asa.addEventListener("pointercancel", soltar);
}

/* Acordeón de las semanas. Es la única animación que cuesta layout en cada
   fotograma, así que va corta. No se puede animar hacia `auto`: hay que medir. */
function comoAcordeon(detalle) {
  const cuerpo = detalle.querySelector(".sesiones");
  detalle.querySelector("summary").addEventListener("click", (evento) => {
    if (menosMovimiento.matches) return;
    evento.preventDefault();
    const alto = `${cuerpo.scrollHeight}px`;

    if (!detalle.open) {
      detalle.open = true;
      cuerpo.animate([{ height: "0px" }, { height: alto }], {
        duration: 200,
        easing: EASE_OUT,
      });
      return;
    }
    const animacion = cuerpo.animate([{ height: alto }, { height: "0px" }], {
      duration: 200,
      easing: EASE_OUT,
    });
    animacion.onfinish = () => {
      detalle.open = false;
    };
  });
}

function sincronizarAnclaje() {
  const anclado = planAnclado();
  app.classList.toggle("plan-anclado", anclado);
  // Anclado, el plan no se "abre": ya está ahí. El botón del rail pasa a ser el
  // indicador de sección visible, no un interruptor.
  document
    .querySelector('.boton-rail[data-abre="panel-plan"]')
    ?.setAttribute("aria-current", String(anclado));
  if (anclado) {
    panelPlan.hidden = false;
    panelPlan.classList.remove("abierto");
    velo.classList.remove("abierto");
    velo.hidden = true;
    if (!contenidoPlan.childElementCount) cargarPlan({ abrir: false });
  } else if (!panelPlan.classList.contains("abierto")) {
    panelPlan.hidden = true;
  }
}

anchoParaAnclar.addEventListener("change", sincronizarAnclaje);
[panelPlan, panelPerfil].forEach(hacerArrastrable);

document.querySelectorAll("[data-abre]").forEach((boton) => {
  boton.addEventListener("click", () => {
    if (boton.dataset.abre !== "panel-plan") {
      abrirPerfil();
      return;
    }
    // Con el plan anclado el botón lo recarga y lo lleva arriba; abrirlo no
    // tendría sentido porque ya está a la vista.
    cargarPlan({ abrir: true });
    if (planAnclado()) contenidoPlan.scrollTo({ top: 0, behavior: "smooth" });
  });
});

document.querySelectorAll(".cerrar-panel").forEach((boton) => {
  boton.addEventListener("click", () => cerrarPanel(boton.closest(".panel")));
});

velo.addEventListener("click", () => {
  document.querySelectorAll(".panel.abierto").forEach(cerrarPanel);
});

document.addEventListener("keydown", (evento) => {
  if (evento.key !== "Escape") return;
  document.querySelectorAll(".panel.abierto:not(.modo-bienvenida)").forEach(cerrarPanel);
});

// --- Fechas ------------------------------------------------------------------

function comoFecha(iso) {
  // El backend manda YYYY-MM-DD. new Date("2026-11-08") se interpreta como UTC y
  // en husos al oeste retrocede un dia: se construye a mano para que el domingo
  // no aparezca como sabado.
  const [anio, mes, dia] = iso.split("-").map(Number);
  return new Date(anio, mes - 1, dia);
}

function fechaCorta(iso) {
  return comoFecha(iso).toLocaleDateString("es-MX", { day: "numeric", month: "short" });
}

function diasHasta(iso) {
  const hoy = new Date();
  hoy.setHours(0, 0, 0, 0);
  return Math.round((comoFecha(iso) - hoy) / 86400000);
}

// =============================================================================
// El plan
// =============================================================================

function nodoVacio(nombreIcono, titulo, detalle) {
  const caja = crear("div", "vacio");
  caja.appendChild(icono(nombreIcono));
  caja.appendChild(crear("strong", null, titulo));
  caja.appendChild(crear("p", null, detalle));
  return caja;
}

/* La pista: una barra por semana, la altura es el volumen. El plan se cuenta
   hacia atras desde la carrera, asi que la caida del final no es un fallo — es el
   taper, y de un vistazo se ve donde estas y cuanto falta. */
function nodoPista(plan) {
  const pista = crear("section", "pista");

  const titular = crear("div", "pista-titular");
  const izquierda = crear("div");
  izquierda.appendChild(crear("p", "eyebrow", "Tu objetivo"));
  izquierda.appendChild(
    crear("h3", null, plan.nombre_carrera || NOMBRE_DISTANCIA[plan.distancia] || plan.distancia),
  );
  titular.appendChild(izquierda);

  const faltan = diasHasta(plan.fecha_carrera);
  if (faltan >= 0) {
    const cuenta = crear("div", "cuenta-atras");
    cuenta.appendChild(crear("span", "numero", String(faltan)));
    cuenta.appendChild(crear("span", "unidad", faltan === 1 ? "día" : "días"));
    titular.appendChild(cuenta);
  }
  pista.appendChild(titular);

  const maximo = Math.max(...plan.semanas.map((s) => s.volumen_km), 1);
  const hoy = new Date().toISOString().slice(0, 10);
  const carriles = crear("div", "carriles animar");

  plan.semanas.forEach((semana, indice) => {
    const carril = crear("span", "carril");
    carril.style.height = `${Math.max(8, (semana.volumen_km / maximo) * 100)}%`;
    carril.style.setProperty("--i", String(indice));

    const fechas = semana.sesiones.map((s) => s.fecha);
    const esActual = fechas.some((f) => f >= hoy) && fechas.some((f) => f <= hoy);
    if (esActual) carril.classList.add("carril-actual");
    else if (fechas.every((f) => f < hoy)) carril.classList.add("carril-hecha");
    else if (semana.es_taper) carril.classList.add("carril-taper");
    else if (semana.es_descarga) carril.classList.add("carril-descarga");

    carril.title = `Semana ${semana.numero}: ${semana.volumen_km} km`;
    carriles.appendChild(carril);
  });
  pista.appendChild(carriles);

  const pie = crear("div", "pista-pie");
  const semanas = crear("span", "meta");
  semanas.append(icono("calendario"), crear("span", null, `${plan.semanas.length} semanas`));
  const total = crear("span", "meta");
  total.append(icono("ruta"), crear("span", "dato", `${plan.volumen_total_km} km`));
  const meta = crear("span", "meta");
  meta.append(icono("meta"), crear("span", "dato", fechaCorta(plan.fecha_carrera)));
  pie.append(semanas, total, meta);
  pista.appendChild(pie);

  return pista;
}

function nodoProxima(sesion) {
  const caja = crear("div", "proxima");
  const marca = crear("span", "icono-sesion");
  marca.appendChild(icono(ICONO_SESION[sesion.tipo] || "zapatilla"));
  caja.appendChild(marca);

  const texto = crear("div");
  texto.appendChild(
    crear("p", "cuando", `${DIAS[sesion.dia_semana]} ${fechaCorta(sesion.fecha)}`),
  );
  const descripcion = crear("p");
  conMedidas(descripcion, sesion.descripcion);
  texto.appendChild(descripcion);
  if (sesion.ritmo_objetivo) {
    texto.appendChild(crear("p", "nota", `A ritmo de ${sesion.ritmo_objetivo}`));
  }
  caja.appendChild(texto);
  return caja;
}

function nodoSesion(sesion) {
  const fila = crear("div", `sesion sesion-${sesion.tipo}`);
  fila.appendChild(crear("span", "sesion-dia", DIAS_CORTOS[sesion.dia_semana]));

  const marca = crear("span", "icono-sesion");
  marca.appendChild(icono(ICONO_SESION[sesion.tipo] || "zapatilla"));
  fila.appendChild(marca);

  const texto = crear("span", "sesion-texto");
  if (sesion.tipo === "descanso") texto.textContent = "Descanso";
  else conMedidas(texto, sesion.descripcion);
  fila.appendChild(texto);

  if (sesion.ritmo_objetivo) {
    fila.appendChild(crear("span", "sesion-ritmo", sesion.ritmo_objetivo));
  }
  return fila;
}

function nodoSemana(semana, abierta) {
  const detalle = crear("details", "semana");
  detalle.open = abierta;

  const resumen = crear("summary");
  resumen.appendChild(icono("caret-derecha", "caret"));
  resumen.appendChild(crear("span", "num-semana", `Semana ${semana.numero}`));
  if (semana.es_taper) resumen.appendChild(crear("span", "etiqueta etiqueta-taper", "taper"));
  else if (semana.es_descarga) {
    resumen.appendChild(crear("span", "etiqueta etiqueta-descarga", "descarga"));
  }
  resumen.appendChild(crear("span", "volumen", `${semana.volumen_km} km`));
  detalle.appendChild(resumen);

  const sesiones = crear("div", "sesiones");
  semana.sesiones.forEach((sesion) => sesiones.appendChild(nodoSesion(sesion)));
  detalle.appendChild(sesiones);
  return detalle;
}

// =============================================================================
// Calendario
// =============================================================================

const MESES = [
  "enero", "febrero", "marzo", "abril", "mayo", "junio",
  "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
];
const INICIALES = ["L", "M", "X", "J", "V", "S", "D"];

function claveDelDia(fecha) {
  const mes = String(fecha.getMonth() + 1).padStart(2, "0");
  const dia = String(fecha.getDate()).padStart(2, "0");
  return `${fecha.getFullYear()}-${mes}-${dia}`;
}

/* Un mes completo, no una lista de sesiones. Una lista dice "el martes 8 km"; una
   rejilla deja ver de un vistazo cuántos días seguidos hay descanso, si el largo
   siempre cae en domingo y cuánto falta para la carrera. Eso es lo que un runner
   mira cuando planea su semana. */
function nodoCalendario(plan) {
  const porFecha = new Map();
  for (const semana of plan.semanas) {
    for (const sesion of semana.sesiones) porFecha.set(sesion.fecha, sesion);
  }

  const caja = crear("section", "calendario");
  const cabecera = crear("div", "calendario-cabecera");
  const anterior = crear("button", "boton-icono");
  anterior.type = "button";
  anterior.setAttribute("aria-label", "Mes anterior");
  anterior.appendChild(icono("caret-derecha", "hacia-atras"));
  const titulo = crear("h4", "mes-actual");
  const siguiente = crear("button", "boton-icono");
  siguiente.type = "button";
  siguiente.setAttribute("aria-label", "Mes siguiente");
  siguiente.appendChild(icono("caret-derecha"));
  cabecera.append(anterior, titulo, siguiente);

  const cabeceraDias = crear("div", "calendario-dias");
  INICIALES.forEach((inicial) => cabeceraDias.appendChild(crear("span", null, inicial)));

  const rejilla = crear("div", "calendario-rejilla");
  const detalle = crear("div", "calendario-detalle");
  caja.append(cabecera, cabeceraDias, rejilla, detalle);

  const hoy = new Date();
  hoy.setHours(0, 0, 0, 0);
  const primeraFecha = comoFecha(plan.fecha_inicio);
  const carrera = comoFecha(plan.fecha_carrera);
  // Se abre en el mes de hoy si el plan lo cubre; si no, en el mes en que arranca.
  let visible = hoy >= primeraFecha && hoy <= carrera ? new Date(hoy) : new Date(primeraFecha);
  visible.setDate(1);

  function mostrarDetalle(clave) {
    detalle.replaceChildren();
    const sesion = porFecha.get(clave);
    if (!sesion) {
      detalle.appendChild(crear("p", "letra-chica", "Ese día no hay nada en el plan."));
      return;
    }
    detalle.appendChild(
      crear("p", "cuando", `${DIAS[sesion.dia_semana]} ${fechaCorta(sesion.fecha)}`),
    );
    if (sesion.tipo === "descanso") {
      detalle.appendChild(crear("p", null, "Descanso. Cuenta tanto como correr."));
      return;
    }
    const texto = crear("p");
    conMedidas(texto, sesion.descripcion);
    detalle.appendChild(texto);
    if (sesion.ritmo_objetivo) {
      detalle.appendChild(crear("p", "nota", `A ritmo de ${sesion.ritmo_objetivo}`));
    }
  }

  function pintarMes() {
    titulo.textContent = `${MESES[visible.getMonth()]} ${visible.getFullYear()}`;
    rejilla.replaceChildren();

    // La semana empieza en lunes, como el plan. getDay() cuenta desde el domingo.
    const primero = new Date(visible.getFullYear(), visible.getMonth(), 1);
    const hueco = (primero.getDay() + 6) % 7;
    const arranque = new Date(primero);
    arranque.setDate(1 - hueco);

    for (let i = 0; i < 42; i++) {
      const dia = new Date(arranque);
      dia.setDate(arranque.getDate() + i);
      const clave = claveDelDia(dia);
      const sesion = porFecha.get(clave);

      const celda = crear("button", "dia");
      celda.type = "button";
      celda.appendChild(crear("span", "numero-dia", String(dia.getDate())));

      if (dia.getMonth() !== visible.getMonth()) celda.classList.add("dia-fuera");
      if (dia.getTime() === hoy.getTime()) celda.classList.add("dia-hoy");
      if (clave === plan.fecha_carrera) {
        celda.classList.add("dia-carrera");
        celda.appendChild(icono("meta", "marca-carrera"));
      } else if (sesion && sesion.tipo !== "descanso") {
        celda.classList.add(`dia-${sesion.tipo}`);
        celda.appendChild(crear("span", sesion.completada ? "punto punto-hecho" : "punto"));
      }

      const resumen = sesion ? sesion.descripcion : "sin plan";
      celda.setAttribute("aria-label", `${dia.getDate()} de ${MESES[dia.getMonth()]}: ${resumen}`);
      celda.addEventListener("click", () => {
        rejilla.querySelector(".dia-elegido")?.classList.remove("dia-elegido");
        celda.classList.add("dia-elegido");
        mostrarDetalle(clave);
      });
      rejilla.appendChild(celda);
    }

    const tope = new Date(carrera.getFullYear(), carrera.getMonth(), 1);
    const suelo = new Date(primeraFecha.getFullYear(), primeraFecha.getMonth(), 1);
    anterior.disabled = visible <= suelo;
    siguiente.disabled = visible >= tope;
  }

  const moverMes = (paso) => {
    visible = new Date(visible.getFullYear(), visible.getMonth() + paso, 1);
    pintarMes();
    detalle.replaceChildren();
  };
  anterior.addEventListener("click", () => moverMes(-1));
  siguiente.addEventListener("click", () => moverMes(1));

  pintarMes();
  if (plan.proxima_sesion) {
    rejilla
      .querySelector(`[aria-label^="${comoFecha(plan.proxima_sesion.fecha).getDate()} de"]`)
      ?.click();
  }
  return caja;
}

function pintarPlan(plan) {
  contenidoPlan.replaceChildren();

  if (!plan) {
    // Aquí Koda sale corriendo y no como un icono de línea: es la única pantalla del
    // panel que está vacía de verdad, y un hueco con una silueta gris se lee como
    // algo que falló al cargar. Con el personaje se lee como lo que es — todavía no
    // hay nada porque no se lo has pedido.
    const vacio = nodoVacio(
      "meta",
      "Todavía no tienes plan",
      "Dile a Koda qué carrera quieres correr y para cuándo. Te lo arma en el momento.",
    );
    vacio.classList.add("vacio-con-koda");
    vacio.querySelector("svg")?.replaceWith(
      Object.assign(new Image(491, 520), { src: "/koda/corriendo.webp", alt: "" }),
    );
    contenidoPlan.appendChild(vacio);
    return;
  }

  contenidoPlan.appendChild(nodoPista(plan));

  if (plan.proxima_sesion) contenidoPlan.appendChild(nodoProxima(plan.proxima_sesion));

  // Dos formas de mirar el mismo plan, no dos sitios distintos donde buscarlo: el
  // calendario responde "¿qué hago el jueves?" y las semanas "¿cuánto voy a correr
  // este mes?". Partirlas en dos paneles obligaría a recordar en cuál está cada cosa.
  const semanaDeLaProxima = plan.proxima_sesion
    ? plan.semanas.find((s) => s.sesiones.some((x) => x.fecha === plan.proxima_sesion.fecha))
    : null;
  const semanas = crear("div", "semanas");
  plan.semanas.forEach((semana) =>
    semanas.appendChild(nodoSemana(semana, semana === semanaDeLaProxima)),
  );
  semanas.querySelectorAll(".semana").forEach(comoAcordeon);

  const calendario = nodoCalendario(plan);
  const selector = crear("div", "selector-vista");
  const vistas = [
    ["Calendario", calendario],
    ["Semanas", semanas],
  ];
  vistas.forEach(([nombre, nodo], indice) => {
    const boton = crear("button", "opcion-vista", nombre);
    boton.type = "button";
    boton.setAttribute("aria-pressed", String(indice === 0));
    nodo.hidden = indice !== 0;
    boton.addEventListener("click", () => {
      vistas.forEach(([, otro], i) => {
        otro.hidden = i !== indice;
        selector.children[i].setAttribute("aria-pressed", String(i === indice));
      });
    });
    selector.appendChild(boton);
  });
  contenidoPlan.append(selector, calendario, semanas);

  // El plan se cuenta hacia atras desde la carrera, asi que su arranque suele caer
  // unos dias por delante. Decirlo evita que parezca un error de fechas.
  const hoy = new Date().toISOString().slice(0, 10);
  if (plan.fecha_inicio > hoy) {
    const nota = crear("p", "nota-destacada");
    nota.appendChild(icono("calendario"));
    const texto = crear("span");
    texto.appendChild(crear("strong", null, `Arranca el ${fechaCorta(plan.fecha_inicio)}. `));
    texto.appendChild(
      document.createTextNode(
        "El plan se cuenta hacia atrás desde la carrera para que la bajada de carga caiga " +
          "justo antes. Hasta entonces, rodajes suaves y sin prisa.",
      ),
    );
    nota.appendChild(texto);
    contenidoPlan.appendChild(nota);
  }

  const bloqueZonas = crear("section", "bloque");
  bloqueZonas.appendChild(crear("h4", null, "Tus ritmos"));
  const zonas = crear("ul", "zonas");
  Object.entries(plan.zonas).forEach(([nombre, ritmo]) => {
    const item = crear("li");
    item.appendChild(crear("span", "nombre-zona", nombre));
    item.appendChild(crear("span", "dato", ritmo));
    zonas.appendChild(item);
  });
  bloqueZonas.appendChild(zonas);
  if (plan.ritmos_estimados) {
    bloqueZonas.appendChild(
      crear("p", "letra-chica", "Estimados. En cuanto registres una marca real, los ajusto."),
    );
  }
  contenidoPlan.appendChild(bloqueZonas);

  plan.notas.forEach((texto) => {
    const nota = crear("p", "nota-destacada");
    nota.appendChild(icono("info"));
    nota.appendChild(crear("span", null, texto));
    contenidoPlan.appendChild(nota);
  });

  escalonarEntrada(contenidoPlan);
}

/* Las tarjetas del panel entran en cascada. Es una superficie ocasional, no algo
   que se vea cien veces al día — y el escalonado nunca bloquea: se puede tocar
   cualquier cosa mientras entra. */
function escalonarEntrada(contenedor) {
  contenedor.classList.remove("escalonar");
  [...contenedor.children].forEach((hijo, indice) => {
    hijo.style.setProperty("--i", String(Math.min(indice, 6)));
  });
  // Un reflow forzado entre quitar y poner la clase, o el navegador agrupa los dos
  // cambios y la animación no se vuelve a lanzar.
  void contenedor.offsetHeight;
  contenedor.classList.add("escalonar");
}

/* Lo que hace único a un plan. Sirve para saber si el que acaba de llegar es otro,
   sin comparar el objeto entero: la API devuelve las semanas calculadas y dos
   respuestas del mismo plan no tienen por qué ser idénticas byte a byte. */
function huellaDelPlan(plan) {
  return plan ? `${plan.distancia_km}|${plan.fecha_carrera}|${plan.fecha_inicio}` : null;
}

// undefined = todavía no se ha mirado nunca. Distinto de null, que es "se miró y no
// hay plan": sin esa diferencia, abrir la app con un plan de hace tres semanas se
// celebraría como si Koda acabara de armarlo.
let planConocido;

async function cargarPlan({ abrir = true, silencioso = false } = {}) {
  if (abrir) abrirPanel(panelPlan);

  // Esqueleto con la forma de lo que va a llegar, no una ruleta: cuando el
  // contenido aparece no salta nada de sitio. En la recarga de después de cada
  // turno no se pone: el panel ya tiene contenido bueno delante y sustituirlo por
  // un esqueleto sería un parpadeo por cada frase que dice Koda.
  if (!silencioso) {
    const esqueleto = crear("div", "esqueleto");
    esqueleto.style.height = "190px";
    contenidoPlan.replaceChildren(esqueleto);
  }

  try {
    const resp = await fetch("/api/plan");
    const plan = resp.ok ? await resp.json() : null;
    const huella = huellaDelPlan(plan);
    const cambio = huella !== planConocido;
    if (planConocido !== undefined && huella && cambio) gesto("celebra");
    planConocido = huella;
    // En la recarga silenciosa solo se repinta si de verdad cambió algo. Repintar
    // por repintar relanzaría la cascada de entrada de las tarjetas en cada frase
    // que dice Koda, con el panel anclado y a la vista.
    if (cambio || !silencioso) pintarPlan(plan);
  } catch {
    if (silencioso) return; // el panel se queda como estaba; ya se avisará al abrirlo
    contenidoPlan.replaceChildren(
      nodoVacio("alerta", "No pude cargar tu plan", "Revisa tu conexión e inténtalo otra vez."),
    );
  }
}

/* Koda puede haber creado o cambiado el plan durante el turno — lo hace con una
   herramienta, y el navegador no se entera. Sin esto, el panel enseñaba el plan
   viejo hasta que al runner se le ocurría volver a abrirlo, justo después de oír
   "ya te lo armé". */
function refrescarPlanTrasElTurno() {
  cargarPlan({ abrir: false, silencioso: true }).catch(() => {});
}

// =============================================================================
// Perfil
// =============================================================================

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
  // En la bienvenida no se enseñan: primero lo mínimo para poder entrenar.
  if (activo) seccionAvisos.hidden = true;
}

saltarPerfil.addEventListener("click", () => cerrarPanel(panelPerfil));

async function abrirPerfil() {
  modoBienvenida(false);
  abrirPanel(panelPerfil);
  mensajePerfil.hidden = true;
  try {
    await rellenarPerfil();
    await cargarAvisos();
  } catch {
    /* el formulario se queda vacio: se puede rellenar igual */
  }
}

async function pedirPerfilSiHaceFalta() {
  try {
    const perfil = await rellenarPerfil();
    // Sin nivel ni dias disponibles no se puede calcular nada util. El nombre y
    // la edad son bonitos de tener; estos dos entran en la cuenta.
    if (!perfil || perfil.nivel || perfil.dias_disponibles) return;
    mensajePerfil.hidden = true;
    modoBienvenida(true);
    abrirPanel(panelPerfil);
  } catch {
    /* si no se puede consultar el perfil, se entra al chat sin mas */
  }
}

// El navegador ya sabe en qué huso estás; preguntarlo en un desplegable sería
// hacerte trabajo que no hace falta. De este dato depende que un aviso de las 6
// llegue a las 6.
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

formPerfil.addEventListener("submit", async (evento) => {
  evento.preventDefault();
  const boton = formPerfil.querySelector("button[type=submit]");
  conCargador(boton, true);

  // Solo se mandan los campos con valor: null en la API significa "no me lo has
  // dicho", nunca "bórralo".
  const cuerpo = {};
  Object.entries(camposPerfil).forEach(([campo, input]) => {
    const valor = input.value.trim();
    if (valor) cuerpo[campo] = input.type === "number" ? Number(valor) : valor;
  });

  // Una marca a medias no sirve: el ritmo sale de dividir tiempo entre distancia,
  // asi que con una sola de las dos el plan seguiria con ritmos estimados y el
  // runner creeria que ya dio su dato.
  const segundos = aSegundos(campoMarcaTiempo.value);
  const hayDistancia = Boolean(cuerpo.marca_distancia_km);
  if (hayDistancia !== Boolean(segundos)) {
    mensajePerfil.textContent = hayDistancia
      ? "Falta el tiempo de esa marca: sin él no puedo calcular tus ritmos."
      : "¿Sobre qué distancia es ese tiempo?";
    mensajePerfil.hidden = false;
    conCargador(boton, false);
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
      : "No pudimos guardarlo. Revisa los datos e inténtalo otra vez.";
    // En la bienvenida, guardar es la puerta al chat: se deja leer el mensaje y
    // se pasa.
    if (resp.ok && panelPerfil.classList.contains("modo-bienvenida")) {
      setTimeout(() => cerrarPanel(panelPerfil), 900);
    }
  } catch {
    mensajePerfil.textContent = "No pudimos guardarlo. Inténtalo otra vez.";
  } finally {
    mensajePerfil.hidden = false;
    conCargador(boton, false);
  }
});

// =============================================================================
// Recordatorios
// =============================================================================

const seccionAvisos = document.getElementById("seccion-avisos");
const listaAvisos = document.getElementById("lista-avisos");
const mensajeAvisos = document.getElementById("mensaje-avisos");

const AVISOS = {
  diario: { nombre: "Qué me toca hoy", icono: "rayo" },
  checkin: { nombre: "¿Saliste hoy?", icono: "luna" },
  semanal: { nombre: "Resumen del domingo", icono: "calendario" },
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
  const definicion = AVISOS[aviso.tipo] || { nombre: aviso.tipo, icono: "campana" };
  const fila = crear("div", "aviso");

  const marca = crear("span", "icono-aviso");
  marca.appendChild(icono(definicion.icono));
  fila.appendChild(marca);

  const activo = document.createElement("input");
  activo.type = "checkbox";
  activo.checked = aviso.activo;
  activo.id = `aviso-${aviso.tipo}`;

  const texto = crear("div", "aviso-texto");
  const etiqueta = document.createElement("label");
  etiqueta.htmlFor = activo.id;
  etiqueta.textContent = definicion.nombre;
  texto.appendChild(etiqueta);
  fila.appendChild(texto);

  const hora = document.createElement("input");
  hora.type = "time";
  hora.value = aviso.hora_local;
  hora.disabled = !aviso.activo;
  fila.appendChild(hora);

  const interruptor = crear("span", "interruptor");
  interruptor.append(activo, crear("span", "pista-interruptor"));
  fila.appendChild(interruptor);

  activo.addEventListener("change", () => {
    hora.disabled = !activo.checked;
    guardarAviso(aviso.tipo, hora.value, activo.checked);
  });
  hora.addEventListener("change", () => guardarAviso(aviso.tipo, hora.value, activo.checked));

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

init();
