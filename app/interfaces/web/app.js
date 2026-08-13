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

async function enviarMensaje({ texto, audioBlob }) {
  const formData = new FormData();
  if (texto) formData.append("texto", texto);
  if (audioBlob) formData.append("audio", audioBlob, "mensaje.webm");

  agregarBurbuja(texto || "🎙️ (mensaje de voz)", "usuario");
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

formMensaje.addEventListener("submit", (evento) => {
  evento.preventDefault();
  const texto = inputTexto.value.trim();
  if (!texto) return;
  inputTexto.value = "";
  enviarMensaje({ texto });
});

let mediaRecorder = null;
let fragmentosAudio = [];

botonMic.addEventListener("click", async () => {
  if (mediaRecorder && mediaRecorder.state === "recording") {
    mediaRecorder.stop();
    return;
  }

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
    agregarBurbuja("No pude acceder al micrófono. Revisa los permisos del navegador.", "coach");
  }
});

init();
