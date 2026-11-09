#version 450
#extension GL_GOOGLE_include_directive : require
// SMAA pass 2, blending weight calculation (the reference's): the edges (bilinear), the area texture (bilinear) and the search texture (point)
#include "smaa/common.glsl"
#define SMAA_INCLUDE_VS 0
#include "smaa/SMAA.hlsl"
layout(set = 0, binding = 0) uniform sampler2D edgesTex;
layout(set = 0, binding = 1) uniform sampler2D areaTex;
layout(set = 0, binding = 2) uniform sampler2D searchTex;
layout(location = 0) in vec2 texcoord;
layout(location = 1) in vec2 pixcoord;
layout(location = 2) in vec4 offset[3];
layout(location = 0) out vec4 outWeights;
void main() { outWeights = SMAABlendingWeightCalculationPS(texcoord, pixcoord, offset, edgesTex, areaTex, searchTex, vec4(0.0)); }
