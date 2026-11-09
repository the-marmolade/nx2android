#version 450
#extension GL_GOOGLE_include_directive : require
// SMAA pass 1, edge detection: SMAALumaEdgeDetectionPS with the luma of gamma-encoded colour (an sRGB picture is sampled linear: its square root stands in for
// the encoding, as the reference's thresholds expect gamma space), and 0 written where there is no edge rather than a discard (no clear, no stencil)
#include "smaa/common.glsl"
#define SMAA_INCLUDE_VS 0
#include "smaa/SMAA.hlsl"
layout(set = 0, binding = 0) uniform sampler2D colorTex;
layout(location = 0) in vec2 texcoord;
layout(location = 1) in vec4 offset[3];
layout(location = 0) out vec4 outEdges;
float L(vec2 uv) { vec3 c = textureLod(colorTex, uv, 0.0).rgb; if (pc.srgb > 0.5) c = sqrt(max(c, vec3(0.0))); return dot(c, vec3(0.2126, 0.7152, 0.0722)); }
void main() {
    vec2 threshold = vec2(SMAA_THRESHOLD);
    float l = L(texcoord), lLeft = L(offset[0].xy), lTop = L(offset[0].zw);
    vec4 delta; delta.xy = abs(l - vec2(lLeft, lTop));
    vec2 edges = step(threshold, delta.xy);
    if (dot(edges, vec2(1.0)) == 0.0) { outEdges = vec4(0.0); return; }
    float lRight = L(offset[1].xy), lBottom = L(offset[1].zw);
    delta.zw = abs(l - vec2(lRight, lBottom));
    vec2 maxDelta = max(delta.xy, delta.zw);
    float lLeftLeft = L(offset[2].xy), lTopTop = L(offset[2].zw);
    delta.zw = abs(vec2(lLeft, lTop) - vec2(lLeftLeft, lTopTop));
    maxDelta = max(maxDelta.xy, delta.zw);
    float finalDelta = max(maxDelta.x, maxDelta.y);
    edges.xy *= step(finalDelta, SMAA_LOCAL_CONTRAST_ADAPTATION_FACTOR * delta.xy);
    outEdges = vec4(edges, 0.0, 0.0);
}
