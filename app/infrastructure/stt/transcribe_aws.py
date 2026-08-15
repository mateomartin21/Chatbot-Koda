"""Adaptador de STTPort sobre Amazon Transcribe (batch, via S3).

NOTA: sin probar contra el servicio real todavia — la cuenta de AWS aun no tiene
Transcribe desbloqueado (SubscriptionRequiredException, ver docs/adr/ADR-009-groq-stt-temporal.md).
La logica sigue el mismo patron verificado en scripts/smoke_aws.py.
"""

import asyncio
import json
import time
import uuid

from app.config import Settings
from app.domain.ports.stt_port import STTPort
from app.infrastructure.aws_session import cliente_aws


class TranscribeAWS(STTPort):
    # Construir un adaptador es cablearlo, no usarlo. Si esto reventara aqui, la
    # aplicacion entera dejaria de poder IMPORTARSE sin una cuenta de AWS
    # configurada — y con ella la suite de tests, que se supone que corre sin
    # credenciales. El aviso temprano no se pierde: vive en el arranque de main.py,
    # que es donde toca y donde se oye mas.
    def __init__(self, settings: Settings) -> None:
        self._s3 = cliente_aws("s3", settings)
        self._transcribe = cliente_aws("transcribe", settings)
        self._bucket = settings.s3_bucket
        self._idioma = settings.transcribe_language

    async def transcribir(self, audio: bytes, audio_mime: str) -> str:
        return await asyncio.to_thread(self._transcribir_sync, audio, audio_mime)

    def _transcribir_sync(self, audio: bytes, audio_mime: str) -> str:
        if not self._bucket:
            raise ValueError("S3_BUCKET no esta configurado")
        extension = audio_mime.split("/")[-1] if "/" in audio_mime else "wav"
        audio_key = f"transcribir/entrada/{uuid.uuid4()}.{extension}"
        salida_key = f"transcribir/salida/{uuid.uuid4()}.json"
        job_name = f"koda-{uuid.uuid4()}"

        self._s3.put_object(Bucket=self._bucket, Key=audio_key, Body=audio)
        try:
            self._transcribe.start_transcription_job(
                TranscriptionJobName=job_name,
                Media={"MediaFileUri": f"s3://{self._bucket}/{audio_key}"},
                MediaFormat=extension,
                LanguageCode=self._idioma,
                OutputBucketName=self._bucket,
                OutputKey=salida_key,
            )
            for _ in range(30):
                job = self._transcribe.get_transcription_job(TranscriptionJobName=job_name)[
                    "TranscriptionJob"
                ]
                estado = job["TranscriptionJobStatus"]
                if estado == "COMPLETED":
                    return self._leer_transcripcion(salida_key)
                if estado == "FAILED":
                    raise RuntimeError(job.get("FailureReason", "job de Transcribe fallido"))
                time.sleep(2)
            raise TimeoutError("Transcribe no termino a tiempo (30s)")
        finally:
            self._transcribe.delete_transcription_job(TranscriptionJobName=job_name)
            self._s3.delete_object(Bucket=self._bucket, Key=audio_key)
            self._s3.delete_object(Bucket=self._bucket, Key=salida_key)

    def _leer_transcripcion(self, salida_key: str) -> str:
        objeto = self._s3.get_object(Bucket=self._bucket, Key=salida_key)
        resultado = json.loads(objeto["Body"].read())
        return resultado["results"]["transcripts"][0]["transcript"].strip()
