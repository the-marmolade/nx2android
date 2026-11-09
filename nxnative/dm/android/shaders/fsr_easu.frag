#version 450
#extension GL_GOOGLE_include_directive : require
// Android port: FSR 1's upscaler, EASU (AMD FidelityFX FSR 1, MIT: fsr/LICENSE.txt), the picture into the screen's size (gfx_vk_present.c up_draw). The output
// pixel is the fragment's position less the viewport's corner (pc.off.xy); a picture stored bottom-up is read upside down (pc.off.w, pc.off.z the output height).
// pc.con0..3: FsrEasuConOffset's constants (fsr_con.c), with the source rectangle as its viewport and offset
layout(push_constant) uniform P { vec4 rect; vec2 rcp; float srgb; float pad; uvec4 con0; uvec4 con1; uvec4 con2; uvec4 con3; ivec4 off; } pc;
layout(set = 0, binding = 0) uniform sampler2D tex;
layout(location = 0) out vec4 color;
#define A_GPU 1
#define A_GLSL 1
#include "fsr/ffx_a.h"
#define FSR_EASU_F 1
AF4 FsrEasuRF(AF2 p) { return textureGather(tex, p, 0); }
AF4 FsrEasuGF(AF2 p) { return textureGather(tex, p, 1); }
AF4 FsrEasuBF(AF2 p) { return textureGather(tex, p, 2); }
#include "fsr/ffx_fsr1.h"
void main() {
    AU2 ip = AU2(ivec2(gl_FragCoord.xy) - pc.off.xy);
    if (pc.off.w != 0) ip.y = uint(pc.off.z) - 1u - ip.y;
    AF3 c; FsrEasuF(c, ip, pc.con0, pc.con1, pc.con2, pc.con3);
    color = vec4(c, 1.0);
}
