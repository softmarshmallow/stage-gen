extends SceneTree
## Drives the fake game end to end from the package project: a fast clean win opens the result screen
## with three objectives met, Claim grants the clear, the drop, the bonus and the first clear and sends
## the first-clear mail, the popup shows it, Continue closes the screen; a slow win claims only the
## repeat; the daily gift claims once per day; the shop spends or names the shortfall; the mailbox
## claims all. With `--capture <dir>` (native renderer only) every screen is rendered to PNG.
##   godot --headless --path godot/packages/progression --script res://tests/run_example_checks.gd

var _fails: Array[String] = []
var _checks := 0
var _capture_root := ""
var _game: Control


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	root.size = Vector2i(1280, 800)
	var options := OS.get_cmdline_user_args()
	var ci := options.find("--capture")
	if ci >= 0 and ci + 1 < options.size():
		if DisplayServer.get_name() == "headless":
			push_error("Example captures require the native renderer.")
			quit(1)
			return
		_capture_root = options[ci + 1]
		DirAccess.make_dir_recursive_absolute(_capture_root)
	var ledger_dir := OS.get_temp_dir().path_join("progression-example-%d" % Time.get_ticks_usec())
	var scene: PackedScene = load("res://examples/fake_game/main.tscn")
	_game = scene.instantiate()
	_game.ledger_path = ledger_dir.path_join("ledger.json")
	root.add_child(_game)
	await process_frame
	_check(_game.errors.is_empty(), "the fake game configured its design: " + "; ".join(_game.errors))
	if not _game.errors.is_empty():
		_end()
		return
	_check(_game.ledger["mail"].size() == 1 and _game.mail_button.unread == 1, "a fresh ledger has the welcome mail and the badge shows it")
	# a fast, clean win
	var seen: Dictionary = _game.win("fast")
	_check(seen["errors"].is_empty() and _game.screen.is_open(), "the fast win opens the result screen")
	_check(_game.screen._stars.size() == 3 and _game.screen._rows.size() == 3, "three objectives and three reward rows (clear, bonus, first clear)")
	await _real(1.2)
	await _capture("result")
	_game.screen.claim_pressed.emit()
	await process_frame
	var doc: Dictionary = _game.ledger
	_check(_game.popup.is_open(), "Claim opened the popup")
	_check(doc["balances"].get("gold", 0) == 150 and doc["balances"].get("core", 0) >= 1 and doc["balances"].get("gem", 0) >= 60 and doc["balances"].get("charm", 0) == 1, "the clear, the first clear, the bonus and a drop landed: " + str(doc["balances"]))
	_check(doc["tracks"]["account"]["level"] == 2 and doc["tracks"]["account"]["exp"] == 20, "120 EXP made level 2 with 20")
	_check(doc["mail"].size() == 2 and doc["records"]["arena.first"]["claims"] == 1 and doc["records"]["arena.clear"]["best_met"] == 3, "the first-clear mail arrived and the records are written")
	var saved: Variant = JSON.parse_string(FileAccess.get_file_as_string(_game.ledger_path))
	_check(saved is Dictionary and saved.get("tracks", {}).get("account", {}).get("level", 0) == 2, "the ledger was saved through the store")
	await _real(1.0)
	await _capture("obtained")
	_game.popup.close()
	await process_frame
	_check(_game.screen._continue.visible and _game.screen._exit.visible and not _game.screen._claim.visible, "after the popup the buttons are Continue and Exit")
	await _real(1.5)
	await _capture("result_after")
	_game.screen.continue_pressed.emit()
	await process_frame
	_check(not _game.screen.is_open(), "Continue closes the screen")
	# a slow win: only the repeat source
	seen = _game.win("slow")
	var claimable: Array = seen["rows"].filter(func(r: Dictionary) -> bool: return bool(r["claimable"]))
	_check(claimable.size() == 1 and claimable[0]["id"] == "arena.clear" and claimable[0]["objectives_met"] == 1, "a slow win with six hits previews only the repeat source with one objective met")
	_game.screen.claim_pressed.emit()
	await process_frame
	_check(_game.ledger["balances"]["gold"] == 300 and _game.ledger["balances"].get("charm", 0) == 1, "the repeat paid its gold and no second bonus")
	_game.popup.close()
	await process_frame
	_game.screen.continue_pressed.emit()
	# the daily gift
	var outcome: Dictionary = _game.login()
	_check(outcome["claimed"] == ["daily_gift"] and _game.ledger["balances"]["gold"] == 350 and _game.popup.is_open(), "the first login claims the daily gift")
	_game.popup.close()
	outcome = _game.login()
	_check(outcome["claimed"].is_empty() and _game.status.contains("period_not_elapsed"), "a second login says the period has not elapsed")
	_game.clock_offset = 86400
	outcome = _game.login()
	_check(outcome["claimed"] == ["daily_gift"] and _game.ledger["balances"]["gold"] == 400, "a day later it claims again")
	_game.popup.close()
	# the shop
	outcome = _game.buy()
	_check(outcome["shortfall"].is_empty() and _game.ledger["balances"]["gold"] == 350 and _game.ledger["balances"]["potion"] == 1, "buying a potion spends 50 gold")
	for i in 7:
		_game.buy()
	_check(_game.ledger["balances"]["gold"] == 0 and _game.ledger["balances"]["potion"] == 8, "seven more potions empty the gold")
	outcome = _game.buy()
	_check(outcome["shortfall"] == [{"item": "gold", "count": 50}] and _game.ledger["balances"]["potion"] == 8, "an eighth is refused with the shortfall named")
	# the mailbox
	_check(_game.mail_button.unread == 2, "two mails wait: the welcome and the first clear")
	_game.open_mailbox()
	await process_frame
	_check(_game.mailbox_ui.is_open() and _game.mailbox_ui._rows.size() == 2, "the mailbox lists both")
	await _real(0.8)
	await _capture("mailbox")
	_game.mailbox_ui.claim_all_requested.emit()
	await process_frame
	_check(_game.ledger["balances"]["gold"] == 500 and _game.ledger["balances"]["gem"] >= 100 and _game.mail_button.unread == 0 and _game.popup.is_open(), "Claim all landed the gold and the gems and emptied the badge")
	await _real(1.0)
	await _capture("mail_claimed")
	_game.popup.close()
	_game.mailbox_ui.close()
	await process_frame
	_check(not _game.mailbox_ui.is_open(), "the mailbox closes")
	for name in DirAccess.get_files_at(ledger_dir):
		DirAccess.remove_absolute(ledger_dir.path_join(name))
	DirAccess.remove_absolute(ledger_dir)
	_end()


func _capture(name: String) -> void:
	if _capture_root == "":
		return
	await process_frame
	await process_frame
	RenderingServer.force_draw()   # an unfocused window may have stopped drawing; render this frame regardless
	var image := root.get_texture().get_image()
	image.save_png(_capture_root.path_join("fake_game-%s.png" % name))


func _real(seconds: float) -> void:
	await create_timer(seconds, true, false, true).timeout


func _check(ok: bool, what: String) -> void:
	_checks += 1
	if not ok:
		_fails.append(what)
		printerr("FAIL progression example: " + what)


func _end() -> void:
	if _fails.is_empty():
		print("progression_example: %d checks passed" % _checks)
	quit(0 if _fails.is_empty() else 1)
