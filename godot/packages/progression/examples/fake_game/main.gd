extends Control
## A consumer with no real game: what a game does around the progression package, and nothing else.
## Buttons stand in for a battle (two ways to win the arena, with different measurements), a login
## (the daily gift, a periodic source), a shop (spend) and the mailbox. The design and the text are
## this example's own files; the ledger persists at user://progression_example/ledger.json through the
## package's store (--fresh starts over, --ledger <path> moves it). Every package call is here in the
## open: load, configure, report, preview, claim, spend, deliver, save.
##   godot --path godot/packages/progression res://examples/fake_game/main.tscn -- [--fresh] [--seed 7]

const CATALOG := preload("res://addons/progression/design/catalog.gd")
const TABLES := preload("res://addons/progression/design/tables.gd")
const LEDGER := preload("res://addons/progression/ledger/ledger.gd")
const LEVELS := preload("res://addons/progression/ledger/levels.gd")
const SOURCES := preload("res://addons/progression/ledger/sources.gd")
const CONDITIONS := preload("res://addons/progression/ledger/conditions.gd")
const MAILBOX := preload("res://addons/progression/ledger/mailbox.gd")
const STORE := preload("res://addons/progression/store.gd")
const RESULT_SCREEN := preload("res://addons/progression/presenters/result_screen.gd")
const REWARD_POPUP := preload("res://addons/progression/presenters/reward_popup.gd")
const MAILBOX_UI := preload("res://addons/progression/presenters/mailbox.gd")
const MAIL_BUTTON := preload("res://addons/progression/presenters/mail_button.gd")

const DESIGN_PATH := "res://examples/fake_game/design.json"
const TEXT_PATH := "res://examples/fake_game/text.json"
const DEFAULT_LEDGER_PATH := "user://progression_example/ledger.json"
const POTION_PRICE := [{"item": "gold", "count": 50}]
const WINS := {
	"fast": {"fight_s": 45.0, "hits_taken": 1, "hp_fraction": 0.8},
	"slow": {"fight_s": 200.0, "hits_taken": 6, "hp_fraction": 0.3},
}

var errors: Array[String] = []
var catalog: RefCounted
var ledger: Dictionary = {}
var ledger_path := DEFAULT_LEDGER_PATH
var screen: CanvasLayer
var popup: CanvasLayer
var mailbox_ui: CanvasLayer
var mail_button: Control
var status := ""
var clock_offset := 0          # checks move time forward without waiting a day

var _text: Dictionary = {}
var _rng := RandomNumberGenerator.new()
var _status_label: Label
var _balances_label: Label
var _pending_exp: Dictionary = {}


func _ready() -> void:
	var args := OS.get_cmdline_user_args()
	var li := args.find("--ledger")
	if li >= 0 and li + 1 < args.size():
		ledger_path = args[li + 1]
	var si := args.find("--seed")
	_rng.seed = int(args[si + 1]) if si >= 0 and si + 1 < args.size() else int(Time.get_unix_time_from_system())
	var design: Variant = JSON.parse_string(FileAccess.get_file_as_string(DESIGN_PATH))
	var text: Variant = JSON.parse_string(FileAccess.get_file_as_string(TEXT_PATH))
	if not design is Dictionary or not text is Dictionary:
		errors.append("The example's design or text did not parse")
		return
	_text = text
	catalog = CATALOG.new()
	errors.append_array(catalog.configure(design, text.keys()))
	if not errors.is_empty():
		return
	if "--fresh" in args:
		var absolute := ProjectSettings.globalize_path(ledger_path)
		if FileAccess.file_exists(absolute):
			DirAccess.remove_absolute(absolute)
	var loaded: Dictionary = STORE.load_document(ledger_path, Callable(LEDGER, "validate"), Callable(LEDGER, "create"), now())
	if loaded["refused"] != "":
		printerr("fake_game: " + loaded["refused"])
	ledger = loaded["document"]
	var welcome: Dictionary = MAILBOX.deliver_once(ledger, catalog, "welcome", now())
	if bool(loaded["fresh"]) or bool(welcome["delivered"]):
		_save()
	_build_ui()
	popup = REWARD_POPUP.new()
	add_child(popup)
	screen = RESULT_SCREEN.new()
	screen.claim_pressed.connect(_on_claim)
	screen.continue_pressed.connect(func() -> void: screen.close())
	screen.exit_pressed.connect(func() -> void: screen.close())
	add_child(screen)
	mailbox_ui = MAILBOX_UI.new()
	mailbox_ui.selected.connect(func(id: int) -> void: MAILBOX.mark_read(ledger, id); _save(); _refresh())
	mailbox_ui.claim_requested.connect(_on_mail_claim)
	mailbox_ui.claim_all_requested.connect(_on_mail_claim_all)
	mailbox_ui.closed.connect(_refresh)
	add_child(mailbox_ui)
	_refresh()


func text(key: String, values: Dictionary = {}) -> String:
	return String(_text.get(key, "[" + key + "]")).format(values)


func now() -> int:
	return int(Time.get_unix_time_from_system()) + clock_offset


func draw() -> float:
	return _rng.randf()


# --- what a game does ----------------------------------------------------------------------------------------

func win(way: String) -> Dictionary:
	## The battle ended: report the stage with what was measured and show the result screen.
	return report("stage:arena", WINS[way])


func report(trigger: String, measurements: Dictionary) -> Dictionary:
	var seen: Dictionary = SOURCES.preview(ledger, catalog, trigger, measurements, now())
	if not seen["errors"].is_empty():
		_note("; ".join(seen["errors"]))
		return seen
	var rows: Array = []
	var objectives: Array = []
	for row: Dictionary in seen["rows"]:
		if not bool(row["claimable"]):
			continue
		rows.append({"name": text(String(row["name_key"])), "bundle": row["bundle"]})
		if not row["bonus"].is_empty():
			rows.append({"name": text("reward.clear") + " ★", "bundle": row["bonus"]})
		if objectives.is_empty():
			for objective: Dictionary in row["objectives"]:
				objectives.append({"name": text(String(objective["name_key"]), CONDITIONS.label_values(objective["condition"])), "met": bool(objective["met"])})
	var track: Dictionary = LEVELS.state(ledger, catalog, "account")
	var view := {
		"title": text("ui.stage_clear"),
		"subtitle": text("ui.arena"),
		"objectives": objectives,
		"record_line": text("ui.record", {"seconds": "%.0f" % float(measurements.get("fight_s", 0.0)), "hits": str(int(measurements.get("hits_taken", 0)))}),
		"rows": rows,
		"track": track,
		"exp_to_leave": func(level: int) -> int: return catalog.exp_to_leave("account", level),
	}
	set_meta("pending_trigger", trigger)
	set_meta("pending_measurements", measurements)
	screen.open(view, catalog, Callable(self, "text"))
	return seen


func _on_claim() -> void:
	if popup.is_open() or not _pending_exp.is_empty():
		return
	var outcome: Dictionary = SOURCES.claim(ledger, catalog, String(get_meta("pending_trigger", "")), get_meta("pending_measurements", {}), now(), Callable(self, "draw"))
	if not outcome["errors"].is_empty():
		_note("; ".join(outcome["errors"]))
		return
	_save()
	screen.set_claiming(true)
	_pending_exp = outcome["exp"][0] if not outcome["exp"].is_empty() else {"none": true}
	popup.closed.connect(func() -> void:
		screen.show_result({} if _pending_exp.has("none") else _pending_exp)
		_pending_exp = {}
		_refresh(), CONNECT_ONE_SHOT)
	popup.open(outcome["granted"], catalog, Callable(self, "text"), {}, outcome["lost"])


func login() -> Dictionary:
	## The daily gift claims straight into the popup; a second login inside the period says why not.
	var outcome: Dictionary = SOURCES.claim(ledger, catalog, "login", {}, now(), Callable(self, "draw"))
	if not outcome["errors"].is_empty():
		_note("; ".join(outcome["errors"]))
	elif outcome["claimed"].is_empty():
		_note(text("ui.nothing_to_claim", {"reason": String(outcome["rows"][0]["reason"])}))
	else:
		_save()
		popup.open(outcome["granted"], catalog, Callable(self, "text"), {}, outcome["lost"])
	_refresh()
	return outcome


func buy() -> Dictionary:
	## The shop: spend, all or nothing.
	var outcome: Dictionary = LEDGER.spend(ledger, catalog, POTION_PRICE, "shop:potion", now())
	if not outcome["errors"].is_empty():
		_note("; ".join(outcome["errors"]))
	elif not outcome["shortfall"].is_empty():
		var parts: Array[String] = []
		for entry: Dictionary in outcome["shortfall"]:
			parts.append("%s ×%d" % [text(String(catalog.item(String(entry["item"]))["name_key"])), int(entry["count"])])
		_note(text("ui.short", {"items": ", ".join(parts)}))
	else:
		LEDGER.grant(ledger, catalog, [{"item": "potion", "count": 1}], "shop:potion", now())
		_save()
		_note(text("ui.bought"))
	_refresh()
	return outcome


func open_mailbox() -> void:
	if MAILBOX.prune_expired(ledger, now()) > 0:
		_save()
	mailbox_ui.open(catalog, Callable(self, "text"), now(), MAILBOX.inbox(ledger, now()))


func _on_mail_claim(id: int) -> void:
	var outcome: Dictionary = MAILBOX.claim(ledger, catalog, id, now())
	if not outcome["errors"].is_empty():
		_note("; ".join(outcome["errors"]))
		return
	_save()
	mailbox_ui.refresh(MAILBOX.inbox(ledger, now()), id)
	popup.open(outcome["granted"], catalog, Callable(self, "text"), {}, outcome["lost"])
	_refresh()


func _on_mail_claim_all() -> void:
	var outcome: Dictionary = MAILBOX.claim_all(ledger, catalog, now())
	if outcome["claimed_ids"].is_empty():
		return
	_save()
	mailbox_ui.refresh(MAILBOX.inbox(ledger, now()), -1)
	popup.open(outcome["granted"], catalog, Callable(self, "text"), {}, outcome["lost"])
	_refresh()


func reset() -> void:
	ledger = LEDGER.create(now())
	MAILBOX.deliver_once(ledger, catalog, "welcome", now())
	_save()
	_refresh()


func _save() -> void:
	for e in STORE.save_document(ledger_path, ledger):
		printerr("fake_game: " + e)


func _note(line: String) -> void:
	status = line
	if _status_label != null:
		_status_label.text = line


# --- the example's own chrome ------------------------------------------------------------------------------

func _build_ui() -> void:
	var back := ColorRect.new()
	back.color = Color(0.10, 0.09, 0.11)
	back.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	back.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(back)
	var column := VBoxContainer.new()
	column.position = Vector2(32, 32)
	column.add_theme_constant_override("separation", 10)
	add_child(column)
	for pair in [["ui.win_fast", func() -> void: win("fast")], ["ui.win_slow", func() -> void: win("slow")], ["ui.login", login], ["ui.buy", buy], ["ui.mailbox", open_mailbox], ["ui.reset", reset]]:
		var b := Button.new()
		b.text = text(pair[0])
		b.custom_minimum_size = Vector2(320, 40)
		b.pressed.connect(pair[1])
		column.add_child(b)
	_balances_label = Label.new()
	_balances_label.position = Vector2(400, 32)
	_balances_label.add_theme_font_size_override("font_size", 16)
	add_child(_balances_label)
	_status_label = Label.new()
	_status_label.position = Vector2(32, 360)
	_status_label.add_theme_font_size_override("font_size", 14)
	_status_label.modulate = Color(0.9, 0.85, 0.7)
	add_child(_status_label)
	var layer := CanvasLayer.new()
	layer.layer = 5
	add_child(layer)
	mail_button = MAIL_BUTTON.new()
	mail_button.pressed.connect(open_mailbox)
	layer.add_child(mail_button)
	mail_button.place(get_viewport().get_visible_rect().size)
	get_viewport().size_changed.connect(func() -> void: mail_button.place(get_viewport().get_visible_rect().size))


func _refresh() -> void:
	if _balances_label == null:
		return
	var lines: Array[String] = [text("ui.balances")]
	for id: String in catalog.items:
		lines.append("  %s: %d" % [text(String(catalog.item(id)["name_key"])), LEDGER.balance(ledger, id)])
	var track: Dictionary = LEVELS.state(ledger, catalog, "account")
	lines.append(text("ui.track", {"level": str(track["level"]), "exp": str(track["exp"]), "to_next": str(track["to_next"])}))
	lines.append(text("ui.saved", {"path": ledger_path}))
	_balances_label.text = "\n".join(lines)
	mail_button.unread = MAILBOX.unread_count(ledger, now())
