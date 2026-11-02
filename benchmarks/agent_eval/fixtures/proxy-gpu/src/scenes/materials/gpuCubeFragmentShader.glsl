precision mediump float;

varying vec3 vNormal;
varying vec3 vLocalPosition;
varying float vFlightGlow;
varying float vAccretionHeat;
varying vec3 vTint;
varying vec3 vAccent;
varying vec3 vWorldPosition;
varying float vAlpha;
varying float vDepth;
varying float vPileProgress;

uniform float uLightContrast;
uniform highp float uCollapse;
uniform bool uLinearOutput;
uniform bool uChoreography;

void main() {
    vec3 normalDirection = normalize(vNormal);
    vec3 keyDirection = normalize(vec3(-0.62, 0.76, 0.32));
    vec3 rimDirection = normalize(vec3(0.86, -0.18, 0.28));
    vec3 shadowDirection = normalize(vec3(0.3, -0.42, -0.86));

    float key = max(dot(normalDirection, keyDirection), 0.0);
    float topLight = smoothstep(0.18, 0.88, normalDirection.y);
    float shadow = smoothstep(0.18, 0.92, max(-normalDirection.z, dot(normalDirection, shadowDirection)));
    float sideWarmth = smoothstep(0.24, 0.9, normalDirection.x);
    float rim = pow(max(dot(normalDirection, rimDirection), 0.0), 1.35);
    float leftTopLight = smoothstep(-12.0, 24.0, -vWorldPosition.x) * smoothstep(-16.0, 13.0, vWorldPosition.y);
    float bottomOcclusion = (1.0 - smoothstep(-16.5, -6.5, vWorldPosition.y)) * (0.38 + vPileProgress * 0.62);
    float contactShade = vPileProgress * (1.0 - topLight) * 0.34;

    vec3 deepBlue = vec3(0.0, 0.018, 0.105);
    vec3 color = mix(deepBlue, vTint, 0.24 + key * 0.72 * uLightContrast);
    color = mix(color, vTint * vec3(1.34, 1.48, 1.5), topLight * 0.82);
    color = mix(color, deepBlue, shadow * 0.62 * uLightContrast);
    color = mix(color, vAccent, max(rim * 0.98, sideWarmth * 0.38));
    color += vTint * leftTopLight * (0.08 + topLight * 0.16);
    color = mix(color, color * vec3(0.58, 0.68, 0.86), contactShade);
    color = mix(color, deepBlue, bottomOcclusion * 0.2);
    color += vec3(0.0, 0.11, 0.18) * (1.0 - vDepth);

    vec3 originalColor = color;
    color = mix(color, vec3(1.0, 0.64, 0.12) * (0.5 + key), smoothstep(0.35, 0.85, uCollapse));
    if (uChoreography) color = mix(color, vec3(1.35, 0.83, 0.39), smoothstep(0.30, 0.75, uCollapse));
    if (vAccretionHeat >= 0.0) color = mix(originalColor, vec3(1.35, 0.83, 0.39), vAccretionHeat);
    float opacity = vAlpha;
    if (vFlightGlow > 0.001) {
        float crossSection = exp(-vLocalPosition.y * vLocalPosition.y * 18.0);
        float tail = smoothstep(-0.5, -0.12, vLocalPosition.x) * (1.0 - smoothstep(0.28, 0.5, vLocalPosition.x));
        opacity *= mix(1.0, crossSection * tail, vFlightGlow);
        vec3 heat = mix(vec3(0.42, 0.86, 1.35), vec3(2.6, 1.48, 0.57), vAccretionHeat >= 0.0 ? vAccretionHeat : smoothstep(0.32, 0.64, uCollapse));
        heat = mix(heat, vec3(2.8, 2.32, 1.63), smoothstep(0.0, 0.4, vLocalPosition.x) * 0.35);
        color = mix(color, heat, vFlightGlow);
    }
    if (opacity < mix(0.035, 0.008, vFlightGlow)) discard;
    // Preserve authored display colors when rendering into a linear composer buffer.
    if (uLinearOutput) color = sRGBTransferEOTF(vec4(color, 1.0)).rgb;
    gl_FragColor = vec4(color, opacity);
}
        
