// AudioWorklet que corre en el hilo de audio: convierte el Float32 que entrega la
// Web Audio API a Int16 PCM crudo, el formato que espera Nova Sonic (16kHz mono).
// El AudioContext que carga esto ya se crea a 16000Hz -- ver iniciarSesionVoz() en app.js.
class PCMCapturador extends AudioWorkletProcessor {
  process(inputs) {
    const canal = inputs[0][0];
    if (canal) {
      const pcm16 = new Int16Array(canal.length);
      for (let i = 0; i < canal.length; i++) {
        const muestra = Math.max(-1, Math.min(1, canal[i]));
        pcm16[i] = muestra < 0 ? muestra * 0x8000 : muestra * 0x7fff;
      }
      this.port.postMessage(pcm16.buffer, [pcm16.buffer]);
    }
    return true;
  }
}

registerProcessor("pcm-capturador", PCMCapturador);
