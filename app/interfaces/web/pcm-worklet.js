// AudioWorklet que corre en el hilo de audio: convierte el Float32 que entrega la
// Web Audio API a Int16 PCM crudo, el formato que espera Nova Sonic (16kHz mono).
// El AudioContext que carga esto ya se crea a 16000Hz -- ver iniciarVozTiempoReal()
// en app.js.
//
// Ademas del audio manda el volumen (RMS) cada pocos bloques. Ese numero es lo que
// mueve las barras de la barra de grabacion: si no se mueven, el micro no esta
// captando nada, y eso se ve ANTES de mandar el audio en vez de despues.
const BLOQUES_POR_MEDICION = 4;

class PCMCapturador extends AudioWorkletProcessor {
  constructor() {
    super();
    this.bloques = 0;
  }

  process(inputs) {
    const canal = inputs[0][0];
    if (!canal) return true;

    const pcm16 = new Int16Array(canal.length);
    let suma = 0;
    for (let i = 0; i < canal.length; i++) {
      const muestra = Math.max(-1, Math.min(1, canal[i]));
      suma += muestra * muestra;
      pcm16[i] = muestra < 0 ? muestra * 0x8000 : muestra * 0x7fff;
    }

    this.bloques += 1;
    if (this.bloques % BLOQUES_POR_MEDICION === 0) {
      this.port.postMessage({ nivel: Math.sqrt(suma / canal.length) });
    }

    // El buffer se transfiere, no se copia: el audio no pasa por el recolector de
    // basura en mitad de una conversacion.
    this.port.postMessage(pcm16.buffer, [pcm16.buffer]);
    return true;
  }
}

registerProcessor("pcm-capturador", PCMCapturador);
