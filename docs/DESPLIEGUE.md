# Poner Koda en internet

Koda vive en **una instancia EC2** con tres contenedores: PostgreSQL, la aplicación y
Caddy, que es quien pone el HTTPS. La razón de que sea una instancia y no un servicio
gestionado está en [ADR-019](adr/ADR-019-una-instancia-y-caddy-para-el-https.md).

**El HTTPS no es un adorno.** `getUserMedia` — el micrófono — solo existe en un origen
seguro. Sin certificado, Koda no puede oír a nadie desde un móvil, y la mitad del
proyecto deja de poder enseñarse.

Tiempo estimado la primera vez: **35–45 minutos**.

---

## Antes de empezar

Necesitas, en la cuenta de AWS y con un usuario que **sí** tenga permisos de EC2 (el
usuario `koda-dev` de la aplicación no los tiene, y está bien que no los tenga):

- Acceso a la consola de EC2 en `us-east-1`
- Las credenciales de `koda-dev` a mano — son las mismas del `.env` local

---

## 1. Crear la instancia

Consola de EC2 → **Lanzar instancia**.

| Campo | Valor | Por qué |
|---|---|---|
| Nombre | `koda` | |
| AMI | **Ubuntu Server 24.04 LTS** | Docker se instala en dos comandos |
| Tipo | **t3.small** (2 GB) | Con 1 GB, Postgres y la aplicación juntos se quedan sin memoria al construir la imagen |
| Par de claves | Crear uno nuevo, `koda.pem` | Guárdalo; sin él no se entra |
| Almacenamiento | 20 GB gp3 | Las imágenes de Docker ocupan ~1,5 GB |

En **Configuración de red** → *Editar* → grupo de seguridad nuevo, con estas tres
reglas de entrada y **ninguna más**:

| Tipo | Puerto | Origen |
|---|---|---|
| SSH | 22 | **Mi IP** ← no `0.0.0.0/0` |
| HTTP | 80 | `0.0.0.0/0` |
| HTTPS | 443 | `0.0.0.0/0` |

El 80 hace falta aunque todo vaya por HTTPS: es por donde Let's Encrypt comprueba que
el servidor es tuyo antes de firmar el certificado.

**El 5432 no se abre nunca.** La base de datos solo se ve desde dentro de la red de
Docker.

### La IP tiene que ser fija

Consola de EC2 → **IP elásticas** → *Asignar* → *Asociar* a la instancia `koda`.

Sin esto, la IP cambia cada vez que la instancia se para y arranca. Y como el nombre
del sitio se deriva de la IP (paso 3), cambiarla invalida el certificado y rompe los
enlaces mágicos que ya se enviaron por correo.

---

## 2. Instalar Docker

```bash
ssh -i koda.pem ubuntu@TU_IP_ELASTICA
```

```bash
sudo apt-get update && sudo apt-get install -y ca-certificates curl git
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker ubuntu
```

Sal y vuelve a entrar para que el grupo `docker` haga efecto:

```bash
exit
ssh -i koda.pem ubuntu@TU_IP_ELASTICA
docker run --rm hello-world
```

---

## 3. El nombre del sitio, sin comprar dominio

Let's Encrypt no firma certificados para direcciones IP, así que hace falta un nombre.
Comprar un dominio para una prueba técnica es tiempo y dinero por algo que se va a
tirar, así que se usa **sslip.io**: un DNS público que resuelve cualquier nombre con
la forma `1-2-3-4.sslip.io` a la IP `1.2.3.4`.

Si tu IP elástica es `54.91.20.3`, tu sitio es:

```
https://54-91-20-3.sslip.io
```

Comprueba que resuelve antes de seguir — si esto falla, el certificado también fallará:

```bash
getent hosts 54-91-20-3.sslip.io
```

> Es un apaño explícito y tiene su precio: el enlace es feo y depende de un servicio
> de terceros. Está en las consecuencias negativas del ADR-019.

---

## 4. Clonar y configurar

```bash
git clone https://github.com/mateomartin21/Chatbot-Koda.git koda
cd koda
```

El `.env` se escribe a mano en el servidor. **No sale del repositorio ni viaja en la
imagen de Docker** — el `.dockerignore` lo excluye a propósito, porque una imagen se
comparte y sus capas guardan lo que se horneó dentro.

```bash
nano .env
```

Copia esto y rellena los cuatro valores marcados:

```bash
# --- Servidor ---
DOMINIO=54-91-20-3.sslip.io                    # ← tu IP con guiones
APP_BASE_URL=https://54-91-20-3.sslip.io       # ← el mismo, con https://
APP_ENV=production
LOG_LEVEL=INFO

# --- Base de datos ---
POSTGRES_PASSWORD=                             # ← genérala abajo

# --- Seguridad ---
JWT_SECRET=                                    # ← genéralo abajo
JWT_EXPIRE_DAYS=30
MAGIC_LINK_TTL_MINUTES=15

# --- Proveedores ---
PROVIDER_STT=aws
PROVIDER_LLM=aws
PROVIDER_TTS=aws
PROVIDER_EMAIL=aws

# --- AWS (las mismas del .env local) ---
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
BEDROCK_MODEL_ID=
BEDROCK_MODEL_ID_BARATO=
SES_FROM_EMAIL=
GROQ_API_KEY=
```

Los dos secretos, cada uno distinto:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # JWT_SECRET
python3 -c "import secrets; print(secrets.token_urlsafe(24))"   # POSTGRES_PASSWORD
```

`APP_BASE_URL` **tiene que ser el `https://`**. Es lo que se pega dentro de los enlaces
mágicos: si se queda en `http://localhost:8000`, los correos llevan a un sitio que solo
existe en tu portátil.

Que el `.env` no lo lea nadie más:

```bash
chmod 600 .env
```

### Sobre las credenciales de AWS

Van en el `.env`, no en un rol de instancia, y esto **no** es dejadez. El SDK de Nova
Sonic (`aws_sdk_bedrock_runtime`) resuelve credenciales **solo** por variables de
entorno: con un rol de IAM, la voz en tiempo real deja de funcionar. Está explicado en
`app/infrastructure/aws_session.py` y en las consecuencias negativas del ADR-019.

---

## 5. Levantar

```bash
docker compose up -d --build
```

La primera vez tarda unos 4 minutos: construye la imagen, arranca Postgres, aplica las
migraciones en un contenedor aparte y solo entonces arranca la aplicación. Si una
migración falla, la aplicación **no** arranca — un fallo de despliegue tiene que verse
como un fallo de despliegue, no como una aplicación que contesta 500 a todo.

```bash
docker compose ps
docker compose logs -f caddy      # aquí se ve pedir el certificado
```

Cuando Caddy diga `certificate obtained successfully`, ya está:

```
https://54-91-20-3.sslip.io
```

---

## 6. Comprobar que de verdad funciona

Desde tu máquina:

```bash
curl -s https://54-91-20-3.sslip.io/api/health          # {"status":"ok"}
curl -sI https://54-91-20-3.sslip.io/ | head -1         # HTTP/2 200
curl -sI http://54-91-20-3.sslip.io/  | head -1         # 308 → redirige a HTTPS
```

**Y desde el móvil**, que es lo único que demuestra que está terminado:

1. Abre la portada y entra con tu correo
2. Comprueba que el enlace del correo apunta a `https://…sslip.io`, no a `localhost`
3. **Mantén pulsado el micrófono y habla** ← si esto funciona, el HTTPS está bien
4. Manda una foto de tu reloj
5. Menú del navegador → **Añadir a pantalla de inicio**. Debe abrirse a pantalla
   completa, sin barra de direcciones y con el icono de Koda

---

## Actualizar después de un cambio

```bash
ssh -i koda.pem ubuntu@TU_IP
cd koda && git pull && docker compose up -d --build
```

Los datos sobreviven: viven en un volumen de Docker, no en los contenedores.

---

## Cuando algo falla

| Síntoma | Casi siempre es |
|---|---|
| Caddy no consigue el certificado | El puerto 80 no está abierto, o `DOMINIO` no coincide con la IP |
| El micrófono no aparece en el móvil | Entraste por `http://`. Tiene que ser `https://` |
| El correo lleva a `localhost` | `APP_BASE_URL` se quedó con el valor de desarrollo |
| `502 Bad Gateway` | La aplicación no arrancó: `docker compose logs app` |
| La aplicación reinicia en bucle | Suele ser un ajuste sin valor en el `.env`. `Settings` se niega a construirse sin `JWT_SECRET` |
| El correo no llega | SES en sandbox: el destinatario tiene que estar verificado ([ADR-010](adr/ADR-010-sin-dominio-propio-para-ses.md)) |

Los logs de todo, juntos:

```bash
docker compose logs -f
```

---

## Apagarlo

Mientras la instancia esté encendida, consume crédito. Al terminar la evaluación:

1. Consola de EC2 → **Terminar** la instancia
2. **IP elásticas** → *Liberar* la IP ← una IP elástica sin instancia asociada **se
   cobra igual**, y es la factura sorpresa más común de AWS
