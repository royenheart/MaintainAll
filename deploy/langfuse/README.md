# Self-hosted Langfuse

Local/LAN Langfuse for dsh-observability. It runs Langfuse 3 with Postgres, ClickHouse,
Redis, MinIO, and an nginx TLS terminator. The web app is reachable only through nginx
on the LAN; the raw web port is bound to loopback for debugging.

## URLs

- UI / OTLP: `https://<langfuse-host>:3000` (self-signed certificate)
- Raw local web: `http://127.0.0.1:3000` (loopback only)
- OTLP endpoint: `https://<langfuse-host>:3000/api/public/otel`

The certificate is generated for `IP:<bind-ip>` in `tls/` (gitignored). Browsers
must accept the self-signed certificate or trust `tls/cert.pem`; OTLP clients can set
`LANGFUSE_INSECURE=1` for this local deployment.

## Start

```sh
cd deploy/langfuse
cp .env.example .env       # first time only
chmod 600 .env
docker compose -p langfuse-prod up -d
```

`NEXTAUTH_URL` is pinned to `https://<langfuse-host>:3000`; change it, the nginx bind,
and the certificate if the host IP changes.

Generate the self-signed cert if `tls/` is empty:

```sh
openssl req -x509 -newkey rsa:2048 -days 825 -nodes \
  -keyout tls/key.pem -out tls/cert.pem \
  -subj '/CN=<bind-ip>' -addext 'subjectAltName=IP:<bind-ip>'
chmod 600 tls/key.pem
```

## Credentials

Admin login and OTLP keys live in `.env` (gitignored). Read them locally with
`grep 'LANGFUSE_INIT_USER\|LANGFUSE_INIT_PROJECT_.*KEY' .env`; do not paste them into a
report or commit. Do not commit `.env`, `tls/`, or
reuse the example values. Project name: `dsh-observability`.

Set for the bundled exporter:

```sh
export LANGFUSE_HOST=https://<langfuse-host>:3000
export LANGFUSE_PUBLIC_KEY=...
export LANGFUSE_SECRET_KEY=...
export LANGFUSE_INSECURE=1       # self-signed cert only
python3 ../../skills/dsh-observability/scripts/langfuse_export.py result.json
```

## Stop

```sh
docker compose -p langfuse-prod down
```

Use `down -v` only when you intentionally discard all traces, users and projects.
