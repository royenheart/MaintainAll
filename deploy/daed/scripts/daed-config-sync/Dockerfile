FROM alpine:3.23

RUN apk add --no-cache sqlite

COPY sync-daed-config.sh /usr/local/bin/sync-daed-config

RUN chmod +x /usr/local/bin/sync-daed-config

ENTRYPOINT ["/usr/local/bin/sync-daed-config"]
