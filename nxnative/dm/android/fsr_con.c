// Android port: FSR 1's constants (AMD FidelityFX FSR 1, MIT: shaders/fsr/LICENSE.txt), from its own CPU functions (ffx_a.h's A_CPU mode), for the present's
// upscaling passes (gfx_vk_present.c up_draw; shaders/fsr_easu.frag, fsr_rcas.frag). In a file of its own: ffx_a.h's short macro names (AF1, AU1, ...) stay here
#include <stdint.h>
#include <string.h>
#include <math.h>
#include <stdlib.h>   // (ffx_a.h calls abs and labs)
#define A_CPU 1
#include "shaders/fsr/ffx_a.h"
#define FSR_EASU_F 1
#define FSR_RCAS_F 1
#include "shaders/fsr/ffx_fsr1.h"

// EASU: the source rectangle (vw x vh at ox, oy) of a picture iw x ih into an output ow x oh; con: 16 words (con0..con3)
void dm_fsr_easu_con(uint32_t con[16], float vw, float vh, float iw, float ih, float ow, float oh, float ox, float oy) {
    FsrEasuConOffset(con, con + 4, con + 8, con + 12, vw, vh, iw, ih, ow, oh, ox, oy);
}
// RCAS: sharpness in stops (0 the sharpest, each 1.0 halves it); con: 4 words
void dm_fsr_rcas_con(uint32_t con[4], float sharpness) { FsrRcasCon(con, sharpness); }
