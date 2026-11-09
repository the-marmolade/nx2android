#version 450
#extension GL_GOOGLE_include_directive : require
// SMAA pass 3, neighborhood blending (the reference's): the picture (bilinear) blended by the weights of pass 2
#include "smaa/common.glsl"
#define SMAA_INCLUDE_VS 0
#include "smaa/SMAA.hlsl"
layout(set = 0, binding = 0) uniform sampler2D colorTex;
layout(set = 0, binding = 1) uniform sampler2D blendTex;
layout(location = 0) in vec2 texcoord;
layout(location = 1) in vec4 offset;
layout(location = 0) out vec4 color;
void main() { color = vec4(SMAANeighborhoodBlendingPS(texcoord, offset, colorTex, blendTex).rgb, 1.0); }
