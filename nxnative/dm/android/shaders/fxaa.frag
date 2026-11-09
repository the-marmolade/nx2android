#version 450
// Android port: FXAA on the game's finished picture (gfx_vk_present.c fxaa_draw), the luma-edge version (after Timothy Lottes' FXAA): the four diagonal
// neighbours give the edge's direction, and two or four samples along it blend the edge; a span that leaves the local luma range keeps the two-sample
// result. r.rcp: one source texel in [0,1]. Luma is taken from gamma-encoded colour: an sRGB picture is sampled linear (r.srgb), and its square root
// stands in for the encoding
layout(push_constant) uniform P { vec4 rect; vec2 rcp; float srgb; float pad; } r;
layout(location = 0) in vec2 uv;
layout(location = 0) out vec4 color;
layout(set = 0, binding = 0) uniform sampler2D tex;
const float REDUCE_MIN = 1.0 / 128.0, REDUCE_MUL = 1.0 / 8.0, SPAN_MAX = 8.0;
float luma(vec3 c) { if (r.srgb > 0.5) c = sqrt(max(c, vec3(0.0))); return dot(c, vec3(0.299, 0.587, 0.114)); }
void main() {
    vec3 m = texture(tex, uv).rgb;
    float lNW = luma(texture(tex, uv + vec2(-1.0, -1.0) * r.rcp).rgb), lNE = luma(texture(tex, uv + vec2(1.0, -1.0) * r.rcp).rgb);
    float lSW = luma(texture(tex, uv + vec2(-1.0, 1.0) * r.rcp).rgb), lSE = luma(texture(tex, uv + vec2(1.0, 1.0) * r.rcp).rgb), lM = luma(m);
    float lMin = min(lM, min(min(lNW, lNE), min(lSW, lSE))), lMax = max(lM, max(max(lNW, lNE), max(lSW, lSE)));
    vec2 dir = vec2(-((lNW + lNE) - (lSW + lSE)), (lNW + lSW) - (lNE + lSE));
    float reduce = max((lNW + lNE + lSW + lSE) * 0.25 * REDUCE_MUL, REDUCE_MIN);
    float rcpMin = 1.0 / (min(abs(dir.x), abs(dir.y)) + reduce);
    dir = clamp(dir * rcpMin, vec2(-SPAN_MAX), vec2(SPAN_MAX)) * r.rcp;
    vec3 a = 0.5 * (texture(tex, uv + dir * (1.0 / 3.0 - 0.5)).rgb + texture(tex, uv + dir * (2.0 / 3.0 - 0.5)).rgb);
    vec3 b = a * 0.5 + 0.25 * (texture(tex, uv - dir * 0.5).rgb + texture(tex, uv + dir * 0.5).rgb);
    float lB = luma(b);
    color = vec4(lB < lMin || lB > lMax ? a : b, 1.0);
}
