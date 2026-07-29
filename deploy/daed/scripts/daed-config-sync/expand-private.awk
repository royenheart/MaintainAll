# expand-private.awk — translate config/private.conf DSL.
#
# Usage (file is passed twice: pass 1 collects group names, pass 2 emits):
#   awk -v mode=routing -v known_groups="a b c" -f expand-private.awk private.conf private.conf
#   awk -v mode=groups  -f expand-private.awk private.conf private.conf
#
# mode=routing  -> dae routing rules on stdout
# mode=groups   -> "name|policy|param" lines (groups.txt format) on stdout
# Warnings go to stderr; invalid lines are skipped.

function trim(s) { sub(/^[ \t\r]+/, "", s); sub(/[ \t\r]+$/, "", s); return s }
function warn(msg) { print "warn: private.conf: " msg > "/dev/stderr" }

BEGIN {
  nb = split("direct block proxy must_direct must_block must_proxy", b, " ")
  for (i = 1; i <= nb; i++) known[b[i]] = 1
  nk = split(known_groups, kg, " ")
  for (i = 1; i <= nk; i++) if (kg[i] != "") known[kg[i]] = 1
}

FNR == NR {
  line = $0; sub(/#.*/, "", line); line = trim(line)
  if (line ~ /^group[ \t]/) {
    rest = trim(substr(line, 6))
    eq = index(rest, "=")
    if (eq > 0) {
      name = trim(substr(rest, 1, eq - 1))
      if (name != "") known[name] = 1
    }
  }
  next
}

{
  line = $0; sub(/#.*/, "", line); line = trim(line)
  if (line == "") next

  if (line ~ /^group[ \t]/) {
    if (mode != "groups") next
    rest = trim(substr(line, 6))
    eq = index(rest, "=")
    if (eq == 0) { warn("invalid group line: " $0); next }
    name = trim(substr(rest, 1, eq - 1))
    policy = trim(substr(rest, eq + 1))
    if (name !~ /^[A-Za-z0-9_-]+$/) { warn("invalid group name '" name "'"); next }
    param = ""
    if (policy ~ /^fixed\([0-9]+\)$/) {
      param = policy
      sub(/^fixed\(/, "", param); sub(/\)$/, "", param)
      policy = "fixed"
    }
    if (policy != "random" && policy != "fixed" && policy != "min" && \
        policy != "min_avg10" && policy != "min_moving_avg") {
      warn("unknown policy '" policy "' for group '" name "'"); next
    }
    print name "|" policy "|" param
    next
  }

  if (mode != "routing") next

  arrow = index(line, "->")
  if (arrow == 0) { warn("unrecognized line: " $0); next }
  lhs = trim(substr(line, 1, arrow - 1))
  rhs = trim(substr(line, arrow + 2))
  if (rhs == "") { warn("missing target: " $0); next }
  if (rhs ~ /[ \t]/) { warn("invalid target '" rhs "'"); next }
  if (!(rhs in known)) { warn("target '" rhs "' is not a known group, skipping rule"); next }
  if (lhs ~ /\(/) { print line; next }

  c = index(lhs, ":")
  if (c == 0) { warn("invalid matcher '" lhs "'"); next }
  m = trim(substr(lhs, 1, c - 1))
  v = trim(substr(lhs, c + 1))
  nv = split(v, parts, ",")
  vals = ""
  for (i = 1; i <= nv; i++) {
    p = trim(parts[i])
    if (p == "") continue
    vals = (vals == "") ? p : vals ", " p
  }
  if (vals == "") { warn("empty value: " $0); next }

  if (m == "suffix" || m == "full" || m == "keyword" || m == "regex") {
    out = "domain(" m ": " vals ")"
  } else if (m == "geosite") {
    out = "domain(geosite: " vals ")"
  } else if (m == "ip") {
    out = "dip(" vals ")"
  } else if (m == "geoip") {
    out = "dip(geoip: " vals ")"
  } else {
    warn("unknown matcher '" m "'"); next
  }
  print out " -> " rhs
}
