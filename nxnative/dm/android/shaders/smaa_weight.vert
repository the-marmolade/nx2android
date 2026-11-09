#version 450
#extension GL_GOOGLE_include_directive : require
// SMAA pass 2, blending weight calculation: one triangle over the whole picture (smaa/common.glsl)
#include "smaa/common.glsl"
#define SMAA_INCLUDE_PS 0
#include "smaa/SMAA.hlsl"
layout(location = 0) out vec2 texcoord;
layout(location = 1) out vec2 pixcoord;
layout(location = 2) out vec4 offset[3];
void main() {
    vec2 p = vec2((gl_VertexIndex << 1) & 2, gl_VertexIndex & 2);
    gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0);
    texcoord = p;
    SMAABlendingWeightCalculationVS(texcoord, pixcoord, offset);
}
