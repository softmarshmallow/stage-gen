/**
 * A headless stand-in for Phaser, and for the browser surface the prepared platformer loads through.
 *
 * The platformer's scene is the one runtime in this repository with no seam between gameplay and the
 * engine: `PreparedStageScene` extends `Phaser.Scene`, every actor owns a `GameObject`, and the world
 * is built out of textures. There is no way to drive it for a replay without standing something where
 * Phaser stands. This is that something, and it is deliberately the smallest thing that lets the real
 * gameplay code run: a scene graph that records placement rather than drawing it, a texture manager
 * that owns frame rectangles, a keyboard whose latches behave the way `JustDown` does, and a tween,
 * timer and animation set stepped from the harness's clock rather than from a browser's.
 *
 * What it is NOT is an emulator. Three limits are load-bearing and are stated here rather than
 * discovered later:
 *
 * 1. **No rendering, so no art.** Nothing decodes an image. The harness serves the manifest and
 *    refuses every asset, which sends the scene down its own shipped presentation-fallback path: each
 *    texture becomes the runtime's magenta placeholder at the placeholder's size. Terrain, decks,
 *    ladders, portals, spawns and every gameplay distance come from the manifest and are therefore
 *    real; sprite frame sizes, and the render bounds derived from them, are the fallback's.
 * 2. **One clock.** Phaser steps tweens, timers and animations from the engine's wall clock, and the
 *    scene reads `performance.now()` for simulation time; under a fixed-frame capture those two
 *    diverge, which is exactly the defect the "off engine tweens" work exists to remove. Here they are
 *    the same virtual clock. That makes the harness *kinder* to the engine-driven code than a browser
 *    is: a diff this harness shows when a subsystem moves onto the fixed step is a real semantic
 *    difference, and the nondeterminism the browser would add on top is not visible here at all.
 * 3. **The camera is a re-implementation.** `startFollow` with a dead zone and a lerp is thirty lines
 *    of Phaser arithmetic reproduced below, not Phaser's. It matters because the spawn director asks
 *    what is on screen, so the camera cannot simply be frozen.
 */

/** Everything a `GameObject` in this scene graph is asked to be. */
export class StubFrame {
  constructor(
    readonly name: string | number,
    readonly x: number,
    readonly y: number,
    readonly width: number,
    readonly height: number,
  ) {}
}

export class StubTexture {
  readonly frames = new Map<string, StubFrame>();
  private firstName: string | null = null;

  constructor(
    readonly key: string,
    width: number,
    height: number,
  ) {
    this.add("__BASE", 0, 0, 0, width, height);
    this.firstName = null;
  }

  add(name: string | number, _sourceIndex: number, x: number, y: number, width: number, height: number): StubFrame {
    const frame = new StubFrame(name, x, y, width, height);
    this.frames.set(String(name), frame);
    if (this.firstName === null && String(name) !== "__BASE") this.firstName = String(name);
    return frame;
  }

  has(name: string | number): boolean {
    return this.frames.has(String(name));
  }

  remove(name: string | number): void {
    this.frames.delete(String(name));
    if (this.firstName === String(name)) {
      this.firstName = this.getFrameNames()[0] ?? null;
    }
  }

  /** Phaser answers the first non-base frame for a bare `get()`, and `__BASE` when there is none. */
  get(name?: string | number | null): StubFrame | undefined {
    if (name === undefined || name === null) {
      return this.frames.get(this.firstName ?? "__BASE");
    }
    return this.frames.get(String(name));
  }

  getFrameNames(): string[] {
    return [...this.frames.keys()].filter((name) => name !== "__BASE");
  }

  get frameTotal(): number {
    return this.frames.size;
  }

  getSourceImage(): { width: number; height: number } {
    const base = this.frames.get("__BASE");
    return { width: base?.width ?? 1, height: base?.height ?? 1 };
  }

  /**
   * `CanvasTexture`'s two extra members.
   *
   * The runtime bakes its gauge capsules into a texture once rather than redrawing them per actor
   * per frame, so the drawing surface has to exist. Nothing reads the pixels back.
   */
  getContext(): Record<string, unknown> {
    return STUB_DRAWING_CONTEXT;
  }

  refresh(): this {
    return this;
  }
}

const STUB_DRAWING_CONTEXT: Record<string, unknown> = {
  fillStyle: "",
  strokeStyle: "",
  lineWidth: 0,
  beginPath: () => undefined,
  closePath: () => undefined,
  moveTo: () => undefined,
  lineTo: () => undefined,
  arc: () => undefined,
  arcTo: () => undefined,
  quadraticCurveTo: () => undefined,
  bezierCurveTo: () => undefined,
  rect: () => undefined,
  roundRect: () => undefined,
  clearRect: () => undefined,
  fillRect: () => undefined,
  strokeRect: () => undefined,
  save: () => undefined,
  restore: () => undefined,
  translate: () => undefined,
  scale: () => undefined,
  rotate: () => undefined,
  drawImage: () => undefined,
  fill: () => undefined,
  stroke: () => undefined,
  createLinearGradient: () => ({ addColorStop: () => undefined }),
  createRadialGradient: () => ({ addColorStop: () => undefined }),
};

export type StubCanvas = {
  width: number;
  height: number;
  getContext(kind: string): StubCanvasContext | null;
};

export type StubCanvasContext = Record<string, unknown>;

export class StubTextureManager {
  private readonly textures = new Map<string, StubTexture>();
  private readonly missing = new StubTexture("__MISSING", 1, 1);

  exists(key: string): boolean {
    return this.textures.has(key);
  }

  get(key: string): StubTexture {
    return this.textures.get(key) ?? this.missing;
  }

  remove(key: string): void {
    this.textures.delete(key);
  }

  addCanvas(key: string, canvas: StubCanvas): StubTexture {
    const texture = new StubTexture(key, canvas.width, canvas.height);
    this.textures.set(key, texture);
    return texture;
  }

  createCanvas(key: string, width: number, height: number): StubTexture {
    return this.addCanvas(key, { width, height, getContext: () => null });
  }

  getFrame(key: string, name?: string | number | null): StubFrame | undefined {
    return this.get(key).get(name);
  }

  /** Opaque enough for the widget's safe-rect probe: the fallback art has no measurable alpha. */
  getPixel(): { alpha: number } {
    return { alpha: 255 };
  }
}

// --- the scene graph -------------------------------------------------------

export type StubBounds = Readonly<{
  x: number;
  y: number;
  width: number;
  height: number;
  left: number;
  right: number;
  top: number;
  bottom: number;
  centerX: number;
  centerY: number;
}>;

export class StubGameObject {
  x = 0;
  y = 0;
  alpha = 1;
  angle = 0;
  visible = true;
  active = true;
  depth = 0;
  scaleX = 1;
  scaleY = 1;
  originX = 0.5;
  originY = 0.5;
  flipX = false;
  name = "";
  scrollFactorX = 1;
  scrollFactorY = 1;
  tint: number | null = null;
  tintFill = false;
  width = 0;
  height = 0;
  readonly type: string = "GameObject";
  private readonly data = new Map<string, unknown>();

  constructor(x = 0, y = 0) {
    this.x = x;
    this.y = y;
  }

  get displayWidth(): number {
    return this.width * this.scaleX;
  }

  set displayWidth(value: number) {
    this.scaleX = this.width === 0 ? 1 : value / this.width;
  }

  get displayHeight(): number {
    return this.height * this.scaleY;
  }

  set displayHeight(value: number) {
    this.scaleY = this.height === 0 ? 1 : value / this.height;
  }

  setPosition(x: number, y = x): this {
    this.x = x;
    this.y = y;
    return this;
  }

  setX(x: number): this {
    this.x = x;
    return this;
  }

  setY(y: number): this {
    this.y = y;
    return this;
  }

  setOrigin(x: number, y = x): this {
    this.originX = x;
    this.originY = y;
    return this;
  }

  setAlpha(alpha = 1): this {
    this.alpha = alpha;
    return this;
  }

  setAngle(angle = 0): this {
    this.angle = angle;
    return this;
  }

  setVisible(visible: boolean): this {
    this.visible = visible;
    return this;
  }

  setActive(active: boolean): this {
    this.active = active;
    return this;
  }

  setDepth(depth: number): this {
    this.depth = depth;
    return this;
  }

  setScale(x: number, y = x): this {
    this.scaleX = x;
    this.scaleY = y;
    return this;
  }

  setScrollFactor(x: number, y = x): this {
    this.scrollFactorX = x;
    this.scrollFactorY = y;
    return this;
  }

  setSize(width: number, height: number): this {
    this.width = width;
    this.height = height;
    return this;
  }

  setDisplaySize(width: number, height: number): this {
    this.displayWidth = width;
    this.displayHeight = height;
    return this;
  }

  setName(name: string): this {
    this.name = name;
    return this;
  }

  setFlipX(flip: boolean): this {
    this.flipX = flip;
    return this;
  }

  setTint(tint = 0xffffff): this {
    this.tint = tint;
    return this;
  }

  setTintMode(fill: number): this {
    this.tintFill = fill === 1;
    return this;
  }

  clearTint(): this {
    this.tint = null;
    this.tintFill = false;
    return this;
  }

  setInteractive(): this {
    return this;
  }

  /** Pointer wiring a headless run never delivers: registered, never fired. */
  on(): this {
    return this;
  }

  off(): this {
    return this;
  }

  once(): this {
    return this;
  }

  setCrop(): this {
    return this;
  }

  setFilter(): this {
    return this;
  }

  setData(key: string, value: unknown): this {
    this.data.set(key, value);
    return this;
  }

  getData(key: string): unknown {
    return this.data.get(key);
  }

  getBounds(): StubBounds {
    const width = this.displayWidth;
    const height = this.displayHeight;
    const left = this.x - this.originX * width;
    const top = this.y - this.originY * height;
    return Object.freeze({
      x: left,
      y: top,
      width,
      height,
      left,
      right: left + width,
      top,
      bottom: top + height,
      centerX: left + width / 2,
      centerY: top + height / 2,
    });
  }

  destroy(): void {
    this.active = false;
    this.visible = false;
    this.onDestroy();
  }

  protected onDestroy(): void {
    // Overridden by objects the display list has to forget.
  }
}

/** The animation component of a sprite: a current frame, and a clock that walks it. */
export class StubAnimationState {
  currentAnim: StubAnimation | null = null;
  currentFrame: StubAnimationFrame | null = null;
  isPlaying = false;
  isPaused = false;
  private elapsedMs = 0;

  constructor(private readonly sprite: StubSprite) {}

  play(key: string, ignoreIfPlaying = false): void {
    const anim = this.sprite.sceneAnims.get(key);
    if (!anim) return;
    if (ignoreIfPlaying && this.isPlaying && this.currentAnim?.key === key) return;
    this.currentAnim = anim;
    this.isPlaying = true;
    this.isPaused = false;
    this.elapsedMs = 0;
    this.applyFrame(anim.frames[0] ?? null);
  }

  stop(): void {
    this.isPlaying = false;
    this.isPaused = false;
    this.currentAnim = null;
    this.currentFrame = null;
  }

  pause(): void {
    if (this.isPlaying) this.isPaused = true;
  }

  resume(): void {
    this.isPaused = false;
  }

  setCurrentFrame(frame: StubAnimationFrame | null | undefined): void {
    if (!frame) return;
    this.applyFrame(frame);
  }

  update(deltaMs: number): void {
    const anim = this.currentAnim;
    if (!anim || !this.isPlaying || this.isPaused || anim.msPerFrame <= 0) return;
    this.elapsedMs += deltaMs;
    while (this.elapsedMs >= anim.msPerFrame) {
      this.elapsedMs -= anim.msPerFrame;
      const index = this.currentFrame ? anim.frames.indexOf(this.currentFrame) : -1;
      const next = index + 1;
      if (next >= anim.frames.length) {
        if (anim.repeat < 0) {
          this.applyFrame(anim.frames[0] ?? null);
        } else {
          this.isPlaying = false;
          return;
        }
      } else {
        this.applyFrame(anim.frames[next] ?? null);
      }
    }
  }

  private applyFrame(frame: StubAnimationFrame | null): void {
    this.currentFrame = frame;
    if (frame) this.sprite.setTexture(frame.textureKey, frame.frameName);
  }
}

export type StubAnimationFrame = Readonly<{ textureKey: string; frameName: string | number }>;

export type StubAnimation = Readonly<{
  key: string;
  frames: readonly StubAnimationFrame[];
  msPerFrame: number;
  repeat: number;
}>;

export class StubAnimationManager {
  private readonly anims = new Map<string, StubAnimation>();

  exists(key: string): boolean {
    return this.anims.has(key);
  }

  get(key: string): StubAnimation | undefined {
    return this.anims.get(key);
  }

  create(config: {
    key: string;
    frames: readonly { key: string; frame: string | number }[];
    frameRate: number;
    repeat?: number;
  }): StubAnimation {
    const anim: StubAnimation = Object.freeze({
      key: config.key,
      frames: Object.freeze(
        config.frames.map((frame) =>
          Object.freeze({ textureKey: frame.key, frameName: frame.frame }),
        ),
      ),
      msPerFrame: config.frameRate > 0 ? 1000 / config.frameRate : 0,
      repeat: config.repeat ?? 0,
    });
    this.anims.set(config.key, anim);
    return anim;
  }

  remove(key: string): void {
    this.anims.delete(key);
  }
}

export class StubSprite extends StubGameObject {
  override readonly type = "Sprite";
  readonly anims: StubAnimationState;
  texture: StubTexture;
  frame: StubFrame;

  constructor(
    private readonly textureManager: StubTextureManager,
    readonly sceneAnims: StubAnimationManager,
    x: number,
    y: number,
    key: string,
    frameName?: string | number,
  ) {
    super(x, y);
    this.texture = textureManager.get(key);
    this.frame = this.texture.get(frameName) ?? this.texture.get() ?? new StubFrame("__BASE", 0, 0, 1, 1);
    this.width = this.frame.width;
    this.height = this.frame.height;
    this.anims = new StubAnimationState(this);
  }

  setTexture(key: string, frameName?: string | number): this {
    this.texture = this.textureManager.get(key);
    return this.setFrame(frameName);
  }

  setFrame(frameName?: string | number): this {
    const frame = this.texture.get(frameName) ?? this.texture.get();
    if (frame) {
      this.frame = frame;
      this.width = frame.width;
      this.height = frame.height;
    }
    return this;
  }

  play(key: string, ignoreIfPlaying = false): this {
    this.anims.play(key, ignoreIfPlaying);
    return this;
  }
}

/**
 * An `Image` is a `Sprite` without its own animation state, which nothing here depends on: the two
 * differ only in the label the display list would use, and the scene reads no such label.
 */
export class StubImage extends StubSprite {}

export class StubText extends StubGameObject {
  override readonly type = "Text";
  text: string;
  style: Record<string, unknown>;

  constructor(x: number, y: number, text: string | readonly string[], style: Record<string, unknown>) {
    super(x, y);
    this.text = Array.isArray(text) ? text.join("\n") : String(text);
    this.style = { ...style };
    this.measure();
  }

  setText(text: string | readonly string[]): this {
    this.text = Array.isArray(text) ? text.join("\n") : String(text);
    this.measure();
    return this;
  }

  setStyle(style: Record<string, unknown>): this {
    this.style = { ...this.style, ...style };
    this.measure();
    return this;
  }

  setFill(color: string): this {
    this.style = { ...this.style, color };
    return this;
  }

  /**
   * A deterministic metric in place of a font.
   *
   * Half the declared point size per character, and one line box per newline: no font is loaded, so
   * every alternative is equally invented and this one at least varies with the string, which is what
   * the layouts that read `displayHeight` are actually asking about.
   */
  private measure(): void {
    const size = Number(String(this.style.fontSize ?? "16px").replace(/[^0-9.]/g, "")) || 16;
    const lines = this.text.split("\n");
    this.width = Math.max(...lines.map((line) => line.length)) * size * 0.5;
    this.height = lines.length * size * 1.2;
  }
}

export class StubTileSprite extends StubGameObject {
  override readonly type = "TileSprite";
  tilePositionX = 0;
  tilePositionY = 0;

  constructor(x: number, y: number, width: number, height: number) {
    super(x, y);
    this.width = width;
    this.height = height;
  }

  setTileScale(): this {
    return this;
  }
}

export class StubShape extends StubGameObject {
  override readonly type = "Shape";

  constructor(x: number, y: number, width: number, height: number) {
    super(x, y);
    this.width = width;
    this.height = height;
  }
}

export class StubNineSlice extends StubGameObject {
  override readonly type = "NineSlice";

  constructor(x: number, y: number, width: number, height: number) {
    super(x, y);
    this.width = width;
    this.height = height;
  }
}

/** A drawing surface that records nothing: the platformer only ever paints presentation with it. */
export class StubGraphics extends StubGameObject {
  override readonly type = "Graphics";

  clear(): this {
    return this;
  }
  fillStyle(): this {
    return this;
  }
  lineStyle(): this {
    return this;
  }
  fillRect(): this {
    return this;
  }
  strokeRect(): this {
    return this;
  }
  fillRoundedRect(): this {
    return this;
  }
  strokeRoundedRect(): this {
    return this;
  }
  fillCircle(): this {
    return this;
  }
  strokeCircle(): this {
    return this;
  }
  beginPath(): this {
    return this;
  }
  closePath(): this {
    return this;
  }
  moveTo(): this {
    return this;
  }
  lineTo(): this {
    return this;
  }
  arc(): this {
    return this;
  }
  strokePath(): this {
    return this;
  }
  fillPath(): this {
    return this;
  }
  setBlendMode(): this {
    return this;
  }
  lineBetween(): this {
    return this;
  }
  strokeLineShape(): this {
    return this;
  }
  fillTriangle(): this {
    return this;
  }
  strokeTriangle(): this {
    return this;
  }
  fillEllipse(): this {
    return this;
  }
  strokeEllipse(): this {
    return this;
  }
  slice(): this {
    return this;
  }
  fillPoints(): this {
    return this;
  }
  strokePoints(): this {
    return this;
  }
}

export class StubContainer extends StubGameObject {
  override readonly type = "Container";
  readonly list: StubGameObject[] = [];

  add(child: StubGameObject | StubGameObject[]): this {
    for (const entry of Array.isArray(child) ? child : [child]) this.list.push(entry);
    return this;
  }

  remove(child: StubGameObject, destroyChild = false): this {
    const index = this.list.indexOf(child);
    if (index >= 0) this.list.splice(index, 1);
    if (destroyChild) child.destroy();
    return this;
  }

  removeAll(destroyChild = false): this {
    if (destroyChild) for (const child of this.list) child.destroy();
    this.list.length = 0;
    return this;
  }

  protected override onDestroy(): void {
    for (const child of this.list) child.destroy();
    this.list.length = 0;
  }
}

export class StubDisplayList {
  readonly list: StubGameObject[] = [];

  add(child: StubGameObject): StubGameObject {
    this.list.push(child);
    return child;
  }

  remove(child: StubGameObject): void {
    const index = this.list.indexOf(child);
    if (index >= 0) this.list.splice(index, 1);
  }

  getByName(name: string): StubGameObject | null {
    return this.list.find((child) => child.name === name) ?? null;
  }
}

export class StubGameObjectFactory {
  constructor(
    private readonly displayList: StubDisplayList,
    private readonly textures: StubTextureManager,
    private readonly anims: StubAnimationManager,
  ) {}

  sprite(x: number, y: number, key: string, frame?: string | number): StubSprite {
    return this.track(new StubSprite(this.textures, this.anims, x, y, key, frame));
  }

  image(x: number, y: number, key: string, frame?: string | number): StubImage {
    return this.track(new StubImage(this.textures, this.anims, x, y, key, frame));
  }

  text(x: number, y: number, text: string | readonly string[], style: Record<string, unknown> = {}): StubText {
    return this.track(new StubText(x, y, text, style));
  }

  tileSprite(x: number, y: number, width: number, height: number, _key: string): StubTileSprite {
    return this.track(new StubTileSprite(x, y, width, height));
  }

  rectangle(x: number, y: number, width: number, height: number): StubShape {
    return this.track(new StubShape(x, y, width, height));
  }

  ellipse(x: number, y: number, width: number, height: number): StubShape {
    return this.track(new StubShape(x, y, width, height));
  }

  graphics(): StubGraphics {
    return this.track(new StubGraphics());
  }

  container(x: number, y: number): StubContainer {
    return this.track(new StubContainer(x, y));
  }

  nineslice(
    x: number,
    y: number,
    _key: string,
    _frame: string | number,
    width: number,
    height: number,
  ): StubNineSlice {
    return this.track(new StubNineSlice(x, y, width, height));
  }

  existing<T extends StubGameObject>(child: T): T {
    return this.track(child);
  }

  private track<T extends StubGameObject>(child: T): T {
    this.displayList.add(child);
    return child;
  }
}

// --- camera ---------------------------------------------------------------

type FollowTarget = Readonly<{ x: number; y: number }>;

/**
 * Phaser's dead-zone follow, reproduced.
 *
 * The scene hands the camera a world box, a follow offset and a 300x180 dead zone, and the spawn
 * director then asks which columns are on screen — so a camera that did not move would change what
 * the world does, not only what it looks like. The arithmetic below is Phaser's `preRender`: place the
 * dead zone on the camera's midpoint, push the scroll by however far the target is outside it, lerp
 * toward that, then clamp to the bounds.
 */
export class StubCamera {
  scrollX = 0;
  scrollY = 0;
  zoom = 1;
  originX = 0.5;
  originY = 0.5;
  width: number;
  height: number;
  backgroundColor = "";
  private follow: FollowTarget | null = null;
  private lerpX = 1;
  private lerpY = 1;
  private followOffsetX = 0;
  private followOffsetY = 0;
  private deadzoneWidth = 0;
  private deadzoneHeight = 0;
  private bounds: { x: number; y: number; width: number; height: number } | null = null;

  constructor(width: number, height: number) {
    this.width = width;
    this.height = height;
  }

  get left(): number {
    return this.scrollX;
  }
  get right(): number {
    return this.scrollX + this.width / this.zoom;
  }
  get top(): number {
    return this.scrollY;
  }
  get bottom(): number {
    return this.scrollY + this.height / this.zoom;
  }

  setBackgroundColor(color: string): this {
    this.backgroundColor = color;
    return this;
  }

  setOrigin(x: number, y = x): this {
    this.originX = x;
    this.originY = y;
    return this;
  }

  setZoom(x: number, _y = x): this {
    this.zoom = x;
    return this;
  }

  setScroll(x: number, y: number): this {
    this.scrollX = x;
    this.scrollY = y;
    return this;
  }

  setBounds(x: number, y: number, width: number, height: number): this {
    this.bounds = { x, y, width, height };
    return this;
  }

  setDeadzone(width: number, height: number): this {
    this.deadzoneWidth = width;
    this.deadzoneHeight = height;
    return this;
  }

  startFollow(
    target: FollowTarget,
    _roundPixels = false,
    lerpX = 1,
    lerpY = lerpX,
    offsetX = 0,
    offsetY = 0,
  ): this {
    this.follow = target;
    this.lerpX = lerpX;
    this.lerpY = lerpY;
    this.followOffsetX = offsetX;
    this.followOffsetY = offsetY;
    return this;
  }

  stopFollow(): this {
    this.follow = null;
    return this;
  }

  /** A screen shake the harness does not model; the scene applies its own scroll nudge instead. */
  shake(): this {
    return this;
  }

  preRender(): void {
    const target = this.follow;
    if (!target) return;
    const viewWidth = this.width / this.zoom;
    const viewHeight = this.height / this.zoom;
    const followX = target.x - this.followOffsetX;
    const followY = target.y - this.followOffsetY;
    if (this.deadzoneWidth > 0 || this.deadzoneHeight > 0) {
      const midX = this.scrollX + viewWidth / 2;
      const midY = this.scrollY + viewHeight / 2;
      const zoneLeft = midX - this.deadzoneWidth / 2;
      const zoneRight = midX + this.deadzoneWidth / 2;
      const zoneTop = midY - this.deadzoneHeight / 2;
      const zoneBottom = midY + this.deadzoneHeight / 2;
      if (followX < zoneLeft) {
        this.scrollX = linear(this.scrollX, this.scrollX - (zoneLeft - followX), this.lerpX);
      } else if (followX > zoneRight) {
        this.scrollX = linear(this.scrollX, this.scrollX + (followX - zoneRight), this.lerpX);
      }
      if (followY < zoneTop) {
        this.scrollY = linear(this.scrollY, this.scrollY - (zoneTop - followY), this.lerpY);
      } else if (followY > zoneBottom) {
        this.scrollY = linear(this.scrollY, this.scrollY + (followY - zoneBottom), this.lerpY);
      }
    } else {
      this.scrollX = linear(this.scrollX, followX - viewWidth / 2, this.lerpX);
      this.scrollY = linear(this.scrollY, followY - viewHeight / 2, this.lerpY);
    }
    const bounds = this.bounds;
    if (!bounds) return;
    this.scrollX = clamp(this.scrollX, bounds.x, Math.max(bounds.x, bounds.x + bounds.width - viewWidth));
    this.scrollY = clamp(this.scrollY, bounds.y, Math.max(bounds.y, bounds.y + bounds.height - viewHeight));
  }
}

export class StubCameraManager {
  readonly main: StubCamera;

  constructor(width: number, height: number) {
    this.main = new StubCamera(width, height);
  }

  forEach(callback: (camera: StubCamera) => void): void {
    callback(this.main);
  }
}

// --- input ----------------------------------------------------------------

export class StubKey {
  isDown = false;
  private justDownLatch = false;

  constructor(readonly keyCode: number) {}

  /** Press for one frame's worth of latch, the way a browser keydown arms `JustDown`. */
  press(): void {
    if (!this.isDown) this.justDownLatch = true;
    this.isDown = true;
  }

  release(): void {
    this.isDown = false;
  }

  consumeJustDown(): boolean {
    if (!this.justDownLatch) return false;
    this.justDownLatch = false;
    return true;
  }
}

export class StubKeyboardPlugin {
  private readonly keys = new Map<number, StubKey>();
  private readonly listeners = new Map<string, Set<() => void>>();

  addKey(keyCode: number): StubKey {
    const existing = this.keys.get(keyCode);
    if (existing) return existing;
    const key = new StubKey(keyCode);
    this.keys.set(keyCode, key);
    return key;
  }

  createCursorKeys(): Record<string, StubKey> {
    return {
      up: this.addKey(KEY_CODES.UP),
      down: this.addKey(KEY_CODES.DOWN),
      left: this.addKey(KEY_CODES.LEFT),
      right: this.addKey(KEY_CODES.RIGHT),
      space: this.addKey(KEY_CODES.SPACE),
      shift: this.addKey(KEY_CODES.SHIFT),
    };
  }

  on(event: string, handler: () => void): this {
    const set = this.listeners.get(event) ?? new Set<() => void>();
    set.add(handler);
    this.listeners.set(event, set);
    return this;
  }

  off(event: string, handler: () => void): this {
    this.listeners.get(event)?.delete(handler);
    return this;
  }
}

export class StubInputPlugin {
  readonly keyboard = new StubKeyboardPlugin();
  private readonly listeners = new Map<string, Set<() => void>>();

  on(event: string, handler: () => void): this {
    const set = this.listeners.get(event) ?? new Set<() => void>();
    set.add(handler);
    this.listeners.set(event, set);
    return this;
  }

  off(event: string, handler: () => void): this {
    this.listeners.get(event)?.delete(handler);
    return this;
  }
}

// --- tweens and timers ----------------------------------------------------

type TweenConfig = Record<string, unknown> & {
  targets: StubGameObject | StubGameObject[];
  duration?: number;
  delay?: number;
  hold?: number;
  yoyo?: boolean;
  ease?: string;
  onComplete?: () => void;
};

const TWEEN_RESERVED = new Set([
  "targets",
  "duration",
  "delay",
  "hold",
  "yoyo",
  "ease",
  "onComplete",
  "onUpdate",
  "onStart",
  "repeat",
  "repeatDelay",
  "paused",
]);

type ActiveTween = {
  readonly targets: StubGameObject[];
  readonly props: readonly { key: string; from: number[]; to: number }[];
  readonly durationMs: number;
  readonly holdMs: number;
  readonly yoyo: boolean;
  readonly ease: (t: number) => number;
  readonly onComplete?: () => void;
  elapsedMs: number;
};

export class StubTweenManager {
  private tweens: ActiveTween[] = [];

  add(config: TweenConfig): ActiveTween {
    const targets = Array.isArray(config.targets) ? [...config.targets] : [config.targets];
    const props: { key: string; from: number[]; to: number }[] = [];
    for (const [key, value] of Object.entries(config)) {
      if (TWEEN_RESERVED.has(key) || typeof value !== "number") continue;
      props.push({
        key,
        from: targets.map((target) => Number((target as unknown as Record<string, number>)[key] ?? 0)),
        to: value,
      });
    }
    const tween: ActiveTween = {
      targets,
      props,
      durationMs: Number(config.duration ?? 1000),
      holdMs: Number(config.hold ?? 0),
      yoyo: config.yoyo === true,
      ease: config.ease === "Cubic.easeOut" ? (t) => 1 - (1 - t) ** 3 : (t) => t,
      onComplete: config.onComplete,
      elapsedMs: 0,
    };
    this.tweens.push(tween);
    this.apply(tween);
    return tween;
  }

  killAll(): void {
    this.tweens = [];
  }

  update(deltaMs: number): void {
    const running = this.tweens;
    this.tweens = [];
    for (const tween of running) {
      tween.elapsedMs += deltaMs;
      this.apply(tween);
      if (tween.elapsedMs < this.totalMs(tween)) {
        this.tweens.push(tween);
        continue;
      }
      tween.onComplete?.();
    }
  }

  private totalMs(tween: ActiveTween): number {
    return tween.yoyo ? tween.durationMs * 2 + tween.holdMs : tween.durationMs;
  }

  private apply(tween: ActiveTween): void {
    const progress = this.progress(tween);
    tween.targets.forEach((target, index) => {
      if (!target.active) return;
      for (const prop of tween.props) {
        const from = prop.from[index] ?? 0;
        (target as unknown as Record<string, number>)[prop.key] = from + (prop.to - from) * progress;
      }
    });
  }

  private progress(tween: ActiveTween): number {
    const { elapsedMs, durationMs, holdMs, yoyo } = tween;
    if (!yoyo) return tween.ease(clamp(elapsedMs / Math.max(1, durationMs), 0, 1));
    if (elapsedMs <= durationMs) return tween.ease(clamp(elapsedMs / Math.max(1, durationMs), 0, 1));
    if (elapsedMs <= durationMs + holdMs) return 1;
    const back = (elapsedMs - durationMs - holdMs) / Math.max(1, durationMs);
    return tween.ease(clamp(1 - back, 0, 1));
  }
}

export class StubClock {
  now = 0;
  private timers: { dueMs: number; callback: () => void }[] = [];

  delayedCall(delayMs: number, callback: () => void): { remove: () => void } {
    const timer = { dueMs: this.now + delayMs, callback };
    this.timers.push(timer);
    return {
      remove: () => {
        this.timers = this.timers.filter((entry) => entry !== timer);
      },
    };
  }

  update(nowMs: number): void {
    this.now = nowMs;
    const due = this.timers.filter((timer) => timer.dueMs <= nowMs);
    this.timers = this.timers.filter((timer) => timer.dueMs > nowMs);
    for (const timer of due) timer.callback();
  }
}

// --- the scene ------------------------------------------------------------

export type StubSceneConfig = { key?: string };

export class StubScene {
  readonly textures = new StubTextureManager();
  readonly anims = new StubAnimationManager();
  readonly children = new StubDisplayList();
  readonly cameras: StubCameraManager;
  readonly add: StubGameObjectFactory;
  readonly input = new StubInputPlugin();
  readonly tweens = new StubTweenManager();
  readonly time = new StubClock();
  readonly sceneKey: string;

  constructor(config: StubSceneConfig | string = {}) {
    this.sceneKey = typeof config === "string" ? config : (config.key ?? "scene");
    this.cameras = new StubCameraManager(HEADLESS_CANVAS.width, HEADLESS_CANVAS.height);
    this.add = new StubGameObjectFactory(this.children, this.textures, this.anims);
  }

  /**
   * One engine frame's worth of everything the scene does not step itself.
   *
   * The order is Phaser's: the clock and the display list's animations run on the scene's pre-update,
   * tweens on its update, the scene's own `update` after both, and the camera at render.
   */
  stepEngine(nowMs: number, deltaMs: number, update: () => void): void {
    this.time.update(nowMs);
    for (const child of this.children.list) {
      if (child instanceof StubSprite && child.active) child.anims.update(deltaMs);
    }
    this.tweens.update(deltaMs);
    update();
    this.cameras.main.preRender();
  }
}

// --- the module ------------------------------------------------------------

export const HEADLESS_CANVAS = Object.freeze({ width: 1280, height: 720 });

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

function linear(from: number, to: number, t: number): number {
  return (to - from) * t + from;
}

/** Only the codes the platformer binds; a name it does not bind would be a silent `undefined`. */
export const KEY_CODES = Object.freeze({
  A: 65,
  BACKTICK: 192,
  D: 68,
  DOWN: 40,
  E: 69,
  EIGHT: 56,
  ENTER: 13,
  FIVE: 53,
  FOUR: 52,
  I: 73,
  J: 74,
  K: 75,
  LEFT: 37,
  ONE: 49,
  P: 80,
  Q: 81,
  RIGHT: 39,
  S: 83,
  SEVEN: 55,
  SHIFT: 16,
  SIX: 54,
  SPACE: 32,
  THREE: 51,
  TWO: 50,
  UP: 38,
  W: 87,
  X: 88,
  Z: 90,
});

/** The `Phaser` default export the scene and its subsystems import. */
export const HeadlessPhaser = Object.freeze({
  Scene: StubScene,
  Game: class {},
  AUTO: 0,
  CANVAS: 1,
  Scale: Object.freeze({ FIT: 1, CENTER_BOTH: 2, NONE: 0 }),
  Textures: Object.freeze({ FilterMode: Object.freeze({ NEAREST: 0 }) }),
  TintModes: Object.freeze({ FILL: 1 }),
  Math: Object.freeze({ Clamp: clamp, Linear: linear }),
  Input: Object.freeze({
    Events: Object.freeze({ POINTER_DOWN: "pointerdown", GAMEOBJECT_DOWN: "gameobjectdown" }),
    Keyboard: Object.freeze({
      KeyCodes: KEY_CODES,
      JustDown: (key: StubKey | undefined) => key?.consumeJustDown() ?? false,
    }),
  }),
});

/** The module body `mock.module("phaser", …)` installs. */
export function headlessPhaserModule(): Record<string, unknown> {
  return { default: HeadlessPhaser, ...HeadlessPhaser };
}
