#version 450
#extension GL_GOOGLE_include_directive : require
// SMAA pass 3, neighborhood blending, straight onto the screen: one triangle over the viewport (the picture's rectangle there), the texture coordinate over
// the source rectangle (pc.rect, smaa/common.glsl)
#include "smaa/common.glsl"
#define SMAA_INCLUDE_PS 0
#include "smaa/SMAA.hlsl"
layout(location = 0) out vec2 texcoord;
layout(location = 1) out vec4 offset;
void main() {
    vec2 p = vec2((gl_VertexIndex << 1) & 2, gl_VertexIndex & 2);
    gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0);
    texcoord = pc.rect.xy + p * pc.rect.zw;
    SMAANeighborhoodBlendingVS(texcoord, offset);
}
