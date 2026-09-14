extends CanvasLayer
## The result screen after a report: a title over a subtitle, up to three objectives as stars with
## their names, a record line, the reward rows (one per claimable source, each a name over its cards;
## a table entry shows as a "random drop" card), and a level track with its EXP bar. One button,
## Claim, until the host says the claim went through; then the bar fills and rolls the levels the EXP
## bought, and the buttons become Continue and Exit, whose meaning is the host's. This screen shows
## and asks; the host owns the tree pause, the claim and the popup.
##
## view: {title, subtitle, objectives: [{name, met}], record_line, rows: [{name, bundle}],
##        track: {level, exp}, exp_to_leave: Callable(level) -> int}
## labels (English defaults): claim, continue, exit, level "Lv. {level}", exp, level_up, random.

signal claim_pressed
signal continue_pressed
signal exit_pressed

const STYLE := preload("style.gd")
const CARD := preload("item_card.gd")
const DEFAULT_LABELS := {"claim": "Claim", "continue": "Continue", "exit": "Exit", "level": "Lv. {level}", "exp": "EXP", "level_up": "Level up", "random": "Random drop"}
const EXP_FILL_PER_S := 1.6      # bar fractions per real second while the EXP rolls in

var _root: Control
var _panel: Panel
var _title: Label
var _subtitle: Label
var _stars: Array = []
var _star_labels: Array = []
var _record: Label
var _rows_holder: Control
var _rows: Array = []             # [{label: Label, cards: [ItemCard]}]
var _level_label: Label
var _exp_label: Label
var _exp_bar: Control
var _level_up: Label
var _claim: Button
var _continue: Button
var _exit: Button
var _labels: Dictionary = {}
var _laid_out := Vector2.ZERO
var _last_usec := 0
var _t := 0.0
var _open := false
var _segments: Array = []         # the EXP roll: [from_fraction, to_fraction, level_after] played in order
var _segment := 0
var _fill := 0.0
var _level_shown := 1
var _exp_shown := 0
var _exp_to_leave: Callable
var _level_up_t := -1.0


func _init() -> void:
	layer = 8
	process_mode = Node.PROCESS_MODE_ALWAYS
	_root = STYLE.ignore(Control.new())
	_root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_root.visible = false
	add_child(_root)
	_root.add_child(STYLE.veil(Color(0.02, 0.015, 0.02, 0.7)))
	_panel = STYLE.ignore(Panel.new()) as Panel
	_root.add_child(_panel)
	_title = STYLE.caps("", 44.0)
	_panel.add_child(_title)
	_subtitle = STYLE.text_label("", STYLE.serif(400, true), 22.0, STYLE.BONE, HORIZONTAL_ALIGNMENT_CENTER)
	_panel.add_child(_subtitle)
	for i in 3:
		var star := STYLE.ignore(Star.new())
		_panel.add_child(star)
		_stars.append(star)
		var l := STYLE.text_label("", STYLE.sans(500), 12.0, STYLE.DIM, HORIZONTAL_ALIGNMENT_CENTER)
		l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		l.vertical_alignment = VERTICAL_ALIGNMENT_TOP
		_panel.add_child(l)
		_star_labels.append(l)
	_record = STYLE.text_label("", STYLE.sans(500), 14.0, Color(STYLE.BONE, 0.75), HORIZONTAL_ALIGNMENT_CENTER)
	_panel.add_child(_record)
	_rows_holder = STYLE.ignore(Control.new())
	_panel.add_child(_rows_holder)
	_level_label = STYLE.text_label("", STYLE.sans(700), 16.0, STYLE.GOLD)
	_panel.add_child(_level_label)
	_exp_label = STYLE.text_label("", STYLE.sans(500), 13.0, Color(STYLE.BONE, 0.75), HORIZONTAL_ALIGNMENT_RIGHT)
	_panel.add_child(_exp_label)
	_exp_bar = STYLE.ignore(Bar.new())
	_panel.add_child(_exp_bar)
	_level_up = STYLE.caps("", 20.0, STYLE.PINK)
	_level_up.visible = false
	_panel.add_child(_level_up)
	_claim = STYLE.button("", 18.0, true)
	_claim.pressed.connect(func() -> void: claim_pressed.emit())
	_panel.add_child(_claim)
	_continue = STYLE.button("", 16.0, false)
	_continue.pressed.connect(func() -> void: continue_pressed.emit())
	_continue.visible = false
	_panel.add_child(_continue)
	_exit = STYLE.button("", 16.0, true)
	_exit.pressed.connect(func() -> void: exit_pressed.emit())
	_exit.visible = false
	_panel.add_child(_exit)


func is_open() -> bool:
	return _open


func open(view: Dictionary, catalog: RefCounted, text: Callable, labels: Dictionary = {}) -> void:
	_labels = labels
	_exp_to_leave = view.get("exp_to_leave", Callable())
	_title.text = String(view.get("title", ""))
	_subtitle.text = String(view.get("subtitle", ""))
	var objectives: Array = view.get("objectives", [])
	for i in 3:
		var has := i < objectives.size()
		_stars[i].visible = has
		_star_labels[i].visible = has
		if has:
			(_stars[i] as Star).lit = bool(objectives[i].get("met", false))
			(_stars[i] as Star).reset()
			_star_labels[i].text = String(objectives[i].get("name", ""))
	_record.text = String(view.get("record_line", ""))
	for row in _rows:
		row["label"].queue_free()
		for c in row["cards"]:
			c.queue_free()
	_rows.clear()
	for spec: Dictionary in view.get("rows", []):
		var bundle: Array = spec.get("bundle", [])
		if bundle.is_empty():
			continue
		var label := STYLE.text_label(String(spec.get("name", "")), STYLE.sans(700), 13.0, STYLE.GOLD)
		label.uppercase = true
		_rows_holder.add_child(label)
		var cards: Array = []
		for entry: Dictionary in bundle:
			var card := CARD.new()
			if entry.has("table"):
				card.configure("?" + String(entry["table"]), {"type": "material", "rarity": "common"}, int(entry.get("rolls", 1)), STYLE.label(labels, DEFAULT_LABELS, "random"), 1.0)
			else:
				var item: Dictionary = catalog.item(String(entry["item"]))
				card.configure(String(entry["item"]), item, int(entry["count"]), STYLE.item_name(text, item), 1.0)
			_rows_holder.add_child(card)
			cards.append(card)
		_rows.append({"label": label, "cards": cards})
	var track: Dictionary = view.get("track", {})
	_level_shown = int(track.get("level", 1))
	_exp_shown = int(track.get("exp", 0))
	_fill = _fraction(_exp_shown, _level_shown)
	_segments.clear()
	_segment = 0
	_level_up.visible = false
	_level_up_t = -1.0
	_claim.text = STYLE.label(labels, DEFAULT_LABELS, "claim")
	_claim.visible = true
	_claim.disabled = false
	_continue.text = STYLE.label(labels, DEFAULT_LABELS, "continue")
	_exit.text = STYLE.label(labels, DEFAULT_LABELS, "exit")
	_continue.visible = false
	_exit.visible = false
	_t = 0.0
	_open = true
	_root.visible = true
	_root.modulate.a = 0.0
	_last_usec = Time.get_ticks_usec()
	_laid_out = Vector2.ZERO
	_apply_level()
	_relayout()


func set_claiming(on: bool) -> void:
	## The host is granting: the Claim button refuses a second press meanwhile.
	_claim.disabled = on


func show_result(level: Dictionary) -> void:
	## After the grant: {level_before, exp_before, level, exp} of the shown track (or {} when the claim
	## gave no EXP). The bar rolls from before to after and the buttons become Continue and Exit.
	_claim.visible = false
	_continue.visible = true
	_exit.visible = true
	_segments.clear()
	if not level.is_empty():
		var lv := int(level.get("level_before", _level_shown))
		var from := _fraction(int(level.get("exp_before", 0)), lv)
		var target_level := int(level.get("level", lv))
		while lv < target_level:
			_segments.append([from, 1.0, lv + 1])
			from = 0.0
			lv += 1
		_segments.append([from, _fraction(int(level.get("exp", 0)), target_level), target_level])
		_segment = 0
		_fill = float(_segments[0][0])
		_exp_shown = int(level.get("exp", 0))
	_relayout()


func close() -> void:
	_open = false
	_root.visible = false


func _fraction(exp_value: int, level: int) -> float:
	var need := int(_exp_to_leave.call(level)) if _exp_to_leave.is_valid() else 0
	return 0.0 if need <= 0 else clampf(float(exp_value) / float(need), 0.0, 1.0)


func _apply_level() -> void:
	_level_label.text = STYLE.label(_labels, DEFAULT_LABELS, "level", {"level": str(_level_shown)})
	var need := int(_exp_to_leave.call(_level_shown)) if _exp_to_leave.is_valid() else 0
	var shown := _exp_shown if _segments.is_empty() else int(roundf(_fill * need))
	_exp_label.text = "%s %d / %d" % [STYLE.label(_labels, DEFAULT_LABELS, "exp"), shown, need]
	(_exp_bar as Bar).fill = _fill
	_exp_bar.queue_redraw()


func _input(event: InputEvent) -> void:
	# Escape must not reach the host beneath; Enter presses the one plate button on screen
	if not _open:
		return
	if event is InputEventKey and event.pressed and not event.echo:
		if event.keycode == KEY_ESCAPE:
			get_viewport().set_input_as_handled()
		elif event.keycode in [KEY_ENTER, KEY_KP_ENTER] and _t > 0.4:
			get_viewport().set_input_as_handled()
			if _claim.visible and not _claim.disabled:
				claim_pressed.emit()
			elif _continue.visible:
				continue_pressed.emit()


func _process(_delta: float) -> void:
	if not _open:
		return
	var now := Time.get_ticks_usec()
	var real := clampf(float(now - _last_usec) / 1000000.0, 0.0, 0.1)
	_last_usec = now
	_t += real
	if _root.get_viewport_rect().size != _laid_out:
		_relayout()
	_root.modulate.a = clampf(_t / 0.35, 0.0, 1.0)
	for i in _stars.size():
		(_stars[i] as Star).tick(real, 0.3 + 0.25 * float(i))
	if not _segments.is_empty() and _segment < _segments.size():
		var seg: Array = _segments[_segment]
		_fill = move_toward(_fill, float(seg[1]), EXP_FILL_PER_S * real)
		if is_equal_approx(_fill, float(seg[1])):
			if _segment < _segments.size() - 1:   # a level rolled over
				_level_shown = int(seg[2])
				_fill = 0.0
				_level_up.visible = true
				_level_up_t = 0.0
			_segment += 1
		_apply_level()
	if _level_up_t >= 0.0:
		_level_up_t += real
		_level_up.modulate.a = clampf(1.0 - (_level_up_t - 1.2) / 0.5, 0.0, 1.0)
		if _level_up_t > 1.7:
			_level_up.visible = false
			_level_up_t = -1.0


func _relayout() -> void:
	var vp := _root.get_viewport_rect().size
	_laid_out = vp
	var s := STYLE.scale(vp)
	var pad := roundf(26.0 * s)
	var panel_w := clampf(vp.x * 0.78, 360.0 * s, 760.0 * s)
	var inner := panel_w - pad * 2.0
	var y := pad * 0.7
	_title.add_theme_font_size_override("font_size", int(roundf(40.0 * s)))
	_title.position = Vector2(0.0, y)
	_title.size = Vector2(panel_w, 52.0 * s)
	y += 54.0 * s
	_subtitle.add_theme_font_size_override("font_size", int(roundf(21.0 * s)))
	_subtitle.position = Vector2(0.0, y)
	_subtitle.size = Vector2(panel_w, 30.0 * s)
	y += 40.0 * s
	var star_r := roundf(24.0 * s)
	var star_gap := roundf(86.0 * s)
	var shown := 0
	for st in _stars:
		if st.visible:
			shown += 1
	if shown > 0:
		var x0 := panel_w * 0.5 - (shown - 1) * star_gap * 0.5
		for i in 3:
			if not _stars[i].visible:
				continue
			(_stars[i] as Star).r = star_r
			_stars[i].position = Vector2(x0 + i * star_gap - star_r, y)
			_stars[i].size = Vector2(star_r * 2.0, star_r * 2.0)
			_star_labels[i].add_theme_font_size_override("font_size", int(roundf(11.5 * s)))
			STYLE.place(_star_labels[i], Vector2(x0 + i * star_gap - star_gap * 0.5, y + star_r * 2.0 + 4.0 * s), Vector2(star_gap, 34.0 * s))
		y += star_r * 2.0 + 44.0 * s
	_record.add_theme_font_size_override("font_size", int(roundf(14.0 * s)))
	_record.visible = _record.text != ""
	if _record.visible:
		STYLE.place(_record, Vector2(pad, y), Vector2(inner, 22.0 * s))
		y += 34.0 * s
	# reward rows: each a small caps label over its cards in a line; the rows sit side by side across the
	# panel and start a new line only when the next one would not fit
	var tile := CARD.tile_size(s)
	var gap := roundf(12.0 * s)
	var row_gap := roundf(30.0 * s)
	var label_h := roundf(22.0 * s)
	var block_h := label_h + tile.y
	var rx := 0.0
	var ry := 0.0
	for row in _rows:
		var cards: Array = row["cards"]
		var label: Label = row["label"]
		var label_px := int(roundf(12.5 * s))
		label.add_theme_font_size_override("font_size", label_px)
		# a block is as wide as its cards or its label, whichever is wider, so labels never run together
		var label_w: float = label.get_theme_font("font").get_string_size(label.text.to_upper(), HORIZONTAL_ALIGNMENT_LEFT, -1.0, label_px).x + 6.0 * s
		var block_w := maxf(cards.size() * tile.x + (cards.size() - 1) * gap, label_w)
		if rx > 0.0 and rx + block_w > inner + 0.5:
			rx = 0.0
			ry += block_h + 14.0 * s
		STYLE.place(label, Vector2(rx, ry), Vector2(block_w, 18.0 * s))
		for i in cards.size():
			var card: Control = cards[i]
			card.configure(card.item_id, card.spec, card.count, card.item_name, s)
			card.position = Vector2(rx + i * (tile.x + gap), ry + label_h)
		rx += block_w + row_gap
	_rows_holder.position = Vector2(pad, y)
	if not _rows.is_empty():
		_rows_holder.size = Vector2(inner, ry + block_h)
		y += ry + block_h + 12.0 * s
	# the level block
	_level_label.add_theme_font_size_override("font_size", int(roundf(16.0 * s)))
	_level_label.position = Vector2(pad, y)
	_level_label.size = Vector2(inner * 0.5, 22.0 * s)
	_exp_label.add_theme_font_size_override("font_size", int(roundf(13.0 * s)))
	_exp_label.position = Vector2(pad + inner * 0.5, y)
	_exp_label.size = Vector2(inner * 0.5, 22.0 * s)
	y += 26.0 * s
	(_exp_bar as Bar).ui = s
	_exp_bar.position = Vector2(pad, y)
	_exp_bar.size = Vector2(inner, 14.0 * s)
	_level_up.add_theme_font_size_override("font_size", int(roundf(18.0 * s)))
	_level_up.text = STYLE.label(_labels, DEFAULT_LABELS, "level_up")
	_level_up.position = Vector2(0.0, y - 30.0 * s)
	_level_up.size = Vector2(panel_w, 24.0 * s)
	y += 34.0 * s
	# buttons
	var bh := roundf(46.0 * s)
	_claim.add_theme_font_size_override("font_size", int(roundf(18.0 * s)))
	_claim.position = Vector2(pad + inner * 0.25, y)
	_claim.size = Vector2(inner * 0.5, bh)
	_continue.add_theme_font_size_override("font_size", int(roundf(15.0 * s)))
	_exit.add_theme_font_size_override("font_size", int(roundf(15.0 * s)))
	var bw := (inner - gap) * 0.5
	_continue.position = Vector2(pad, y)
	_continue.size = Vector2(bw, bh)
	_exit.position = Vector2(pad + bw + gap, y)
	_exit.size = Vector2(bw, bh)
	y += bh + pad * 0.8
	_panel.add_theme_stylebox_override("panel", STYLE.flat(STYLE.PANEL, 14.0 * s, Color(STYLE.GOLD, 0.6), maxf(1.5 * s, 1.0)))
	var panel_h := minf(y, vp.y - 16.0 * s)
	_panel.position = Vector2(roundf((vp.x - panel_w) * 0.5), roundf((vp.y - panel_h) * 0.5))
	_panel.size = Vector2(panel_w, panel_h)
	_apply_level()


class Star extends Control:
	var lit := false
	var r := 24.0
	var _a := 0.0
	var _t := 0.0

	func reset() -> void:
		_a = 0.0
		_t = 0.0
		queue_redraw()

	func tick(real: float, delay: float) -> void:
		_t += real
		var goal := 1.0 if lit and _t > delay else 0.0
		if not is_equal_approx(_a, goal):
			_a = move_toward(_a, goal, real / 0.35)
			queue_redraw()

	func _draw() -> void:
		var c := size * 0.5
		var pts := PackedVector2Array()
		for i in 10:
			var a := -PI * 0.5 + TAU * float(i) / 10.0
			var rr := r if i % 2 == 0 else r * 0.45
			pts.append(c + Vector2(cos(a), sin(a)) * rr)
		var e := 1.0 - pow(1.0 - _a, 3.0)
		draw_colored_polygon(pts, Color(0.12, 0.1, 0.1))
		if e > 0.0:
			var lit_pts := PackedVector2Array()
			var k := lerpf(1.25, 1.0, e)
			for p in pts:
				lit_pts.append(c + (p - c) * k)
			draw_colored_polygon(lit_pts, Color(1.0, 0.84, 0.42, e))
			draw_circle(c, r * 0.22, Color(1.0, 0.97, 0.85, e * 0.9))
		var ring := pts.duplicate()
		ring.append(pts[0])
		draw_polyline(ring, Color(0.83, 0.67, 0.40, 0.8), 1.5, true)


class Bar extends Control:
	var fill := 0.0
	var ui := 1.0

	func _draw() -> void:
		var rect := Rect2(Vector2.ZERO, size)
		draw_rect(rect, Color(0.0, 0.0, 0.0, 0.55))
		var w := roundf(size.x * clampf(fill, 0.0, 1.0))
		if w > 0.0:
			draw_rect(Rect2(Vector2.ZERO, Vector2(w, size.y)), Color(0.83, 0.67, 0.40))
			draw_rect(Rect2(Vector2(0.0, 0.0), Vector2(w, maxf(size.y * 0.3, 1.0))), Color(1.0, 0.9, 0.68, 0.6))
		draw_rect(rect, Color(0.83, 0.67, 0.40, 0.7), false, maxf(1.0 * ui, 1.0))
