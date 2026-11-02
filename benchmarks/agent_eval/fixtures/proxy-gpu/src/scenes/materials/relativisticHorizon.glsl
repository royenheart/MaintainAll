/**
 * Copyright (c) 2020 Eric Bruneton
 * All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are met:
 *
 * 1. Redistributions of source code must retain the above copyright notice, this
 * list of conditions and the following disclaimer.
 *
 * 2. Redistributions in binary form must reproduce the above copyright notice,
 * this list of conditions and the following disclaimer in the documentation
 * and/or other materials provided with the distribution.
 *
 * 3. Neither the name of the copyright holder nor the names of its contributors
 * may be used to endorse or promote products derived from this software without
 * specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
 * AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
 * IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
 * DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
 * FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
 * DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
 * SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
 * CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
 * OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
 * OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 */

precision highp float;
precision highp sampler2D;
uniform sampler2D uDeflection;
uniform sampler2D uInverseRadius;
uniform float uTime;
uniform float uAspect;
uniform float uViewHeight;
uniform float uPresence;
uniform float uFormation;
uniform float uAccretionStyle;
uniform bool uChoreography;
uniform bool uExpressive;
uniform bool uMirrorRupture;
uniform bool uGlitchSource;
uniform bool uWaveOnly;
uniform bool uSpatialWaves;
uniform sampler2D uRadiationMap;
uniform vec2 uResolution;
uniform float uTransition;
uniform float uDirection;
uniform float uInclination;
uniform float uTurbulence;
uniform float uLimb;
uniform float uFlowView;
uniform float uSeed;
uniform vec2 uCenter;
varying vec2 vUv;
varying float vShardEdge;
varying float vShardSeed;
varying float vShardOpacity;

/* MIRROR_WAVES */

const float pi = 3.141592653589793;
const float rad = 1.0;
const float INNER_DISC_R = 3.0;
const float OUTER_DISC_R = 12.0;

// Explicit filtering also works on devices without OES_texture_float_linear.
vec4 opticalSample(sampler2D source, vec2 uv) {
  ivec2 size = textureSize(source, 0);
  vec2 p = clamp(uv * vec2(size) - 0.5, vec2(0.0), vec2(size - 1));
  ivec2 p0 = ivec2(floor(p));
  ivec2 p1 = min(p0 + 1, size - 1);
  vec2 f = fract(p);
  return mix(mix(texelFetch(source, p0, 0), texelFetch(source, ivec2(p1.x, p0.y), 0), f.x),
             mix(texelFetch(source, ivec2(p0.x, p1.y), 0), texelFetch(source, p1, 0), f.x), f.y);
}

/* OPTICAL_FUNCTIONS */

float hash(vec3 p) {
  p = fract(p * 0.1031 + uSeed * 0.00013);
  p += dot(p, p.yxz + 33.33);
  return fract((p.x + p.y) * p.z);
}
float noise(vec3 p) {
  vec3 i = floor(p), f = fract(p);
  f = f * f * (3.0 - 2.0 * f);
  return mix(mix(mix(hash(i), hash(i + vec3(1,0,0)), f.x),
                 mix(hash(i + vec3(0,1,0)), hash(i + vec3(1,1,0)), f.x), f.y),
             mix(mix(hash(i + vec3(0,0,1)), hash(i + vec3(1,0,1)), f.x),
                 mix(hash(i + vec3(0,1,1)), hash(i + vec3(1,1,1)), f.x), f.y), f.z);
}
float densityField(vec3 p) {
  return noise(p) * 0.56 + noise(p * 2.03 + 7.1) * 0.28 + noise(p * 4.07 + 19.7) * 0.16;
}

vec3 sky(vec3 direction) {
  vec2 uv = vec2(atan(direction.y, direction.x) / (2.0 * pi) + 0.5,
                 acos(clamp(direction.z, -1.0, 1.0)) / pi);
  vec2 grid = uv * vec2(1000.0, 500.0);
  vec2 cell = floor(grid);
  float random = hash(vec3(cell, 9.0));
  vec2 offset = vec2(hash(vec3(cell, 2.0)), hash(vec3(cell, 3.0))) - 0.5;
  float distance = length(fract(grid) - 0.5 - offset * 0.6);
  float width = max(length(fwidth(grid)), 0.07);
  float star = (1.0 - smoothstep(0.02, 0.02 + width, distance)) / max(width * width, 1.0);
  star *= step(0.996, random) * (0.2 + hash(vec3(cell, 4.0)) * 1.8);
  float cloud = densityField(direction * 4.0);
  return vec3(0.0014, 0.0017, 0.0027) + vec3(0.025, 0.012, 0.005) * pow(cloud, 4.0)
         + vec3(1.0, 0.88, 0.7) * star;
}

// Two spatial scales share a warped field: emitting wisps and absorbing dust.
// This is a seeded background material, not a volume integration or sky image.
vec3 nebulaSky(vec2 screen, float time) {
  vec3 p = vec3(screen * vec2(0.48, 0.62), 0.7) + vec3(3.1, 7.6, 1.2);
  vec3 drift = vec3(time * 0.008, -time * 0.005, time * 0.003);
  vec3 warp = vec3(densityField(p * 0.63 + drift),
                   densityField(p * 0.63 + 8.7 - drift), 0.0) - 0.5;
  vec3 field = p + warp * 2.8;
  float cloud = densityField(field) * 0.82 + noise(field * 8.17 + 21.0) * 0.12
              + noise(field * 16.3 + 31.0) * 0.06;
  float wisps = pow(noise(field * 5.8 + 4.1), 2.0);
  float dust = smoothstep(0.45, 0.73, densityField(field * 0.82 + 16.3));
  float density = smoothstep(0.25, 0.78, cloud);
  float warm = smoothstep(0.25, 0.72, noise(p * 0.54 + 11.2));
  vec3 tint = mix(vec3(0.035, 0.067, 0.091), vec3(0.23, 0.083, 0.032), warm);
  vec3 emission = tint * pow(density, 1.5) * (0.38 + wisps * 1.2);
  emission += vec3(0.075, 0.035, 0.058) * pow(density, 3.0) * 0.45;
  emission *= exp(-dust * 3.3);

  vec2 grid = screen * 3.5;
  vec2 cell = floor(grid);
  float random = hash(vec3(cell, 31.0));
  vec2 offset = vec2(hash(vec3(cell, 32.0)), hash(vec3(cell, 33.0))) - 0.5;
  vec2 point = fract(grid) - 0.5 - offset * 0.45;
  float width = max(length(fwidth(grid)) * 0.42, 0.014);
  float core = exp(-dot(point, point) / (width * width));
  float glow = exp(-length(point) / 0.072) * 0.16;
  float rays = exp(-abs(point.x) / width - abs(point.y) / 0.12)
             + exp(-abs(point.y) / width - abs(point.x) / 0.12);
  float pulse = 0.82 + 0.18 * sin(time * (0.4 + random * 0.4) + random * 71.0);
  vec3 starTint = mix(vec3(0.47, 0.76, 0.86), vec3(1.0, 0.77, 0.5), hash(vec3(cell, 35.0)));
  vec3 stars = starTint * (core + glow + rays * 0.22) * step(0.985, random) * pulse;
  vec2 fineGrid = screen * 24.0;
  vec2 fineCell = floor(fineGrid);
  vec2 finePoint = fract(fineGrid) - 0.5;
  float fineWidth = max(length(fwidth(fineGrid)) * 0.38, 0.025);
  float fineStar = exp(-dot(finePoint, finePoint) / (fineWidth * fineWidth));
  fineStar *= step(0.995, hash(vec3(fineCell, 41.0))) * exp(-dust * 1.8);
  stars += mix(vec3(0.5, 0.67, 0.84), vec3(1.0, 0.77, 0.52), warm) * fineStar * 0.48;
  float backdrop = mix(0.12, 1.0, smoothstep(-2.0, 0.4, screen.y));
  return (vec3(0.012, 0.011, 0.016) + emission * 1.6 + stars) * backdrop;
}

// Local smooth bulges thicken only the outer emitting mantle. The shadow and
// inner crest stay anchored; no point sprite or lens flare represents the event.
float coronaSwell(vec2 surface, float time) {
  float angle = atan(surface.y, surface.x);
  float height = 0.0;
  for (int i = 0; i < 3; i++) {
    float index = float(i);
    float center = 0.79 + index * 0.68 + 0.045 * sin(time * 0.095 + index * 1.7);
    float width = 0.085 + index * 0.015;
    float pulse = pow(0.5 + 0.5 * sin(time * (0.25 + index * 0.045) + index * 2.4), 3.0);
    float shoulder = exp(-pow((angle - center) / width, 2.0));
    height += (0.10 - index * 0.015) * pulse * shoulder;
  }
  return height * smoothstep(0.25, 0.8, surface.y);
}

/* RIBBON_GEOMETRY */
/* ACCRETION_GEOMETRY */

vec4 ribbonEmission(vec2 screen, float captureRadius, float time) {
  vec2 unbrokenScreen = screen;
  float rupture = uExpressive && !uMirrorRupture && !uGlitchSource && uDirection < 0.0 ? 1.0 - uTransition : 0.0;
  if (rupture > 0.0) screen = ruptureSource(screen, rupture);
  vec2 surface = waveSurface(screen, time);
  float swell = coronaSwell(surface, time);
  float heat = clamp(swell / 0.16, 0.0, 1.0);
  vec3 coordinates = ribbonCoordinates(surface, captureRadius);
  float radius = coordinates.z;
  float foreground = 1.0 - smoothstep(-1.1, 0.05, surface.y);
  float angle = atan(coordinates.y, coordinates.x) - time * 0.12;
  vec3 texturePosition = vec3(cos(angle) * 3.0, sin(angle) * 3.0, radius * 0.7);
  float texture = densityField(texturePosition);
  float phase = ribbonPhase(radius + (texture - 0.5) * 0.07);
  if (uFlowView > 0.5 && uFlowView < 1.5) {
    // Broad numbered groups carry the same warped coordinate as the fine strands.
    float group = phase / (2.0 * pi * 4.0);
    vec3 identifier = 0.45 + 0.4 * cos(floor(group) * 2.39996 + vec3(0.0, 2.0944, 4.1888));
    float grid = smoothstep(0.02, 0.06, fract(group)) * (1.0 - smoothstep(0.94, 0.98, fract(group)));
    return vec4(identifier * mix(0.3, 1.0, grid) * step(3.0, radius) * step(radius, 60.0), 1.0);
  }
  float aa = max(fwidth(phase), 0.001);
  float carrier = 0.5 + 0.5 * sin(phase) * exp(-aa * aa * 0.15);
  float strands = pow(carrier, mix(1.4, 5.0, foreground) * (0.8 + texture * 0.4));
  float fine = 0.5 + 0.5 * sin(phase * 3.13 + texture * 2.0) * exp(-aa * aa * 1.5);
  float edge = smoothstep(3.0, 3.08, radius);
  float outer = 1.0 - smoothstep(42.0, 60.0, radius);
  float profile = pow(3.0 / max(radius, 3.0), 1.2);
  float diffuse = (0.13 + texture * 0.28 + fine * 0.045) * profile * mix(0.75, 0.22, foreground);
  float line = strands * mix(0.18, 1.45, foreground) * profile * (0.7 + texture * 0.65);
  float azimuth = atan(coordinates.y, coordinates.x);
  float copper = 0.5 + 0.5 * sin(azimuth * 2.0 + radius * 0.055 + 0.8);
  float cool = pow(0.5 + 0.5 * cos(azimuth - 2.35 + radius * 0.035), 8.0);
  vec3 diffuseTint = mix(vec3(1.0, 0.59, 0.27), vec3(1.0, 0.36, 0.27), copper * 0.48);
  diffuseTint = mix(diffuseTint, vec3(0.27, 0.6, 0.7), cool * 0.33);
  // Shared radial strata color neighboring strands differently, while broad
  // azimuthal reflections stay periodic and follow the same moving material.
  float strata = smoothstep(0.25, 0.75, noise(vec3(radius * 0.58, 2.1, 4.6)));
  float pearl = pow(1.0 - strata, 3.0) * 0.38;
  float reflection = pow(0.5 + 0.5 * sin(azimuth * 2.0 + radius * 0.12 + 0.5), 6.0);
  vec3 strandTint = mix(vec3(1.0, 0.73, 0.38), vec3(1.0, 0.31, 0.16), strata * 0.78);
  strandTint = mix(strandTint, vec3(1.0, 0.91, 0.73), pearl);
  strandTint = mix(strandTint, vec3(0.38, 0.65, 0.71), reflection * 0.3 + cool * 0.18);
  vec3 color = (diffuseTint * diffuse + strandTint * line) * edge * outer;
  // Measure the inner contour itself; a local radial derivative would saturate
  // far from the logarithmically compressed arc and create a hard halo cutoff.
  float opening = ribbonOpening(surface.y);
  float innerContour = length(surface / ribbonAxes(3.0, opening, captureRadius)) - 1.0;
  vec2 gradient = vec2(dFdx(innerContour) / max(abs(dFdx(screen.x)), 0.00001),
                       dFdy(innerContour) / max(abs(dFdy(screen.y)), 0.00001));
  float distance = innerContour / max(length(gradient), 0.001);
  float pixel = max(fwidth(distance), 0.004);
  float upper = smoothstep(-0.65, -0.25, screen.y);
  float crest = exp(-pow(distance / max(0.018, pixel), 2.0));
  float shoulder = exp(-abs(distance) / 0.057);
  float halo = smoothstep(-pixel, pixel, distance) * (exp(-max(distance, 0.0) / 0.21) * 0.21 + exp(-max(distance, 0.0) / 0.5) * 0.05);
  float outward = max(distance, 0.0);
  float flowAngle = azimuth + outward * 0.22 - time * 0.028;
  vec3 plumeCoordinates = vec3(cos(flowAngle) * 7.0, sin(flowAngle) * 7.0,
                               outward * 5.0 - time * 0.065);
  float plume = densityField(plumeCoordinates);
  float fibers = pow(1.0 - abs(noise(plumeCoordinates * 2.7) * 2.0 - 1.0), 4.0);
  float shimmer = 0.86 + 0.14 * sin(time * 0.58 + azimuth * 9.0 + plume * 5.0);
  vec3 haloTint = mix(vec3(1.0, 0.44, 0.105), vec3(0.9, 0.21, 0.3), copper * 0.48);
  haloTint = mix(haloTint, vec3(0.22, 0.61, 0.74), cool * 0.5);
  float mantle = halo * (0.45 + plume * 1.25 + fibers * 0.65) * shimmer * (1.0 + heat * 1.4) * 1.2;
  float coloredEdge = exp(-pow((distance - 0.036) / max(0.018, pixel), 2.0));
  color += (vec3(1.0, 0.92, 0.79) * crest * 3.8
         + haloTint * (shoulder * 0.38 + mantle)
         + mix(vec3(1.0, 0.45, 0.35), vec3(0.45, 0.74, 0.91), cool)
           * coloredEdge * (0.14 + plume * 0.22)) * upper;
  // Integrate the raised outer lip with a filled, softly emitting bridge back to
  // the unchanged inner edge. Only outward distance participates in this field.
  float outside = smoothstep(0.0, max(pixel, 0.006), distance);
  float raisedLip = exp(-pow((distance - swell) / max(0.025, pixel), 2.0));
  float bridge = 1.0 - smoothstep(swell * 0.62, swell + 0.045, distance);
  float outerGlow = exp(-max(distance - swell, 0.0) / 0.1);
  vec3 hotTint = mix(vec3(1.0, 0.76, 0.4), vec3(0.66, 0.85, 0.9), cool * 0.35);
  color += (hotTint * (raisedLip * 1.25 + bridge * (0.7 + plume * 0.35))
         + haloTint * outerGlow * 0.28) * outside * heat * upper;
  float coverage = edge * outer * mix(0.5, 0.9, foreground) * pow(profile, 0.35);
  // The artistic silhouette occludes its backdrop. A circular geodesic mask
  // would otherwise expose a second, unrelated shadow across the foreground.
  coverage = max(coverage, 1.0 - smoothstep(2.98, 3.0, radius));
  if (uChoreography) {
    bool depositing = uExpressive && uDirection > 0.0 && uAccretionStyle > 0.5;
    float formation = depositing
      ? accretionDeposit(radius, azimuth, uAccretionStyle, uTransition)
      : ribbonFormation(surface, radius, captureRadius, uFormation);
    if (depositing) coverage *= smoothstep(0.22, 0.58, uTransition);
    color *= formation;
  }
  if (rupture > 0.0) {
    float pressure = smoothstep(0.0, 0.10, rupture) * (1.0 - smoothstep(0.12, 0.23, rupture));
    float survival = ruptureSurvival(coordinates, rupture);
    color *= (1.0 + pressure * 0.65) * survival;
    // The void opens while its emitting boundary and disk move outward. Do not
    // leave a stationary intact scene under the ejecta or grow a larger black mask.
    vec2 originalSurface = waveSurface(unbrokenScreen, time);
    float originalRadius = ribbonCoordinates(originalSurface, captureRadius).z;
    float voidCoverage = (1.0 - smoothstep(2.98, 3.0, originalRadius))
      * (1.0 - smoothstep(0.12, 0.35, rupture));
    float emittingCoverage = edge * outer * mix(0.5, 0.9, foreground) * pow(profile, 0.35);
    coverage = max(emittingCoverage * survival, voidCoverage);
  }
  return vec4(color, coverage);
}

vec4 disc(vec2 position, float time, float shift) {
  float radius = length(position);
  float edge = smoothstep(3.0, 3.22, radius) * (1.0 - smoothstep(9.5, 12.0, radius));
  float azimuth = atan(position.y, position.x);
  float orbit = azimuth - time * 0.48 * pow(3.0 / max(radius, 3.0), 1.5);
  vec3 coordinates = vec3(cos(orbit) * 2.7, sin(orbit) * 2.7, radius * 1.8);
  float structures = densityField(coordinates);
  float warpedRadius = radius * 26.0 + structures * 8.0 + sin(orbit * 3.0 + radius) * 1.4;
  float frequency = max(fwidth(warpedRadius), 0.001);
  float filaments = 0.5 + 0.5 * sin(warpedRadius) * exp(-frequency * frequency * 0.2);
  float density = mix(0.65 + structures * 0.5,
                      0.25 + pow(structures, 1.8) * 2.8 + filaments * 0.38, uTurbulence);
  float profile = pow(max(0.0, (1.0 - sqrt(3.0 / max(radius, 3.0))) / pow(radius, 3.0)), 0.25) / 0.21415;
  // Temperature-informed gold art direction, with restrained frequency-shift contrast.
  float temperature = profile * pow(clamp(shift, 0.35, 2.0), 0.35);
  vec3 amber = vec3(1.0, 0.22, 0.028), gold = vec3(1.0, 0.65, 0.28);
  vec3 color = mix(amber, gold, smoothstep(0.35, 0.86, temperature));
  color = mix(color, vec3(1.0, 0.94, 0.78), smoothstep(0.83, 1.16, temperature));
  float emission = 1.8 * pow(profile, 3.0) * density * pow(clamp(shift, 0.35, 2.0), 2.0);
  return vec4(color * emission * edge, edge * 0.96);
}

// Static observer specialization of Bruneton's SceneColor (BSD-3-Clause).
// The basis and received/source frequency ratio follow model.glsl at the pinned revision.
vec3 sceneColor(vec2 screen) {
  float cameraRadius = 30.0;
  vec3 radial = vec3(0.0, -cos(uInclination), sin(uInclination));
  vec3 right = vec3(1.0, 0.0, 0.0);
  vec3 up = cross(right, -radial);
  vec3 direction = normalize(-radial * cameraRadius + right * screen.x + up * screen.y);
  vec3 normal = normalize(cross(radial, direction) + vec3(1e-10));
  vec3 tangent = normalize(cross(normal, radial));
  vec3 crossing = normalize(cross(vec3(0,0,1), normal) + vec3(1e-10));
  if (dot(crossing, tangent) < 0.0) crossing = -crossing;
  float alpha = acos(clamp(dot(radial, crossing), -1.0, 1.0));
  float delta = acos(clamp(dot(radial, direction), -0.9999999, 0.9999999));
  float u = 1.0 / cameraRadius, velocity = -u / tan(delta);
  if (uLimb > 0.5) {
    // Near the view axis, acos(dot) loses precision and bends the disk into a cusp.
    // The camera-plane radius gives cot(delta) directly, without cancellation.
    float impact = max(length(screen), 0.00001);
    alpha = atan(length(cross(radial, crossing)), dot(radial, crossing));
    delta = pi - atan(impact / cameraRadius);
    velocity = 1.0 / impact;
  }
  float energySquared = velocity * velocity + u * u * (1.0 - u);
  float energy = -sqrt(energySquared);
  float u0, phi0, t0, a0, u1, phi1, t1, a1;
  float deflection = TraceRay(uDeflection, uInverseRadius, u, velocity, energySquared,
    delta, alpha, 1.0 / INNER_DISC_R, 1.0 / mix(OUTER_DISC_R, 48.0, uLimb), u0, phi0, t0, a0, u1, phi1, t1, a1);
  float escapeAngle = delta + max(deflection, 0.0);
  vec3 escapeDirection = cos(escapeAngle) * radial + sin(escapeAngle) * tangent;
  vec3 color = deflection >= 0.0 ? sky(escapeDirection) * mix(1.0, 0.45, uLimb) : vec3(0.0);
  float captureRadius = inversesqrt(4.0 / 27.0 - u * u * (1.0 - u));
  if (uLimb > 0.5) {
    vec4 ribbon = ribbonEmission(screen, captureRadius, uTime);
    float skyArrival = uChoreography ? smoothstep(0.28, 1.0, uFormation) : 1.0;
    return (color + nebulaSky(screen, uTime)) * (1.0 - ribbon.a) * skyArrival + ribbon.rgb;
  }
  float receiver = energy / sqrt(1.0 - u);
  if (u1 > 0.0 && a1 > 0.0 && uLimb < 0.5) {
    float source = energy * sqrt(2.0 / (2.0 - 3.0 * u1)) - u1 * sqrt(u1 / (2.0 - 3.0 * u1)) * normal.z;
    vec3 intersection = (radial * cos(phi1) + tangent * sin(phi1)) / u1;
    vec4 emission = disc(intersection.xy, uTime - t1 * 0.015, receiver / source);
    color = color * (1.0 - emission.a * a1) + emission.rgb * a1;
  }
  if (u0 > 0.0 && a0 > 0.0) {
    float source = energy * sqrt(2.0 / (2.0 - 3.0 * u0)) - u0 * sqrt(u0 / (2.0 - 3.0 * u0)) * normal.z;
    vec3 intersection = (radial * cos(phi0) + tangent * sin(phi0)) / u0;
    vec4 emission = disc(intersection.xy, uTime - t0 * 0.015, receiver / source);
    color = color * (1.0 - emission.a * a0) + emission.rgb * a0;
  }
  return color;
}

void main() {
  if (uPresence < 0.001 || uWaveOnly) { gl_FragColor = vec4(0.0); return; }
  float scale = uChoreography ? 1.0 : mix(0.22, 1.0, uPresence);
  vec2 screen = (vUv - uCenter) * vec2(uAspect, 1.0) * uViewHeight / scale;
  if (uMirrorRupture && uExpressive && uDirection < 0.0) {
    float q = 1.0 - uTransition;
    vec2 displayPoint = (gl_FragCoord.xy / uResolution - uCenter) * vec2(uAspect, 1.0) * uViewHeight;
    // Re-evaluate the actual horizon, disk and nebula behind each tilted fragment.
    if (uSpatialWaves) {
      screen += texture2D(uRadiationMap, gl_FragCoord.xy / uResolution).xy * vec2(uAspect, 1.0) * uViewHeight;
    } else {
      vec3 wave = mirrorWaveField(displayPoint, q, uViewHeight * uAspect * 0.5, uViewHeight * 0.5);
      screen.x += wave.x;
    }
    screen += vec2(vShardSeed - 0.5, sin(vShardSeed * 21.0) * 0.35) * smoothstep(0.05, 0.26, q) * 0.42;
    vec3 color = sceneColor(screen);
    float edge = 1.0 - smoothstep(0.0, max(fwidth(vShardEdge) * 1.25, 0.003), vShardEdge);
    float glint = smoothstep(0.08, 0.25, q) * (1.0 - smoothstep(0.50, 0.80, q));
    color += vec3(0.55, 0.34, 0.15) * edge * glint * (0.45 + vShardSeed * 0.55);
    gl_FragColor = vec4(color, uPresence * vShardOpacity);
  } else gl_FragColor = vec4(sceneColor(screen), uPresence);
}
