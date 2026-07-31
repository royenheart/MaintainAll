# DoH mode — for hosts where outbound UDP/TCP 53 is blocked (ICMP/HTTPS fine;
# see deploy/doh-dns). dae dials its DNS upstreams directly (routing.conf:
# pname(daed) -> must_direct), so on such hosts the upstream must NOT use
# port 53. Reuse the host's doh-dns kit: dnscrypt-proxy listens on
# 127.0.0.1:5353 (daed runs with network_mode: host and can reach it).
# If dnscrypt-proxy is unavailable, fall back to direct DoH over 443:
#   localdoh: 'https://223.5.5.5/dns-query'
upstream {
  localdoh: 'udp://127.0.0.1:5353'
}
routing {
  request {
    qname(geosite:cn) -> localdoh
    fallback: localdoh
  }
}
