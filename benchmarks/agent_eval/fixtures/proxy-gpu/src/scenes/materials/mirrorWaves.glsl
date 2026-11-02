// Shared screen-space wavefronts: upright curves travel sideways in delayed pairs.
// Their displacement and visible emission come from the same signed distances.
float mirrorNoise(float x) {
  float i = floor(x), f = fract(x);
  f = f * f * (3.0 - 2.0 * f);
  float a = fract(sin(i * 127.1 + 4.7) * 43758.5453);
  float b = fract(sin((i + 1.0) * 127.1 + 4.7) * 43758.5453);
  return mix(a, b, f) * 2.0 - 1.0;
}
vec3 mirrorWaveField(vec2 screen, float progress, float halfWidth, float halfHeight) {
  float offset = 0.0, light = 0.0, glow = 0.0;
  for (int pair = 0; pair < 4; pair++) {
    float index = float(pair);
    float age = (progress - 0.12 - index * 0.083) / 0.56;
    float life = smoothstep(0.0, 0.065, age) * (1.0 - smoothstep(0.78, 1.05, age));
    float front = 0.12 + max(age, 0.0) * (halfWidth + 1.8);
    float large = mirrorNoise(screen.y * 0.58 + index * 7.7 - progress * 0.6);
    float detail = mirrorNoise(screen.y * 3.7 + index * 11.3 + progress * 0.35);
    float curve = large * 0.20 + detail * 0.028;
    for (int side = 0; side < 2; side++) {
      float signX = side == 0 ? -1.0 : 1.0;
      float axis = signX * front + curve + signX * index * 0.025;
      float distance = screen.x - axis;
      float taper = 1.0 - smoothstep(halfHeight * 0.58, halfHeight * 1.1, abs(screen.y + sin(index * 2.4) * halfHeight * 0.18));
      float broken = 0.68 + 0.32 * mirrorNoise(screen.y * 9.1 + index * 31.0);
      float width = 0.010 + index * 0.0015;
      float aa = max(fwidth(distance), 0.003);
      float core = 1.0 - smoothstep(width, width + aa * 1.4, abs(distance));
      float tail = exp(-abs(distance + signX * 0.028) / 0.052);
      light += (core * 0.9 + tail * 0.18) * life * taper * broken;
      glow += exp(-abs(distance) / 0.13) * life * taper * 0.12;
      // Bipolar displacement compresses one side of the wave and expands the other.
      offset += distance / 0.14 * exp(-pow(distance / 0.14, 2.0)) * life * taper * 0.32;
    }
  }
  return vec3(offset, light, glow);
}
