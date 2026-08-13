"""Comprueba que Transcribe, Bedrock, Polly y SES responden con las credenciales de .env.

Uso:
    python scripts/smoke_aws.py

Definicion de terminado (ver docs/contexto/07-PLAN-EJECUCION.md, Dia 0):
los cuatro servicios responden sin error. No valida la calidad de las
respuestas (el audio de prueba no es voz real), solo la conectividad
y los permisos IAM.
"""

import io
import math
import os
import struct
import sys
import time
import uuid
import wave
from pathlib import Path

import boto3
from dotenv import load_dotenv

load_dotenv()

REGION = os.environ["AWS_REGION"]
BUCKET = os.environ.get("S3_BUCKET")
BEDROCK_MODEL_ID = os.environ["BEDROCK_MODEL_ID"]
SES_FROM = os.environ["SES_FROM_EMAIL"]


def ok(mensaje: str) -> None:
    print(f"  OK  {mensaje}")


def fail(servicio: str, err: object) -> None:
    print(f"  FALLO  {servicio}: {err}")


def _wav_de_prueba() -> bytes:
    """Genera un WAV corto en memoria (tono, no voz real) para no depender de un fixture binario."""
    frecuencia_muestreo = 16000
    duracion_segundos = 2
    tono_hz = 440

    frames = bytearray()
    for i in range(frecuencia_muestreo * duracion_segundos):
        valor = int(3000 * math.sin(2 * math.pi * tono_hz * i / frecuencia_muestreo))
        frames += struct.pack("<h", valor)

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(frecuencia_muestreo)
        wav_file.writeframes(bytes(frames))
    return buffer.getvalue()


def test_transcribe() -> bool:
    print("1/4 - Transcribe")
    if not BUCKET:
        fail("Transcribe", "falta S3_BUCKET en .env - Transcribe (batch) exige que el audio este en S3")
        return False

    s3 = boto3.client("s3", region_name=REGION)
    transcribe = boto3.client("transcribe", region_name=REGION)

    key = f"smoke-test/{uuid.uuid4()}.wav"
    job_name = f"koda-smoke-{uuid.uuid4()}"
    try:
        s3.put_object(Bucket=BUCKET, Key=key, Body=_wav_de_prueba())
        transcribe.start_transcription_job(
            TranscriptionJobName=job_name,
            Media={"MediaFileUri": f"s3://{BUCKET}/{key}"},
            MediaFormat="wav",
            LanguageCode=os.environ.get("TRANSCRIBE_LANGUAGE", "es-MX"),
        )
        for _ in range(30):
            job = transcribe.get_transcription_job(TranscriptionJobName=job_name)["TranscriptionJob"]
            estado = job["TranscriptionJobStatus"]
            if estado == "COMPLETED":
                ok("Transcribe respondio (job completado)")
                return True
            if estado == "FAILED":
                fail("Transcribe", job.get("FailureReason", "job fallido sin motivo reportado"))
                return False
            time.sleep(2)
        fail("Transcribe", "timeout esperando el resultado del job (60s)")
        return False
    except Exception as e:  # noqa: BLE001 - es un script de diagnostico, no logica de dominio
        fail("Transcribe", e)
        return False
    finally:
        try:
            transcribe.delete_transcription_job(TranscriptionJobName=job_name)
        except Exception:  # noqa: BLE001 - limpieza best-effort
            pass
        try:
            s3.delete_object(Bucket=BUCKET, Key=key)
        except Exception:  # noqa: BLE001
            pass


def test_bedrock() -> bool:
    print("2/4 - Bedrock")
    client = boto3.client("bedrock-runtime", region_name=REGION)
    try:
        resp = client.converse(
            modelId=BEDROCK_MODEL_ID,
            messages=[{"role": "user", "content": [{"text": "Responde unicamente con la palabra: ok"}]}],
        )
        texto = resp["output"]["message"]["content"][0]["text"].strip()
        ok(f"Bedrock respondio: {texto!r}")
        return True
    except Exception as e:  # noqa: BLE001
        fail("Bedrock", e)
        return False


def test_polly() -> bool:
    print("3/4 - Polly")
    client = boto3.client("polly", region_name=REGION)
    try:
        resp = client.synthesize_speech(
            Text="Prueba de Koda.",
            OutputFormat=os.environ.get("POLLY_OUTPUT_FORMAT", "mp3"),
            VoiceId=os.environ.get("POLLY_VOICE_ID", "Mia"),
            Engine=os.environ.get("POLLY_ENGINE", "generative"),
        )
        salida = Path(__file__).parent / "smoke_test_output.mp3"
        salida.write_bytes(resp["AudioStream"].read())
        ok(f"Polly respondio (audio guardado en {salida})")
        return True
    except Exception as e:  # noqa: BLE001
        fail("Polly", e)
        return False


def test_ses() -> bool:
    print("4/4 - SES")
    client = boto3.client("sesv2", region_name=REGION)
    try:
        client.send_email(
            FromEmailAddress=SES_FROM,
            Destination={"ToAddresses": [SES_FROM]},
            Content={
                "Simple": {
                    "Subject": {"Data": "Koda - smoke test"},
                    "Body": {"Text": {"Data": "Si ves esto, SES esta enviando correctamente."}},
                }
            },
        )
        ok(f"SES envio el correo a {SES_FROM}")
        return True
    except Exception as e:  # noqa: BLE001
        fail("SES", e)
        return False


def main() -> None:
    print("Koda - smoke test de AWS\n")
    resultados = {
        "Transcribe": test_transcribe(),
        "Bedrock": test_bedrock(),
        "Polly": test_polly(),
        "SES": test_ses(),
    }

    print("\nResumen:")
    for servicio, paso in resultados.items():
        print(f"  {'OK' if paso else 'FALLO':6} {servicio}")

    if not all(resultados.values()):
        sys.exit(1)
    print("\nLos cuatro servicios respondieron sin error.")


if __name__ == "__main__":
    main()
