extends CanvasLayer
## The inbox: mail rows on the left (an unread dot, the title, the sender, the days left, a claimed
## mark), the selected mail on the right (title, sender, body, its attachments as cards, Claim), and
## Claim all along the bottom. It shows what the host hands it in refresh() and asks through signals;
## the host reads and writes the ledger. Mail text comes from the design's own keys through the text
## callable; the chrome strings through `labels` (English defaults). Runs on real time with the tree
## paused.

signal closed
signal selected(id: int)
signal claim_requested(id: int)
signal claim_all_requested

const STYLE := preload("style.gd")
const CARD := preload("item_card.gd")
const DEFAULT_LABELS := {"title": "Mailbox", "close": "Close", "claim": "Claim", "claimed": "Claimed", "claim_all": "Claim all", "empty": "No mail.", "attachments": "Attachments", "days_left": "{days} days left", "keeps": "Keeps"}

var _root: Control
var _panel: Panel
var _title: Label
var _close: Button
var _list_frame: Panel
var _scroll: ScrollContainer
var _list: VBoxContainer
var _empty: Label
var _detail: Control
var _d_title: Label
var _d_from: Label
var _d_body: Label
var _d_attach_label: Label
var _d_cards: Array = []
var _claim: Button
var _claim_all: Button
var _rows: Array = []          # MailRow
var _mails: Array = []         # the records shown, in order
var _selected := -1
var _text: Callable
var _catalog: RefCounted
var _labels: Dictionary = {}
var _now := 0
var _laid_out := Vector2.ZERO
var _open := false


func _init() -> void:
	layer = 8
	process_mode = Node.PROCESS_MODE_ALWAYS
	_root = STYLE.ignore(Control.new())
	_root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_root.visible = false
	add_child(_root)
	_root.add_child(STYLE.veil())
	_panel = STYLE.ignore(Panel.new()) as Panel
	_root.add_child(_panel)
	_title = STYLE.caps("", 28.0, STYLE.GOLD, HORIZONTAL_ALIGNMENT_LEFT)
	_panel.add_child(_title)
	_close = STYLE.button("", 14.0, false)
	_close.pressed.connect(func() -> void: close())
	_panel.add_child(_close)
	_list_frame = STYLE.ignore(Panel.new()) as Panel
	_panel.add_child(_list_frame)
	_scroll = ScrollContainer.new()
	_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	_scroll.focus_mode = Control.FOCUS_NONE
	_list_frame.add_child(_scroll)
	_list = VBoxContainer.new()
	_list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_scroll.add_child(_list)
	_empty = STYLE.text_label("", STYLE.serif(400, true), 16.0, Color(STYLE.BONE, 0.6), HORIZONTAL_ALIGNMENT_CENTER)
	_list_frame.add_child(_empty)
	_detail = STYLE.ignore(Control.new())
	_panel.add_child(_detail)
	_d_title = STYLE.text_label("", STYLE.serif(600), 22.0, STYLE.BONE)
	_d_title.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS   # one line: the row already shows it whole
	_detail.add_child(_d_title)
	_d_from = STYLE.text_label("", STYLE.sans(500), 13.0, STYLE.DIM)
	_detail.add_child(_d_from)
	_d_body = STYLE.text_label("", STYLE.sans(400), 14.5, Color(STYLE.BONE, 0.9))
	_d_body.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_d_body.vertical_alignment = VERTICAL_ALIGNMENT_TOP
	_detail.add_child(_d_body)
	_d_attach_label = STYLE.text_label("", STYLE.sans(700), 12.5, STYLE.GOLD)
	_d_attach_label.uppercase = true
	_detail.add_child(_d_attach_label)
	_claim = STYLE.button("", 16.0, true)
	_claim.pressed.connect(func() -> void:
		if _selected >= 0:
			claim_requested.emit(int(_mails[_selected]["id"])))
	_detail.add_child(_claim)
	_claim_all = STYLE.button("", 15.0, false)
	_claim_all.pressed.connect(func() -> void: claim_all_requested.emit())
	_panel.add_child(_claim_all)


func is_open() -> bool:
	return _open


func open(catalog: RefCounted, text: Callable, now: int, mails: Array, labels: Dictionary = {}) -> void:
	_catalog = catalog
	_text = text
	_labels = labels
	_now = now
	_title.text = _l("title")
	_close.text = _l("close")
	_claim.text = _l("claim")
	_claim_all.text = _l("claim_all")
	_empty.text = _l("empty")
	_d_attach_label.text = _l("attachments")
	_selected = -1
	_open = true
	_root.visible = true
	_laid_out = Vector2.ZERO
	refresh(mails, -1)


func refresh(mails: Array, keep_id: int = -1) -> void:
	## Rebuilds the rows from the records (already sorted by the host) and keeps the selection when
	## that mail is still shown; otherwise the first mail is selected.
	_mails = mails.duplicate()
	for r in _rows:
		r.queue_free()
	_rows.clear()
	var s := STYLE.scale(_root.get_viewport_rect().size)
	for i in _mails.size():
		var row := MailRow.new()
		row.ui = s
		row.setup(_mails[i], _text, _now, _labels)
		row.pressed.connect(_on_row.bind(i))
		_list.add_child(row)
		_rows.append(row)
	_empty.visible = _mails.is_empty()
	var index := -1
	for i in _mails.size():
		if int(_mails[i]["id"]) == keep_id:
			index = i
	if index < 0 and not _mails.is_empty():
		index = 0
	_select(index, index >= 0 and keep_id < 0)
	var any_claimable := false
	for mail: Dictionary in _mails:
		if not bool(mail["claimed"]) and not mail["attachments"].is_empty():
			any_claimable = true
	_claim_all.disabled = not any_claimable
	_relayout()


func close() -> void:
	if not _open:
		return
	_open = false
	_root.visible = false
	closed.emit()


func _on_row(index: int) -> void:
	_select(index, true)
	_relayout()


func _select(index: int, announce: bool) -> void:
	_selected = index
	for i in _rows.size():
		_rows[i].selected = i == index
		_rows[i].queue_redraw()
	for c in _d_cards:
		c.queue_free()
	_d_cards.clear()
	_detail.visible = index >= 0
	if index < 0:
		return
	var mail: Dictionary = _mails[index]
	_d_title.text = String(_text.call(String(mail["title_key"])))
	var days: int = _days_left(mail)
	var when := _l("keeps") if days < 0 else _l("days_left", {"days": str(days)})
	_d_from.text = "%s · %s" % [String(_text.call(String(mail["sender_key"]))), when]
	_d_body.text = String(_text.call(String(mail["body_key"])))
	var attachments: Array = mail["attachments"]
	for entry: Dictionary in attachments:
		var card := CARD.new()
		var item: Dictionary = _catalog.item(String(entry["item"]))
		card.configure(String(entry["item"]), item, int(entry["count"]), STYLE.item_name(_text, item), 1.0)
		_detail.add_child(card)
		_d_cards.append(card)
	_d_attach_label.visible = not attachments.is_empty()
	var claimed := bool(mail["claimed"])
	_claim.visible = not attachments.is_empty()
	_claim.disabled = claimed
	_claim.text = _l("claimed" if claimed else "claim")
	if announce and not bool(mail["read"]):
		selected.emit(int(mail["id"]))
		mail["read"] = true
		_rows[index].setup(mail, _text, _now, _labels)


func _l(key: String, values: Dictionary = {}) -> String:
	return STYLE.label(_labels, DEFAULT_LABELS, key, values)


func _days_left(mail: Dictionary) -> int:
	var expires: Variant = mail.get("expires_at", null)
	if expires == null:
		return -1
	return maxi(int(ceilf(float(int(expires) - _now) / 86400.0)), 0)


func _input(event: InputEvent) -> void:
	if not _open:
		return
	if event is InputEventKey and event.pressed and not event.echo and event.keycode == KEY_ESCAPE:
		get_viewport().set_input_as_handled()
		close()


func _process(_delta: float) -> void:
	if _open and _root.get_viewport_rect().size != _laid_out:
		_relayout()


func _relayout() -> void:
	var vp := _root.get_viewport_rect().size
	_laid_out = vp
	var s := STYLE.scale(vp)
	var pad := roundf(22.0 * s)
	var panel_w := clampf(vp.x * 0.86, 360.0 * s, 980.0 * s)
	var panel_h := clampf(vp.y * 0.82, 300.0 * s, 620.0 * s)
	_panel.add_theme_stylebox_override("panel", STYLE.flat(STYLE.PANEL, 14.0 * s, Color(STYLE.GOLD, 0.6), maxf(1.5 * s, 1.0)))
	_panel.position = Vector2(roundf((vp.x - panel_w) * 0.5), roundf((vp.y - panel_h) * 0.5))
	_panel.size = Vector2(panel_w, panel_h)
	var inner := panel_w - pad * 2.0
	_title.add_theme_font_size_override("font_size", int(roundf(26.0 * s)))
	_title.position = Vector2(pad, pad * 0.7)
	_title.size = Vector2(inner * 0.6, 36.0 * s)
	_close.add_theme_font_size_override("font_size", int(roundf(13.0 * s)))
	_close.size = Vector2(90.0 * s, 32.0 * s)
	_close.position = Vector2(panel_w - pad - _close.size.x, pad * 0.75)
	var top := pad * 0.7 + 46.0 * s
	var bottom_h := roundf(44.0 * s)
	var body_h := panel_h - top - pad - bottom_h - 10.0 * s
	var narrow := panel_w < 640.0 * s
	var list_w := inner if narrow else roundf(inner * 0.4)
	var gap := roundf(14.0 * s)
	_list_frame.add_theme_stylebox_override("panel", STYLE.flat(Color(0.0, 0.0, 0.0, 0.35), 8.0 * s, Color(STYLE.BONE, 0.15), 1.0))
	_list_frame.position = Vector2(pad, top)
	_list_frame.size = Vector2(list_w, body_h * (0.42 if narrow else 1.0))
	_scroll.position = Vector2(4.0 * s, 4.0 * s)
	_scroll.size = _list_frame.size - Vector2(8.0 * s, 8.0 * s)
	_list.custom_minimum_size.x = _scroll.size.x
	_list.add_theme_constant_override("separation", int(roundf(4.0 * s)))
	for r in _rows:
		r.ui = s
		r.custom_minimum_size = Vector2(_scroll.size.x, 58.0 * s)
		r.queue_redraw()
	_empty.add_theme_font_size_override("font_size", int(roundf(16.0 * s)))
	_empty.position = Vector2.ZERO
	_empty.size = _list_frame.size
	if narrow:
		_detail.position = Vector2(pad, top + _list_frame.size.y + gap)
		_detail.size = Vector2(inner, body_h - _list_frame.size.y - gap)
	else:
		_detail.position = Vector2(pad + list_w + gap, top)
		_detail.size = Vector2(inner - list_w - gap, body_h)
	var dw := _detail.size.x
	var y := 0.0
	_d_title.add_theme_font_size_override("font_size", int(roundf(21.0 * s)))
	STYLE.place(_d_title, Vector2(0.0, y), Vector2(dw, 30.0 * s))
	y += 32.0 * s
	_d_from.add_theme_font_size_override("font_size", int(roundf(13.0 * s)))
	STYLE.place(_d_from, Vector2(0.0, y), Vector2(dw, 20.0 * s))
	y += 30.0 * s
	var tile := CARD.tile_size(s)
	var cards_h := (tile.y + 26.0 * s) if not _d_cards.is_empty() else 0.0
	var button_h := roundf(42.0 * s) if _claim.visible else 0.0
	_d_body.add_theme_font_size_override("font_size", int(roundf(14.5 * s)))
	STYLE.place(_d_body, Vector2(0.0, y), Vector2(dw, maxf(_detail.size.y - y - cards_h - button_h - 14.0 * s, 30.0 * s)))
	var ay := _detail.size.y - button_h - cards_h - 6.0 * s
	_d_attach_label.add_theme_font_size_override("font_size", int(roundf(12.5 * s)))
	_d_attach_label.position = Vector2(0.0, ay)
	_d_attach_label.size = Vector2(dw, 18.0 * s)
	for i in _d_cards.size():
		var card: Control = _d_cards[i]
		card.configure(card.item_id, card.spec, card.count, card.item_name, s)
		card.position = Vector2(i * (tile.x + gap), ay + 22.0 * s)
	_claim.add_theme_font_size_override("font_size", int(roundf(16.0 * s)))
	_claim.size = Vector2(minf(dw, 220.0 * s), button_h)
	_claim.position = Vector2(dw - _claim.size.x, _detail.size.y - button_h)
	_claim_all.add_theme_font_size_override("font_size", int(roundf(15.0 * s)))
	_claim_all.size = Vector2(minf(list_w, 220.0 * s), bottom_h)
	_claim_all.position = Vector2(pad, panel_h - pad - bottom_h)


## One mail in the list: drawn on a flat Button so the press, hover and touch handling are the engine's.
class MailRow extends Button:
	var ui := 1.0
	var selected := false
	var _title := ""
	var _sub := ""
	var _unread := false
	var _claimed := false
	var _has_attachment := false

	func _init() -> void:
		focus_mode = Control.FOCUS_NONE
		text = ""
		for state in ["normal", "hover", "pressed", "disabled", "focus"]:
			add_theme_stylebox_override(state, StyleBoxEmpty.new())

	func setup(mail: Dictionary, text_fn: Callable, now: int, labels: Dictionary) -> void:
		_title = String(text_fn.call(String(mail["title_key"])))
		var expires: Variant = mail.get("expires_at", null)
		var when := STYLE.label(labels, DEFAULT_LABELS, "keeps")
		if expires != null:
			when = STYLE.label(labels, DEFAULT_LABELS, "days_left", {"days": str(maxi(int(ceilf(float(int(expires) - now) / 86400.0)), 0))})
		_sub = "%s · %s" % [String(text_fn.call(String(mail["sender_key"]))), when]
		_unread = not bool(mail["read"])
		_claimed = bool(mail["claimed"])
		_has_attachment = not mail["attachments"].is_empty()
		queue_redraw()

	func _draw() -> void:
		var s := ui
		var rect := Rect2(Vector2.ZERO, size)
		var back := Color(STYLE.GOLD, 0.16) if selected else (Color(STYLE.BONE, 0.07) if is_hovered() else Color(0, 0, 0, 0))
		draw_rect(rect, back)
		if selected:
			draw_rect(Rect2(Vector2.ZERO, Vector2(3.0 * s, size.y)), STYLE.GOLD)
		var x := 18.0 * s
		if _unread:
			draw_circle(Vector2(x * 0.5, size.y * 0.42), 4.0 * s, Color(0.95, 0.35, 0.3))
		var serif := STYLE.serif(600)
		var sans := STYLE.sans(500)
		var title_px := int(roundf(15.0 * s))
		var sub_px := int(roundf(11.5 * s))
		var col := Color(STYLE.BONE, 0.55 if _claimed else 1.0)
		var tw := size.x - x - 30.0 * s
		draw_string(serif, Vector2(x, size.y * 0.42 + title_px * 0.35), _title, HORIZONTAL_ALIGNMENT_LEFT, tw, title_px, col)
		draw_string(sans, Vector2(x, size.y * 0.78 + sub_px * 0.2), _sub, HORIZONTAL_ALIGNMENT_LEFT, tw, sub_px, Color(STYLE.DIM, 0.55 if _claimed else 1.0))
		if _has_attachment:
			# a small package mark on the right: a box, a ribbon across; dimmed once claimed
			var m := Vector2(size.x - 18.0 * s, size.y * 0.5)
			var half := 6.0 * s
			var c := Color(STYLE.GOLD, 0.35 if _claimed else 0.9)
			draw_rect(Rect2(m - Vector2(half, half), Vector2(half * 2.0, half * 2.0)), c, false, maxf(1.2 * s, 1.0))
			draw_line(m - Vector2(0.0, half), m + Vector2(0.0, half), c, maxf(1.2 * s, 1.0))
