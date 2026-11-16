FROM debian:bookworm-slim AS assets
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates python3 && rm -rf /var/lib/apt/lists/*
COPY fetch-editor.py /tmp/fetch-editor.py
RUN python3 /tmp/fetch-editor.py

FROM caddy:2-alpine@sha256:003a97808e781aa9f7e75cc2f43d34d461099031faf5e20faefb9f61126836f0
COPY --from=assets /srv/drawio /srv/drawio
