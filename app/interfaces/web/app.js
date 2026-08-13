const form = document.getElementById("form-solicitar");
const mensaje = document.getElementById("mensaje");

function mostrarMensaje(texto) {
  mensaje.textContent = texto;
  mensaje.hidden = false;
}

form.addEventListener("submit", async (evento) => {
  evento.preventDefault();
  const email = document.getElementById("email").value.trim();
  const boton = form.querySelector("button");
  boton.disabled = true;

  try {
    await fetch("/api/auth/solicitar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    });
    mostrarMensaje("Revisa tu bandeja de entrada — te mandamos un enlace para entrar.");
    form.reset();
  } catch {
    mostrarMensaje("No pudimos enviar el correo. Intenta de nuevo en unos segundos.");
  } finally {
    boton.disabled = false;
  }
});
