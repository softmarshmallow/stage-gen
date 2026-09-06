extends WorldEnvironment

## The frame's environment, which is almost nothing: the viewer's renderer has
## no tone mapping, no lights, no shadow maps and no scene background — the
## page's body colour shows where the water does not, and every material shades
## itself arithmetically in `night.gdshaderinc`.
##
## So this module exists to say no: linear tone mapping (three's
## `NoToneMapping`), no glow, no SSAO, no fog, no ambient, and the clear colour
## the page's CSS carries. It also turns on the 4x MSAA the viewer gets from
## `WebGLRenderer({ antialias: true })`.

## Black, because that is what the viewer's canvas clears to. The page's CSS
## body colour is `#0c0d10` and it does show around the canvas, but the canvas
## itself is opaque and cleared by three to 0x000000: measured on the reference
## `gallery` frame, whose 90.6% of uncovered background is exactly (0, 0, 0)
## with alpha 255, not (12, 13, 16). The gallery is the only shot where any of
## it is visible; every other shot is filled by the ground plane.
const CLEAR_COLOUR := Color(0.0, 0.0, 0.0)

func setup(_pkg, _world, _fu) -> void:
	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = CLEAR_COLOUR
	env.ambient_light_source = Environment.AMBIENT_SOURCE_DISABLED
	env.tonemap_mode = Environment.TONE_MAPPER_LINEAR
	env.glow_enabled = false
	env.ssao_enabled = false
	env.ssil_enabled = false
	env.sdfgi_enabled = false
	env.fog_enabled = false
	env.volumetric_fog_enabled = false
	env.adjustment_enabled = false
	environment = env
	var viewport := get_viewport()
	if viewport != null:
		viewport.msaa_3d = Viewport.MSAA_4X

func update(_world, _delta: float, _cam: Dictionary) -> void:
	pass
