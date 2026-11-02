precision highp float;
uniform float uAspect;
uniform float uStreaming;
uniform float uTime;
varying float vSide;
varying float vAlong;
varying float vLife;
varying vec2 vNormal;
varying float vNear;
void main() {
  float taper = smoothstep(0.0, mix(0.10, 0.035, uStreaming), vAlong)
    * (1.0 - smoothstep(mix(0.86, 0.965, uStreaming), 1.0, vAlong));
  float alpha = vLife * taper;
  if (alpha < 0.001) discard;
  #if DISTORTION == 1
    float lens = vSide * exp(-vSide * vSide * 4.0);
    vec2 displacement = vNormal / vec2(uAspect, 1.0) * lens * mix(0.007, 0.014, uStreaming) * vNear;
    gl_FragColor = vec4(displacement, 0.0, alpha);
  #else
    float core = exp(-vSide * vSide * 75.0);
    float halo = exp(-abs(vSide) * 4.8) * 0.22;
    vec3 light = vec3(1.8, 1.41, 0.87) * core + vec3(0.7, 0.32, 0.11) * halo;
    if (uStreaming > 0.5) {
      float density = 0.66 + 0.19 * sin(vAlong * 38.0 - uTime * 0.17)
        + 0.15 * sin(vAlong * 91.0 + uTime * 0.11);
      float fold = vSide - sin(vAlong * 48.0 + uTime * 0.12) * 0.11;
      float fiber = exp(-fold * fold * 95.0);
      float body = exp(-vSide * vSide * 9.0);
      float shoulder = exp(-abs(vSide) * 3.8);
      light = vec3(1.0, 0.78, 0.46) * fiber * density
        + vec3(0.33, 0.20, 0.10) * body * density
        + vec3(0.18, 0.09, 0.045) * shoulder;
    }
    gl_FragColor = vec4(light, alpha);
  #endif
}
