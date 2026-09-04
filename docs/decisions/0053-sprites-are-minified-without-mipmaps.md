# 0053 — Sprites are minified without mipmaps, and higher source resolution makes it worse

*Ruled after device-pixel rendering landed.*

## Fact

Every game now draws at device pixel resolution, which removed the visible pixelation on the
runner's player, but the underlying sampling is unchanged: an actor sheet's figure is 500-700
source pixels tall and drawn at 154 design pixels, so even at a 2x device ratio the GPU takes
one bilinear tap per output pixel across a 2x2 texel footprint or wider. The engine leaves its
mipmap filter empty by default and only generates mipmaps for power-of-two textures, which the
atlases and alpha-trimmed cells are not.

## Challenge

The intuitive fix for a soft or jagged sprite is to generate the source art larger.

## Ruling

Higher source resolution makes it worse, not better: it widens the texel footprint each output
pixel must average, and one bilinear tap cannot average it. No change is taken now, because the
device-pixel path removed the visible symptom. If jagged sprites return — on a 1x screen, a
taller design-space character, or a heavier minification — the fix is a filtered pre-shrink of
the trimmed cells at load time toward display height times device ratio, or power-of-two padding
plus an explicit mipmap filter.

## Evidence

The symptom and the sampling are independent: the symptom went away when the output resolution
rose, while the ratio of source to drawn pixels did not move at all.

## Falsifier

Visible aliasing at the shipped sizes on a device-pixel display, which would make the deferral
wrong rather than merely cheap.
