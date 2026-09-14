extends CanvasLayer
## The "Obtained" panel every grant ends in: a dim veil, a title, the items as cards revealed one after
## another, and a footer saying a tap anywhere closes it. The same panel serves a source claim, a mail
## claim and whatever grants come later; it knows items only through the design and the text callable
## it is given, and its own chrome strings through `labels` (English defaults). Runs on real time with
## the tree paused (process always).

signal closed

const STYLE := preload("style.gd")
const CARD := preload("item_card.gd")
const DEFAULT_LABELS := {"title": "Obtained", "tap_to_close": "Tap anywhere to close", "stack_full": "Could not hold: {items}"}
const REVEAL_FIRST_S := 0.18
const REVEAL_STEP_S := 0.09
const REVEAL_LEN_S := 0.3
const MIN_OPEN_S := 0.35     # a press before the first card has shown does not close (a stray tap)

var _root: Control
var _veil: ColorRect
var _panel: Panel
var _title: Label
var _cards_holder: Control
var _footer: Label
var _lost: Label
var _cards: Array = []
var _t := 0.0
var _open := false
var _last_usec := 0
var _laid_out := Vector2.ZERO


func _init() -> void:
	layer = 9
	process_mode = Node.PROCESS_MODE_ALWAYS
	_root = STYLE.ignore(Control.new())
	_root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_root.visible = false
	add_child(_root)
	_veil = STYLE.veil()
	_veil.gui_input.connect(_on_veil_input)
	_root.add_child(_veil)
	_panel = STYLE.ignore(Panel.new()) as Panel
	_root.add_child(_panel)
	_title = STYLE.caps("", 34.0)
	_panel.add_child(_title)
	_cards_holder = STYLE.ignore(Control.new())
	_panel.add_child(_cards_holder)
	_lost = STYLE.text_label("", STYLE.sans(500), 13.0, Color(1.0, 0.6, 0.55), HORIZONTAL_ALIGNMENT_CENTER)
	_lost.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_lost.vertical_alignment = VERTICAL_ALIGNMENT_TOP   # a wrapping label's first-pass height is stale; top keeps the text put
	_lost.visible = false
	_panel.add_child(_lost)
	_footer = STYLE.text_label("", STYLE.serif(400, true), 16.0, Color(STYLE.BONE, 0.7), HORIZONTAL_ALIGNMENT_CENTER)
	_panel.add_child(_footer)


func is_open() -> bool:
	return _open


func open(entries: Array, catalog: RefCounted, text: Callable, labels: Dictionary = {}, lost: Array = []) -> void:
	## `entries` is a granted list of {item, count}; `lost` what a full stack refused (shown as a note).
	for c in _cards:
		c.queue_free()
	_cards.clear()
	for entry: Dictionary in entries:
		var spec: Dictionary = catalog.item(String(entry["item"]))
		var card := CARD.new()
		card.configure(String(entry["item"]), spec, int(entry["count"]), STYLE.item_name(text, spec), 1.0)
		card.reveal = 0.0
		_cards_holder.add_child(card)
		_cards.append(card)
	_title.text = STYLE.label(labels, DEFAULT_LABELS, "title")
	_footer.text = STYLE.label(labels, DEFAULT_LABELS, "tap_to_close")
	if lost.is_empty():
		_lost.visible = false
	else:
		var parts: Array[String] = []
		for entry: Dictionary in lost:
			parts.append("%s ×%d" % [STYLE.item_name(text, catalog.item(String(entry["item"]))), int(entry["count"])])
		_lost.text = STYLE.label(labels, DEFAULT_LABELS, "stack_full", {"items": ", ".join(parts)})
		_lost.visible = true
	_t = 0.0
	_open = true
	_root.visible = true
	_root.modulate.a = 0.0
	_last_usec = Time.get_ticks_usec()
	_laid_out = Vector2.ZERO
	_relayout()


func close() -> void:
	if not _open:
		return
	_open = false
	_root.visible = false
	closed.emit()


func _on_veil_input(event: InputEvent) -> void:
	if _open and _t >= MIN_OPEN_S and STYLE.pressed(event):
		_veil.accept_event()
		close()


func _input(event: InputEvent) -> void:
	# Enter, Space or Escape close it too, and never reach the host beneath
	if not _open:
		return
	if event is InputEventKey and event.pressed and not event.echo and event.keycode in [KEY_ENTER, KEY_KP_ENTER, KEY_SPACE, KEY_ESCAPE]:
		get_viewport().set_input_as_handled()
		if _t >= MIN_OPEN_S:
			close()


func _process(_delta: float) -> void:
	if not _open:
		return
	var now := Time.get_ticks_usec()
	var real := clampf(float(now - _last_usec) / 1000000.0, 0.0, 0.1)
	_last_usec = now
	_t += real
	if _root.get_viewport_rect().size != _laid_out:
		_relayout()
	_root.modulate.a = clampf(_t / 0.2, 0.0, 1.0)
	for i in _cards.size():
		var start := REVEAL_FIRST_S + REVEAL_STEP_S * float(i)
		_cards[i].reveal = clampf((_t - start) / REVEAL_LEN_S, 0.0, 1.0)
	_footer.modulate.a = clampf((_t - REVEAL_FIRST_S - REVEAL_STEP_S * _cards.size()) / 0.3, 0.0, 1.0)


func _relayout() -> void:
	var vp := _root.get_viewport_rect().size
	_laid_out = vp
	var s := STYLE.scale(vp)
	var tile := CARD.tile_size(s)
	var gap := roundf(14.0 * s)
	var n := _cards.size()
	var max_cols := maxi(1, int(floorf((vp.x * 0.86 - 40.0 * s) / (tile.x + gap))))
	var cols := clampi(n, 1, mini(5, max_cols))
	var rows := maxi(1, int(ceilf(float(n) / float(cols))))
	var grid_w := cols * tile.x + (cols - 1) * gap
	var grid_h := rows * tile.y + (rows - 1) * gap
	var pad := roundf(28.0 * s)
	var title_h := roundf(48.0 * s)
	var footer_h := roundf(30.0 * s)
	var lost_h := roundf(40.0 * s) if _lost.visible else 0.0
	var panel_w := maxf(grid_w + pad * 2.0, 380.0 * s)
	var panel_h := pad + title_h + gap + grid_h + lost_h + gap + footer_h + pad * 0.6
	_panel.add_theme_stylebox_override("panel", STYLE.flat(STYLE.PANEL, 12.0 * s, Color(STYLE.GOLD, 0.6), maxf(1.5 * s, 1.0)))
	_panel.position = Vector2(roundf((vp.x - panel_w) * 0.5), roundf((vp.y - panel_h) * 0.5))
	_panel.size = Vector2(panel_w, panel_h)
	_title.add_theme_font_size_override("font_size", int(roundf(30.0 * s)))
	_title.position = Vector2(0.0, pad * 0.6)
	_title.size = Vector2(panel_w, title_h)
	_cards_holder.position = Vector2(roundf((panel_w - grid_w) * 0.5), pad + title_h + gap * 0.5)
	_cards_holder.size = Vector2(grid_w, grid_h)
	for i in n:
		var card: Control = _cards[i]
		card.configure(card.item_id, card.spec, card.count, card.item_name, s)
		card.position = Vector2((i % cols) * (tile.x + gap), (i / cols) * (tile.y + gap))
	_lost.add_theme_font_size_override("font_size", int(roundf(13.0 * s)))
	STYLE.place(_lost, Vector2(pad, _cards_holder.position.y + grid_h + gap * 0.5), Vector2(panel_w - pad * 2.0, lost_h))
	_footer.add_theme_font_size_override("font_size", int(roundf(16.0 * s)))
	_footer.position = Vector2(0.0, panel_h - footer_h - pad * 0.5)
	_footer.size = Vector2(panel_w, footer_h)
