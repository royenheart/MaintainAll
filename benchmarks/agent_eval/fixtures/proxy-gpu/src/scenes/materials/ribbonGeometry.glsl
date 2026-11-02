// Inverse height displacement moves the whole emitting surface up and down.
// Unequal directions, wavelengths and speeds produce travelling swells.
// The amplitude bound keeps the vertical map monotone at every inclination.
vec2 waveSurface(vec2 screen, float time) {
  float vertical = clamp(sin(uInclination) * 1.06, 0.1, 0.65);
  vec2 p = vec2(screen.x, screen.y / vertical);
  float height = 0.15 * sin(dot(p, vec2(0.73, 0.31)) - time * 0.62)
               + 0.09 * sin(dot(p, vec2(-1.13, 0.57)) + time * 0.83 + 1.9)
               + 0.055 * sin(dot(p, vec2(0.34, 0.17)) - time * 0.48 + 3.4);
  float nearField = 1.0 - smoothstep(-2.8, -0.72, screen.y);
  height *= nearField * min(1.0, vertical / 0.22);
  return screen - vec2(0.0, height);
}

// Integrate a decreasing radial frequency instead of spacing contours equally.
// The local interval grows continuously with radius, from the distant inner disk
// toward the near foreground, without independent per-ring offsets or seams.
float ribbonPhase(float radius) {
  return 140.0 * log(1.0 + max(radius - 3.0, -0.5) / 7.0);
}

// Art-directed nested ribbons preserve the selected framing; these are not
// additional geodesic images. Both axes increase with material radius, so every
// screen point has at most one radius and the material map cannot fold radially.
float ribbonOpening(float y) {
  return 1.0 / (1.0 + exp(clamp((y + 0.1) / 0.28, -30.0, 30.0)));
}
vec2 ribbonAxes(float radius, float opening, float captureRadius) {
  float upper = captureRadius + 0.33 * log(radius / 3.0);
  return mix(vec2(upper), radius * vec2(captureRadius / 3.0, clamp(sin(uInclination) * 1.06, 0.1, 0.65)), opening);
}

vec3 ribbonCoordinates(vec2 screen, float captureRadius) {
  float opening = ribbonOpening(screen.y);
  float low = 0.7, high = 64.0;
  for (int i = 0; i < 16; i++) {
    float radius = (low + high) * 0.5;
    vec2 axes = ribbonAxes(radius, opening, captureRadius);
    if (length(screen / axes) > 1.0) low = radius;
    else high = radius;
  }
  float radius = (low + high) * 0.5;
  vec2 direction = normalize(screen / ribbonAxes(radius, opening, captureRadius) + vec2(1e-7));
  return vec3(direction * radius, radius);
}

// Forward parameterization uses the same nested contour as the pixel shader.
// Solve the vertical opening before restoring the travelling surface displacement.
vec2 ribbonPoint(float radius, float angle, float captureRadius, float time) {
  float extent = max(captureRadius + 0.33 * log(radius / 3.0), radius * 0.65);
  float low = -extent, high = extent;
  for (int i = 0; i < 16; i++) {
    float y = (low + high) * 0.5;
    float ordinate = y / ribbonAxes(radius, ribbonOpening(y), captureRadius).y;
    if (ordinate < sin(angle)) low = y;
    else high = y;
  }
  float y = (low + high) * 0.5;
  vec2 point = vec2(cos(angle) * ribbonAxes(radius, ribbonOpening(y), captureRadius).x, y);
  vec2 displaced = point;
  for (int i = 0; i < 5; i++) displaced = point + displaced - waveSurface(displaced, time);
  return displaced;
}

// The edge traces upward from both shoulders; outer strata follow toward the viewer.
// Reversing the master progress retraces the same material, without new random targets.
float ribbonFormation(vec2 surface, float radius, float captureRadius, float progress) {
  float crown = clamp((surface.y + 0.5) / (captureRadius + 0.5), 0.0, 1.0);
  float depth = clamp(log(max(radius, 3.0) / 3.0) / log(9.0), 0.0, 1.0);
  float front = mix(crown * 0.30, 0.24 + depth * 0.57, ribbonOpening(surface.y));
  return smoothstep(front, front + 0.18, progress);
}

// A reversible material-space transport map moves the emitting surface itself.
// Angle-dependent expansion and twist are shared by the source and its ejecta.
float ruptureExpansion(float angle, float progress) {
  float pressure = smoothstep(0.0, 0.10, progress) * (1.0 - smoothstep(0.10, 0.18, progress));
  float release = smoothstep(0.12, 0.62, progress);
  return 1.0 - pressure * 0.035 + release * (2.7 + 0.40 * sin(angle * 3.0 + 0.7));
}
float ruptureTwist(float angle, float progress) {
  return smoothstep(0.12, 0.65, progress) * (0.11 * sin(angle * 3.0) + 0.06 * sin(angle * 7.0 + 1.3));
}
vec2 rupturePosition(vec2 source, float progress) {
  float angle = atan(source.y, source.x);
  float outputAngle = angle + ruptureTwist(angle, progress);
  return vec2(cos(outputAngle), sin(outputAngle)) * length(source) * ruptureExpansion(angle, progress);
}
vec2 ruptureSource(vec2 screen, float progress) {
  float outputAngle = atan(screen.y, screen.x);
  float angle = outputAngle;
  for (int i = 0; i < 6; i++) angle = outputAngle - ruptureTwist(angle, progress);
  return vec2(cos(angle), sin(angle)) * length(screen) / ruptureExpansion(angle, progress);
}
float ruptureSurvival(vec3 coordinates, float progress) {
  float angle = atan(coordinates.y, coordinates.x);
  float group = ribbonPhase(coordinates.z) / (6.283185 * 5.0);
  float cell = (angle + 3.141593) / 6.283185 * 13.0 + sin(group * 1.7) * 0.22;
  float angularEdge = min(fract(cell), 1.0 - fract(cell));
  float radialCell = fract(group + sin(floor(cell) * 2.39) * 0.18);
  float radialEdge = min(radialCell, 1.0 - radialCell);
  float opening = smoothstep(0.12, 0.40, progress);
  float gaps = smoothstep(opening * 0.12, opening * 0.12 + 0.014, angularEdge);
  gaps *= smoothstep(opening * 0.09, opening * 0.09 + 0.014, radialEdge);
  float seed = fract(sin(floor(cell) * 127.1 + floor(group) * 311.7) * 43758.5453);
  float remains = 1.0 - smoothstep(0.24 + seed * 0.10, 0.44 + seed * 0.14, progress);
  return mix(1.0, gaps * remains, smoothstep(0.10, 0.17, progress));
}
