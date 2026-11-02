precision highp float;
uniform float uProgress;
uniform float uDirection;
uniform bool uMirror;
uniform float uTime;
uniform float uAspect;
uniform float uViewHeight;
uniform vec2 uCenter;
varying vec2 vUv;

/* MIRROR_WAVES */

void main() {
  vec2 p = (vUv - uCenter) * vec2(uAspect, 1.0) * uViewHeight;
  if (uMirror && uDirection < 0.0) {
    vec3 wave = mirrorWaveField(p, 1.0 - uProgress, uViewHeight * uAspect * 0.5, uViewHeight * 0.5);
    vec3 pearl = vec3(1.6, 1.27, 0.82);
    gl_FragColor = vec4(pearl * wave.y + vec3(0.8, 0.39, 0.14) * wave.z, 1.0);
    return;
  }
  float radius = length(p);
  float angle = atan(p.y, p.x);
  float light = 0.0;
  vec3 color = vec3(0.55, 0.76, 1.0);
  if (uDirection > 0.0) {
    float fall = pow(clamp((uProgress - 0.12) / 0.54, 0.0, 1.0), 2.2);
    float front = mix(13.0, 2.60, fall);
    float compression = exp(-abs(radius - front) / 0.13);
    float sectors = 0.5 + 0.5 * pow(sin(angle * 5.0 + radius * 0.12), 2.0);
    float envelope = smoothstep(0.14, 0.36, uProgress) * (1.0 - smoothstep(0.64, 0.78, uProgress));
    float impact = exp(-pow((uProgress - 0.655) / 0.042, 2.0));
    light = compression * sectors * envelope * 0.34;
    light += exp(-abs(radius - 2.60) / 0.16) * impact * 0.52;
    color = mix(vec3(0.25, 0.64, 1.0), vec3(1.5, 0.95, 0.46), smoothstep(0.4, 0.66, uProgress));
  } else {
    float burst = 1.0 - uProgress;
    float age = clamp((burst - 0.17) / 0.48, 0.0, 1.0);
    float expansion = (1.0 - exp(-age * 3.0)) / (1.0 - exp(-3.0));
    float uneven = 0.18 * sin(angle * 5.0 + 0.7) + 0.11 * sin(angle * 11.0 - 1.1);
    float front = 2.55 + expansion * 10.0 + uneven * expansion;
    float envelope = smoothstep(0.17, 0.215, burst) * (1.0 - smoothstep(0.42, 0.73, burst));
    float edge = exp(-pow((radius - front) / (0.09 + age * 0.10), 2.0));
    float shoulder = exp(-abs(radius - front) / (0.22 + age * 0.15));
    float breakout = exp(-pow((burst - 0.22) / 0.035, 2.0));
    float filaments = pow(0.5 + 0.5 * sin(angle * 63.0 + sin(angle * 13.0) * 4.0), 7.0);
    float stream = smoothstep(2.2, 3.4, radius) * (1.0 - smoothstep(front - 0.5, front + 0.2, radius));
    float lobes = pow(0.5 + 0.5 * sin(angle * 7.0 + sin(angle * 3.0) * 2.1), 3.0);
    float taper = exp(-max(radius - 2.6, 0.0) / (1.2 + lobes * 2.0));
    light = (edge * 0.72 + shoulder * 0.36 + filaments * stream * lobes * taper * 0.14) * envelope;
    light += exp(-radius * radius / 3.8) * breakout * 1.25;
    color = mix(vec3(1.6, 1.16, 0.64), vec3(0.45, 0.78, 1.0), smoothstep(0.25, 0.65, burst));
  }
  gl_FragColor = vec4(color * light, 1.0);
}
