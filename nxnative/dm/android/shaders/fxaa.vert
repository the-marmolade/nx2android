#version 450
// Android port: the game's picture put on the screen through FXAA (gfx_vk_present.c fxaa_draw). One triangle covers the viewport, which is the picture's
// rectangle on the screen; the texture coordinate runs over the source rectangle (r.rect: its corner and size in [0,1], the size negative when the
// picture is stored bottom-up)
layout(push_constant) uniform P { vec4 rect; vec2 rcp; float srgb; float pad; } r;
layout(location = 0) out vec2 uv;
void main() {
    vec2 p = vec2((gl_VertexIndex << 1) & 2, gl_VertexIndex & 2);   // (0,0) (2,0) (0,2): the viewport is the corner [0,1]^2
    gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0);
    uv = r.rect.xy + p * r.rect.zw;
}
