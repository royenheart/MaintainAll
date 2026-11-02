precision mediump float;

uniform float uTime;
uniform float uAspect;
uniform float uPresence;
uniform bool uLinearOutput;
varying vec2 vUv;

float softCircle(vec2 uv, vec2 center, float radius) {
    vec2 delta = uv - center;
    delta.x *= uAspect;
    return 1.0 - smoothstep(radius * 0.18, radius, length(delta));
}

void main() {
    vec3 topColor = vec3(0.0, 0.98, 1.0);
    vec3 midColor = vec3(0.0, 0.75, 0.995);
    vec3 bottomColor = vec3(0.03, 0.56, 0.9);
    vec3 color = mix(topColor, midColor, smoothstep(0.08, 0.52, vUv.y));
    color = mix(color, bottomColor, smoothstep(0.56, 1.0, vUv.y));

    vec2 warmCenter = vec2(0.58 + sin(uTime * 0.06) * 0.035, 0.52 + cos(uTime * 0.05) * 0.025);
    vec2 coolCenter = vec2(0.16, 0.88);
    float warmMist = softCircle(vUv, warmCenter, 0.62);
    float coolMist = softCircle(vUv, coolCenter, 0.5);
    color += vec3(1.0, 0.16, 0.5) * warmMist * 0.18;
    color += vec3(0.72, 1.0, 1.0) * coolMist * 0.16;
    color = mix(color, vec3(0.0, 0.15, 0.36), smoothstep(0.72, 1.0, vUv.y) * 0.16);

    if (uLinearOutput) color = sRGBTransferEOTF(vec4(color, 1.0)).rgb;
    gl_FragColor = vec4(color, uPresence);
}
        
