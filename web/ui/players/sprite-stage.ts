// Player: the sprite stage: the strips drawn the way the game draws them, the play buttons and the keyboard character.
//
// Moved from the [data-sprite-stage] section of the retired showcase's page script: same
// logic, same constants and the same comments, typed.
// Root: [data-sprite-stage], with its config. Hooks inside it: [data-stage], [data-body],
// [data-shadow], [data-ladder], [data-rope], [data-ground], [data-hint], [data-play],
// [data-opt], [data-info].

import type { Mount } from "./dom";

/** One delivered strip, as `<SpriteStage>` writes it into the config (the record's `states`). */
interface Motion {
  readonly state: string;
  readonly src: string;
  readonly columns: number;
  readonly cell: readonly [number, number];
  readonly frames: readonly number[];
  readonly mode: "loop" | "once" | "hold" | "gameplay_driven";
  /** Null on a hold or a climb, which never read a clock. */
  readonly fps: number | null;
  readonly mirror: boolean;
  readonly rebase: number;
}

export interface SpriteStageConfig {
  readonly states: readonly Motion[];
  readonly per_unit: number;
  readonly baseline: string;
}

/** A stage box, with the hook that lets a test advance it by hand. */
type StageBox = HTMLElement & { step?: (dt: number) => void };

// Sprite stage: the delivered strips drawn the way the game draws them. Sizes are in units of
// character height; a strip's cell is scaled by the ruler and its size correction, and its bottom
// stands on the ground.
export const mount: Mount<SpriteStageConfig> = (root, cfg) => {
  const box = root as StageBox;
  const controller = new AbortController(), { signal } = controller;
  const motions: Record<string, Motion> = Object.fromEntries(cfg.states.map(s => [s.state, s]));
  cfg.states.forEach(s => { new Image().src = s.src; });
  const $ = (sel: string) => box.querySelector(sel) as HTMLElement;
  const stage = $("[data-stage]"), body = $("[data-body]"), shadow = $("[data-shadow]"), ladder = $("[data-ladder]"), rope = $("[data-rope]");
  const words = (s: string) => box.querySelector(`[data-play="${s}"]`)?.textContent ?? s;
  const WALK = 1.4, RUN = 3.2, JUMP = 4.2, FALL = 13, CLIMB = 0.9, RUNG = 0.2, EDGE = 0.6;
  const opt: Record<string, boolean> = { raw: false, box: false }, keys = new Set<string>();
  const st = { state: "idle", t: 0, x: 3, y: 0, vy: 0, face: 1, travel: 0, demo: "idle" as string | null, dir: 1, wait: 0 };
  let U = 1, W = 1, H = 1, ground = 1;
  const measure = () => { const r = stage.getBoundingClientRect(); H = r.height; U = H * 0.34; W = r.width / U; ground = H * 0.84; };
  const clamp = (v: number, lo: number, hi: number) => Math.min(Math.max(v, lo), hi);
  const once = (s: string) => motions[s].mode === "once";
  // Only reached for a clocked strip (a loop or a one-shot), which has its fps.
  const length = (s: string) => motions[s].frames.length / (motions[s].fps as number);
  const climbing = () => st.state.startsWith("climb_");
  const top = () => { const m = motions[st.state]; return ground / U - m.cell[1] * m.rebase / cfg.per_unit - 0.1; };
  const set = (s: string, restart = false) => { if (restart || st.state !== s) { st.state = s; st.t = 0; describe(); } };
  const describe = () => {
    const m = motions[st.state], n = m.frames.length;
    const play = m.mode === "loop" ? `${n} frames at ${m.fps} fps, looping` : m.mode === "once" ? `${n} frames at ${m.fps} fps, played once`
      : m.mode === "hold" ? `holds one frame of the ${m.columns} drawn` : `${n} frames, stepped by the distance climbed, not by a clock`;
    const size = opt.raw ? (m.rebase === 1 ? "the size every other strip is matched to" : `shown as drawn; the correction would scale it ${m.rebase}×`)
      : st.state === cfg.baseline ? "the size every other strip is matched to" : `drawn at ${m.rebase}× to match ${words(cfg.baseline).toLowerCase()}`;
    $("[data-info]").textContent = `${words(st.state)}: ${play}; ${size}; ${m.mirror ? "mirrored when facing left" : "faces away, so it is never mirrored"}.`;
  };
  const press = (s: string | null) => box.querySelectorAll<HTMLElement>("[data-play]").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.play === s)));
  const fall = (dt: number) => {
    if (st.y <= 0 && st.vy <= 0) return false;
    st.vy -= FALL * dt; st.y += st.vy * dt;
    if (st.y > 0) return false;
    st.y = 0; st.vy = 0; return true;
  };
  const climbBy = (dy: number) => { const y = clamp(st.y + dy, 0.12, top()); st.travel += Math.abs(y - st.y); st.y = y; return y; };

  // A button plays one state on its own: walks cross the stage and turn, one-shots repeat after a pause.
  const demo = (dt: number) => {
    const d = st.demo as string;
    if (d === "walk" || d === "run") {
      st.x += st.face * (d === "run" ? RUN : WALK) * dt;
      if (st.x > W - EDGE || st.x < EDGE) { st.x = clamp(st.x, EDGE, W - EDGE); st.face *= -1; }
      set(d);
    } else if (d === "jump") {
      if (fall(dt)) st.wait = 0.6;
      if (st.y === 0 && (st.wait -= dt) <= 0) { st.vy = JUMP; st.y = 1e-4; set("jump", true); }
      else if (st.y === 0) set("idle");
    } else if (d.startsWith("climb_")) {
      set(d);
      if (st.wait > 0) st.wait -= dt;
      else { const y = climbBy(st.dir * CLIMB * dt); if (y >= top() || y <= 0.12) { st.dir *= -1; st.wait = 0.6; } }
    } else if (once(d)) {
      if (st.state !== d || st.t > length(d) + (d === "death" ? 1.4 : 0.7)) set(d, true);
    } else set(d);
  };
  // The keyboard drives it as a game would.
  const drive = (dt: number) => {
    if (climbing()) {
      const dy = ((keys.has("ArrowUp") ? 1 : 0) - (keys.has("ArrowDown") ? 1 : 0)) * CLIMB * dt;
      if (dy) climbBy(dy);
      return;
    }
    if (st.state === "death") return;
    const dir = (keys.has("ArrowRight") ? 1 : 0) - (keys.has("ArrowLeft") ? 1 : 0), fast = keys.has("Shift");
    const busy = once(st.state) && st.state !== "jump" && st.t < length(st.state);
    if (dir && (!busy || st.y > 0)) { st.face = dir; st.x = clamp(st.x + dir * (fast ? RUN : WALK) * dt, EDGE, W - EDGE); }
    fall(dt);
    if (!busy) set(st.y > 0 ? "jump" : keys.has("ArrowDown") ? "crouch" : dir ? (fast ? "run" : "walk") : "idle");
  };
  const frame = (m: Motion) => {
    const n = m.frames.length;
    if (m.mode === "hold") return m.frames[0];
    if (m.mode === "gameplay_driven") return m.frames[Math.floor(st.travel / RUNG) % n];
    const i = Math.floor(st.t * (m.fps as number));
    return m.frames[m.mode === "loop" ? i % n : Math.min(i, n - 1)];
  };
  const draw = () => {
    const m = motions[st.state], k = U * (opt.raw ? 1 : m.rebase) / cfg.per_unit, w = m.cell[0] * k, h = m.cell[1] * k;
    Object.assign(body.style, {
      width: `${w}px`, height: `${h}px`, left: `${st.x * U - w / 2}px`, top: `${ground - st.y * U - h}px`,
      backgroundImage: `url("${m.src}")`, backgroundSize: `${m.columns * w}px ${h}px`, backgroundPosition: `${-frame(m) * w}px 0`,
      transform: m.mirror && st.face < 0 ? "scaleX(-1)" : "", outline: opt.box ? "1px dashed rgb(161 161 170)" : "",
    });
    const lift = clamp(st.y, 0, 1), sw = U * 0.42 * (1 - lift * 0.5), sh = U * 0.07;
    Object.assign(shadow.style, { width: `${sw}px`, height: `${sh}px`, left: `${st.x * U - sw / 2}px`, top: `${ground - sh / 2}px`,
      opacity: String(climbing() ? 0 : 0.18 * (1 - lift * 0.6)) });
    ladder.classList.toggle("hidden", st.state !== "climb_ladder");
    rope.classList.toggle("hidden", st.state !== "climb_rope");
    Object.assign(ladder.style, { left: `${st.x * U - U * 0.26}px`, width: `${U * 0.52}px`, height: `${ground}px`,
      background: `repeating-linear-gradient(to top, transparent 0 ${RUNG * U - 3}px, rgb(161 161 170) ${RUNG * U - 3}px ${RUNG * U}px)` });
    Object.assign(rope.style, { left: `${st.x * U - 1.5}px`, height: `${ground}px` });
  };
  const step = (dt: number) => {
    st.t += dt;
    if (st.demo) demo(dt); else drive(dt);
    draw();
  };
  box.step = step;  // lets a test advance the stage by hand

  box.querySelectorAll<HTMLElement>("[data-play]").forEach(b => b.addEventListener("click", () => {
    const s = b.dataset.play as string;
    st.demo = s; st.wait = 0; st.dir = 1; st.vy = 0;
    if (s.startsWith("climb_")) { st.x = clamp(st.x, 1, W - 1); st.y = 0.12; } else st.y = 0;
    set(s, true); press(s);
  }, { signal }));
  box.querySelectorAll<HTMLInputElement>("[data-opt]").forEach(input => input.addEventListener("change", () => { opt[input.dataset.opt as string] = input.checked; describe(); draw(); }, { signal }));
  const KEYS = ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Shift", "z", "x"];
  stage.addEventListener("keydown", e => {
    const k = e.key === " " ? "ArrowUp" : e.key.length === 1 ? e.key.toLowerCase() : e.key;
    if (!KEYS.includes(k)) return;
    e.preventDefault();
    $("[data-hint]").classList.add("hidden");
    if (st.demo) { st.demo = null; press(null); if (!climbing()) { st.y = Math.max(st.y, 0); set("idle"); } }
    if (st.state === "death") set("idle");
    if (!keys.has(k)) {
      if (climbing() && (k === "ArrowLeft" || k === "ArrowRight")) { st.vy = 0; st.face = k === "ArrowLeft" ? -1 : 1; set("jump", true); }
      else if (!climbing() && k === "ArrowUp" && st.y === 0) { st.vy = JUMP; st.y = 1e-4; set("jump", true); }
      else if (!climbing() && k === "z") set("basic_attack", true);
      else if (!climbing() && k === "x") set("skill_cast", true);
    }
    keys.add(k);
  }, { signal });
  stage.addEventListener("keyup", e => keys.delete(e.key === " " ? "ArrowUp" : e.key.length === 1 ? e.key.toLowerCase() : e.key), { signal });
  stage.addEventListener("blur", () => keys.clear(), { signal });
  stage.addEventListener("pointerdown", () => stage.focus({ preventScroll: true }), { signal });
  const resized = new ResizeObserver(() => { measure(); st.x = clamp(st.x, EDGE, W - EDGE); draw(); });
  resized.observe(stage);
  measure(); st.x = W / 2; set("idle", true); press("idle"); draw();
  let last = performance.now(), frameId = 0;
  const loop = (now: number) => { step(Math.min(0.05, (now - last) / 1000)); last = now; frameId = requestAnimationFrame(loop); };
  frameId = requestAnimationFrame(loop);
  return () => {
    controller.abort();
    resized.disconnect();
    cancelAnimationFrame(frameId);
    delete box.step;
  };
};
