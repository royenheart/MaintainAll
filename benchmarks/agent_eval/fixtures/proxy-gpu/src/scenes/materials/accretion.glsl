// One landing schedule drives both transported cubes and deposited emission.
// This is authored material transport, not a gravitational fluid solver.
float accretionLanding(float radius, float angle, float mode) {
  float disk = 1.0 - smoothstep(-0.10, 0.10, sin(angle));
  float depth = clamp(log(max(radius, 3.0) / 3.0) / log(9.0), 0.0, 1.0);
  float arc = acos(clamp(cos(angle), -1.0, 1.0)) / 3.141593;
  if (mode > 2.5) return mix(0.34 + arc * 0.13, 0.54 + depth * 0.30, disk);
  if (mode > 1.5) return 0.43 + arc * 0.23 + disk * depth * 0.12;
  return 0.43 + arc * 0.14 + depth * 0.16 + 0.035 * sin(angle * 5.0);
}

float accretionDeposit(float radius, float angle, float mode, float progress) {
  float landing = accretionLanding(radius, angle, mode);
  return smoothstep(landing - 0.015, landing + 0.085, progress);
}
