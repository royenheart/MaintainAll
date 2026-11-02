attribute vec3 instanceOffset;
attribute vec3 instanceScale;
attribute vec3 instancePile;
attribute vec4 instanceMotion;
attribute vec4 instanceRotation;
attribute vec3 instanceTint;
attribute vec3 instanceAccent;
attribute float instanceAlpha;

uniform float uTime;
uniform float uFallTop;
uniform float uFallBottom;
uniform float uVerticalDensityPower;
uniform float uPileHoldStart;
uniform float uPileFadeStart;
uniform highp float uCollapse;
uniform float uPresence;
uniform float uSwirl;
uniform float uHorizonRadius;
uniform vec3 uHorizonCenter;
uniform bool uChoreography;
uniform bool uExpressive;
uniform bool uMirrorRupture;
uniform float uFractureOverride;
uniform float uDirection;
uniform float uInclination;
uniform float uWorldPerScreen;
uniform float uAccretionStyle;
uniform bool uGravityArrival;

/* RIBBON_GEOMETRY */
/* ACCRETION_GEOMETRY */

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

mat3 rotateX(float angle) {
    float c = cos(angle);
    float s = sin(angle);
    return mat3(1.0, 0.0, 0.0, 0.0, c, -s, 0.0, s, c);
}

mat3 rotateY(float angle) {
    float c = cos(angle);
    float s = sin(angle);
    return mat3(c, 0.0, s, 0.0, 1.0, 0.0, -s, 0.0, c);
}

mat3 rotateZ(float angle) {
    float c = cos(angle);
    float s = sin(angle);
    return mat3(c, -s, 0.0, s, c, 0.0, 0.0, 0.0, 1.0);
}

void main() {
    vLocalPosition = position;
    vFlightGlow = 0.0;
    vAccretionHeat = -1.0;
    float cycle = fract(instanceMotion.w + uTime * instanceMotion.x);
    float normalizedFall = clamp(cycle / uPileHoldStart, 0.0, 1.0);
    float densityFallProgress = 1.0 - pow(1.0 - normalizedFall, uVerticalDensityPower);
    float pileProgress = smoothstep(uPileHoldStart - 0.08, uPileHoldStart + 0.12, cycle);
    float fadeProgress = smoothstep(uPileFadeStart, 1.0, cycle);
    float fallY = mix(uFallTop, uFallBottom, densityFallProgress);
    float pileY = uFallBottom + instancePile.y;
    float driftX = sin(uTime * 0.28 + instanceMotion.z) * instanceMotion.y * (1.0 - pileProgress * 0.72);
    float spin = uTime * instanceRotation.w * (1.0 - pileProgress * 0.48);
    mat3 rotationMatrix =
        rotateZ(instanceRotation.z + spin) *
        rotateY(instanceRotation.y + spin * 0.64) *
        rotateX(instanceRotation.x + spin * 0.48);
    vec3 fallingOffset = instanceOffset + vec3(driftX, fallY, 0.0);
    vec3 pileOffset = vec3(instancePile.x, pileY, instancePile.z);
    pileOffset.y += sin(uTime * 0.9 + instanceMotion.z) * 0.08 * pileProgress * (1.0 - fadeProgress);
    vec3 baseWorldOffset = mix(fallingOffset, pileOffset, pileProgress);
    float lowerDensity = 1.0 - smoothstep(-14.0, 16.0, baseWorldOffset.y);
    float verticalDensityScale = mix(0.72, 1.08, lowerDensity);
    vec3 localPosition = rotationMatrix * (position * instanceScale * verticalDensityScale);
    float collapse = smoothstep(0.02, 0.66, uCollapse);
    float angle = instanceMotion.z + collapse * uSwirl * 6.283185 + uTime * 0.08;
    float radius = mix(uHorizonRadius * 1.8, uHorizonRadius, collapse);
    radius += sin(instanceMotion.z * 5.0) * mix(2.0, 0.15, collapse);
    vec3 center = uHorizonCenter;
    vec3 orbit = center + vec3(cos(angle) * radius, sin(angle) * radius, 0.0);
    vec3 gatheredOffset = mix(baseWorldOffset, orbit, pow(collapse, 0.7));
    vec3 worldPosition = mix(center, gatheredOffset, uPresence) + localPosition * mix(1.0, 0.16, collapse) * uPresence;

    float topFade = smoothstep(0.0, 0.08, cycle);
    float bottomFade = 1.0 - fadeProgress;
    float verticalDensityAlpha = mix(0.46, 1.18, lowerDensity);
    vAlpha = instanceAlpha * topFade * bottomFade * verticalDensityAlpha;
    vAlpha *= uPresence * (1.0 - smoothstep(0.72, 0.96, uCollapse));
    vNormal = normalize(normalMatrix * rotationMatrix * normal);
    vTint = instanceTint;
    vAccent = instanceAccent;
    vWorldPosition = worldPosition;
    vDepth = smoothstep(-42.0, -4.0, instanceOffset.z);
    vPileProgress = pileProgress;

    vec4 viewPosition = modelViewMatrix * vec4(worldPosition, 1.0);
    if (uChoreography) {
        float seed = instanceMotion.w;
        float entry = smoothstep(seed * 0.32, 0.60 + seed * 0.40, uPresence);
        if (uCollapse <= 0.00001) {
            if (uGravityArrival) {
                // Release full-sized cubes above the actual camera frustum. Lower
                // destinations settle first, followed by the upper airborne layers.
                vec3 settled = (modelViewMatrix * vec4(baseWorldOffset, 1.0)).xyz;
                vec3 shape = (modelViewMatrix * vec4(localPosition, 0.0)).xyz;
                float halfHeight = -settled.z / projectionMatrix[1][1];
                float heightOrder = clamp((settled.y / halfHeight + 1.0) * 0.5, 0.0, 1.0);
                float landing = 0.40 + heightOrder * 0.43 + seed * 0.055;
                float fall = clamp((uPresence - landing + 0.36) / 0.36, 0.0, 1.0);
                float travel = min(fall / 0.78, 1.0);
                float above = max(halfHeight - settled.y + length(instanceScale) * 2.0, 5.0);
                float lift = above * (1.0 - travel * travel);
                float settle = clamp((fall - 0.78) / 0.22, 0.0, 1.0);
                lift += sin(settle * 3.141593) * (1.0 - settle) * instanceScale.y * 0.5;
                settled.y += lift;
                settled.x += sin(instanceMotion.z) * sin(fall * 3.141593) * 0.45;
                viewPosition = vec4(settled + shape, 1.0);
                vAlpha = instanceAlpha * topFade * bottomFade * verticalDensityAlpha;
                vWorldPosition = baseWorldOffset + localPosition;
                gl_Position = projectionMatrix * viewPosition;
                return;
            }
            vec3 arrivalOffset = vec3(sin(instanceMotion.z) * 3.0, 9.0 + seed * 10.0, -12.0) * (1.0 - entry);
            viewPosition = modelViewMatrix * vec4(baseWorldOffset + localPosition * mix(0.16, 1.0, entry), 1.0);
            viewPosition.xyz += arrivalOffset;
            vAlpha = instanceAlpha * topFade * bottomFade * verticalDensityAlpha * entry;
            vWorldPosition = baseWorldOffset + localPosition;
            gl_Position = projectionMatrix * viewPosition;
            return;
        }
        if (uCollapse >= 0.99999) {
            vAlpha = 0.0;
            gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
            return;
        }
        if (uExpressive && uMirrorRupture && uDirection < 0.0) {
            float release = uFractureOverride >= 0.0 ? uFractureOverride : 1.0 - uCollapse;
            float recovery = smoothstep(0.26 + seed * 0.06, 0.76 + seed * 0.12, release);
            vec3 settled = (modelViewMatrix * vec4(baseWorldOffset, 1.0)).xyz;
            vec3 shape = (modelViewMatrix * vec4(localPosition, 0.0)).xyz;
            settled.xy += normalize(settled.xy + vec2(0.001)) * (1.0 - recovery) * 1.4;
            settled.z -= (1.0 - recovery) * 3.0;
            viewPosition = vec4(settled + shape * mix(0.65, 1.0, recovery), 1.0);
            vAlpha = instanceAlpha * topFade * bottomFade * verticalDensityAlpha * recovery * entry;
            vWorldPosition = baseWorldOffset + localPosition;
            gl_Position = projectionMatrix * viewPosition;
            return;
        }
        if (uExpressive && uDirection > 0.0 && uAccretionStyle > 0.5) {
            // Stable cohorts feed the upper emitting mantle and lower disk. Both
            // land on the exact material contours used by the horizon shader.
            bool halo = seed < 0.44;
            float cohort = halo ? seed / 0.44 : (seed - 0.44) / 0.56;
            float targetAngle = halo ? 0.035 + instanceMotion.z * 0.489
                                     : -0.035 - instanceMotion.z * 0.489;
            float materialRadius = halo ? 3.014 + pow(cohort, 4.0) * 0.65
                : 3.0 + 7.0 * (exp((1.570796 + floor(cohort * 29.0) * 6.283185) / 140.0) - 1.0);
            float landing = accretionLanding(materialRadius, targetAngle, uAccretionStyle);
            float flight = clamp((uCollapse - landing + 0.34) / 0.34, 0.0, 1.0);
            float travel = pow(flight, 2.0);
            float fuse = smoothstep(0.73, 1.0, flight);
            float captureRadius = inversesqrt(4.0 / 27.0 - (1.0 / 900.0) * (1.0 - 1.0 / 30.0));
            vec2 point = ribbonPoint(materialRadius, targetAngle, captureRadius, uTime);
            vec2 ahead = ribbonPoint(materialRadius, targetAngle + 0.004, captureRadius, uTime);
            vec2 tangent = normalize(ahead - point);
            vec3 anchor = (viewMatrix * vec4(center, 1.0)).xyz;
            vec3 source = (modelViewMatrix * vec4(baseWorldOffset, 1.0)).xyz;
            vec3 target = anchor + vec3(point * uWorldPerScreen, 0.0);
            vec3 current;
            if (uAccretionStyle > 1.5 && uAccretionStyle < 2.5) {
                // Curved orbital capture retains a distinct winding stage before
                // transport locks to the destination contour and material phase.
                float winding = sin(flight * 3.141593) * 1.7;
                float pathAngle = targetAngle + (halo ? winding : -winding);
                float pathRadius = materialRadius + sin(flight * 3.141593) * (halo ? 2.0 : 4.0);
                vec2 orbitPoint = ribbonPoint(pathRadius, pathAngle, captureRadius, uTime);
                vec3 orbit = anchor + vec3(orbitPoint * uWorldPerScreen, -sin(flight * 3.141593) * 6.0);
                current = mix(source, orbit, smoothstep(0.0, 0.82, flight));
            } else {
                vec3 control = target - vec3(tangent * uWorldPerScreen * (halo ? 1.25 : 2.4), 0.0);
                control.z = mix(source.z, target.z, 0.65) - 3.0;
                current = mix(mix(source, control, travel), mix(control, target, travel), travel);
            }
            vec3 originalShape = (modelViewMatrix * vec4(localPosition, 0.0)).xyz;
            vec2 flightDirection = normalize(target.xy - source.xy + vec2(0.0001));
            float strain = sin(flight * 3.141593) * smoothstep(0.15, 0.65, flight);
            vec3 stressed = vec3(flightDirection * position.x * instanceScale.x * (1.0 + strain * 1.5)
                + vec2(-flightDirection.y, flightDirection.x) * position.y * instanceScale.y / sqrt(1.0 + strain * 1.5),
                originalShape.z);
            vec3 molten = vec3(tangent * position.x * 0.20 * uWorldPerScreen
                + vec2(-tangent.y, tangent.x) * position.y * 0.015 * uWorldPerScreen,
                position.z * 0.01 * uWorldPerScreen);
            vec3 shape = mix(originalShape, stressed, smoothstep(0.25, 0.65, flight));
            shape = mix(shape, molten, fuse);
            viewPosition = vec4(current + shape, 1.0);
            float baseAlpha = instanceAlpha * topFade * bottomFade * verticalDensityAlpha;
            vAlpha = mix(baseAlpha, 0.94, smoothstep(0.1, 0.55, flight))
                * (1.0 - smoothstep(landing + 0.025, landing + 0.09, uCollapse));
            vAccretionHeat = smoothstep(0.32, 0.93, flight);
            vFlightGlow = smoothstep(0.62, 0.98, flight);
            vWorldPosition = mix(baseWorldOffset + localPosition, center, travel);
            gl_Position = projectionMatrix * viewPosition;
            return;
        }
        float gather = smoothstep(0.035 + seed * 0.065, 0.62 + seed * 0.09, uCollapse);
        float melt = smoothstep(0.32 + seed * 0.08, 0.77 + seed * 0.05, uCollapse);
        float materialRadius = seed < 0.68 ? 3.0 + seed * 0.07 :
            3.0 + 7.0 * (exp((1.570796 + floor((seed - 0.68) / 0.32 * 29.0) * 6.283185) / 140.0) - 1.0);
        float targetAngle = instanceMotion.z;
        if (seed < 0.68) targetAngle = mod(targetAngle, 3.141593);
        else targetAngle = -abs(targetAngle - 3.141593);
        targetAngle += uSwirl * sin(uCollapse * 3.141593) * 0.18;
        vec3 sourceView = (modelViewMatrix * vec4(baseWorldOffset, 1.0)).xyz;
        vec3 anchorView = (viewMatrix * vec4(center, 1.0)).xyz;
        if (uExpressive && uDirection > 0.0) {
            vec2 approach = sourceView.xy - anchorView.xy;
            targetAngle = atan(approach.y, approach.x) + sin(seed * 6.283185) * 0.12;
        }
        float captureRadius = inversesqrt(4.0 / 27.0 - (1.0 / 900.0) * (1.0 - 1.0 / 30.0));
        if (uExpressive && uDirection > 0.0) {
            gather = pow(clamp((uCollapse - 0.04 - seed * 0.055) / 0.55, 0.0, 1.0), 2.9);
            melt = smoothstep(0.51, 0.72, uCollapse);
            materialRadius = mix(3.02, materialRadius, smoothstep(0.63, 0.83, uCollapse));
        }
        vec2 target = ribbonPoint(materialRadius, targetAngle, captureRadius, uTime);
        vec2 ahead = ribbonPoint(materialRadius, targetAngle + 0.002, captureRadius, uTime);
        if (uExpressive && uDirection > 0.0 && length(sourceView.xy - anchorView.xy) < captureRadius * uWorldPerScreen * 0.92) {
            target *= 0.07;
            ahead *= 0.07;
        }
        vec2 tangent = normalize(ahead - target);
        vec3 targetView = (viewMatrix * vec4(center, 1.0)).xyz;
        targetView.xy += target * uWorldPerScreen;
        vec3 startView = (modelViewMatrix * vec4(baseWorldOffset, 1.0)).xyz;
        startView += vec3(sin(instanceMotion.z) * 3.0, 9.0 + seed * 10.0, -12.0) * (1.0 - entry);
        vec3 gatherView = mix(startView, targetView, gather);
        // A shallow curved approach carries depth until each shard lands on its contour.
        gatherView.xy += vec2(-tangent.y, tangent.x) * sin(gather * 3.141593) * (2.0 + seed * 2.0);
        vec3 originalShape = (modelViewMatrix * vec4(localPosition, 0.0)).xyz * mix(0.16, 1.0, entry);
        float shardLength = mix(0.055, 0.12, seed) * uWorldPerScreen;
        float shardWidth = 0.008 * uWorldPerScreen;
        vec3 moltenShape = vec3(tangent * position.x * shardLength + vec2(-tangent.y, tangent.x) * position.y * shardWidth, position.z * shardWidth);
        viewPosition = vec4(gatherView + mix(originalShape, moltenShape, melt), 1.0);
        float baseAlpha = instanceAlpha * topFade * bottomFade * verticalDensityAlpha;
        vAlpha = mix(baseAlpha, 0.88, smoothstep(0.05, 0.38, uCollapse)) * entry;
        vAlpha *= 1.0 - smoothstep(0.70 + seed * 0.08, 0.88 + seed * 0.10, uCollapse);
        vWorldPosition = mix(baseWorldOffset, center, gather);
        if (uExpressive) {
            vec2 radial = normalize(target + vec2(0.0001));
            vec2 flightDirection = normalize(targetView.xy - startView.xy + vec2(0.0001));
            if (uDirection > 0.0) {
                float strain = pow(gather, 0.65) * (1.0 - smoothstep(0.61, 0.76, uCollapse));
                float stretch = 1.0 + strain * 2.8;
                vFlightGlow = smoothstep(0.06, 0.25, strain);
                float thickness = inversesqrt(stretch);
                vec3 stressedShape = vec3(flightDirection * position.x * instanceScale.x * stretch
                  + vec2(-flightDirection.y, flightDirection.x) * position.y * instanceScale.y * thickness,
                  position.z * instanceScale.z * thickness);
                vec3 shape = mix(originalShape, stressedShape, smoothstep(0.08, 0.42, gather));
                shape = mix(shape, moltenShape, melt);
                // Acceleration into a thin capture shell gives a single decisive inward pull.
                gatherView = mix(startView, targetView, gather);
                gatherView.xy += vec2(-flightDirection.y, flightDirection.x) * sin(gather * 3.141593) * (0.4 + seed * 1.2);
                viewPosition = vec4(gatherView + shape, 1.0);
                vAlpha = mix(baseAlpha, 0.96, smoothstep(0.08, 0.34, uCollapse)) * entry;
                vAlpha *= 1.0 - smoothstep(0.63 + seed * 0.04, 0.76 + seed * 0.07, uCollapse);
            } else {
                float burst = 1.0 - uCollapse;
                float release = 0.18 + seed * 0.13;
                float flight = clamp((burst - release) / (0.83 - release), 0.0, 1.0);
                float travel = (1.0 - exp(-flight * 5.0)) / (1.0 - exp(-5.0));
                float impulse = sin(flight * 3.141593) * exp(-flight * 1.7);
                vec3 core = (viewMatrix * vec4(center, 1.0)).xyz;
                vec2 transported = rupturePosition(target, release);
                vec3 emitter = core + vec3(transported * uWorldPerScreen, 0.0);
                radial = normalize(transported + vec2(0.0001));
                vec3 ejected = mix(emitter, startView, travel);
                ejected.xy += radial * impulse * uWorldPerScreen * (3.2 + seed * 2.2);
                ejected.z += impulse * (seed - 0.5) * 12.0;
                float stretch = 1.0 + impulse * 4.5;
                vFlightGlow = smoothstep(0.0, 0.09, flight) * (1.0 - smoothstep(0.38, 0.75, flight));
                vec3 streak = vec3(radial * position.x * instanceScale.x * stretch
                    + vec2(-radial.y, radial.x) * position.y * instanceScale.y / sqrt(stretch),
                    position.z * instanceScale.z / sqrt(stretch));
                vec3 shard = mix(moltenShape, streak, smoothstep(0.0, 0.18, flight));
                shard = mix(shard, originalShape, smoothstep(0.22, 0.76, flight));
                viewPosition = vec4(ejected + shard, 1.0);
                float birth = smoothstep(release, release + 0.055, burst);
                vAlpha = mix(0.94, baseAlpha, smoothstep(0.56, 0.92, burst)) * birth * entry;
                vWorldPosition = mix(center, baseWorldOffset, travel);
            }
        }
    }
    gl_Position = projectionMatrix * viewPosition;
}
        
