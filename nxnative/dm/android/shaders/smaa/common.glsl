// Android port: SMAA 1x on the game's finished picture (gfx_vk_present.c smaa_draw), from the reference SMAA.hlsl (iryoku/smaa, MIT: smaa/LICENSE.txt) in its
// GLSL 4 mode. Shared by the three passes (smaa_edge, smaa_weight, smaa_blend): pc.rt is the picture's metrics (1/w, 1/h, w, h); pc.rect the source rectangle
// the last pass reads ([0,1], the height negative when the picture is stored bottom-up); pc.srgb 1 when the picture is sampled linear (an sRGB format)
layout(push_constant) uniform P { vec4 rt; vec4 rect; float srgb; float pad0; float pad1; float pad2; } pc;
#define SMAA_RT_METRICS pc.rt
#define SMAA_GLSL_4 1
#define SMAA_PRESET_HIGH 1
