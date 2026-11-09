#version 450
#extension GL_GOOGLE_include_directive : require
// Android port: FSR 1's sharpening, RCAS (AMD FidelityFX FSR 1, MIT: fsr/LICENSE.txt), the upscaled picture (EASU's, the screen's size) onto the screen at the
// viewport's corner (pc.off.xy). pc.con0: FsrRcasCon's constants (fsr_con.c)
layout(push_constant) uniform P { vec4 rect; vec2 rcp; float srgb; float pad; uvec4 con0; uvec4 con1; uvec4 con2; uvec4 con3; ivec4 off; } pc;
layout(set = 0, binding = 0) uniform sampler2D tex;
layout(location = 0) out vec4 color;
#define A_GPU 1
#define A_GLSL 1
#include "fsr/ffx_a.h"
#define FSR_RCAS_F 1
AF4 FsrRcasLoadF(ASU2 p) { return texelFetch(tex, p, 0); }
void FsrRcasInputF(inout AF1 r, inout AF1 g, inout AF1 b) {}
#include "fsr/ffx_fsr1.h"
void main() {
    AU2 ip = AU2(ivec2(gl_FragCoord.xy) - pc.off.xy);
    AF3 c; FsrRcasF(c.r, c.g, c.b, ip, pc.con0);
    color = vec4(c, 1.0);
}
