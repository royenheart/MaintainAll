uniform float uWorldScale;
uniform float uStreaming;
uniform float uTime;
attribute vec3 aTangent;
attribute float aSide;
attribute float aAlong;
attribute float aLife;
varying float vSide;
varying float vAlong;
varying float vLife;
varying vec2 vNormal;
varying float vNear;
void main() {
  vec4 point = modelViewMatrix * vec4(position, 1.0);
  vec2 tangent = normalize((modelViewMatrix * vec4(aTangent, 0.0)).xy + vec2(0.00001));
  vec2 normal = vec2(-tangent.y, tangent.x);
  #if DISTORTION == 1
    float width = mix(0.50, 1.25, uStreaming);
  #else
    float density = 0.72 + 0.16 * sin(aAlong * 33.0 + uTime * 0.2)
      + 0.12 * sin(aAlong * 71.0 - uTime * 0.13);
    float width = mix(0.12, 0.25 * density, uStreaming);
  #endif
  point.xy += normal * aSide * width * uWorldScale;
  vNormal = normal;
  vSide = aSide;
  vAlong = aAlong;
  vLife = aLife;
  vNear = clamp(60.0 / max(-point.z, 5.0), 0.5, 3.0);
  gl_Position = projectionMatrix * point;
}
