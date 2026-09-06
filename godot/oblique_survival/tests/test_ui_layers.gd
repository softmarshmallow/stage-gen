extends RefCounted

## The 2D layers, headless: the kit's readings of the world, the death sheet
## showing on `dead` with the cause's headline, the craft panel following
## `craft_open` and writing the sim's one-shot inputs, the HUD building a slot
## per pack slot and its card for the chosen one, and every layer taking a
## scale. Nothing is drawn; a Control tree stands up under the dummy display
## server, which is enough to prove the layers build and read.


func run(h: TestHarness) -> void:
	var w := SimFixture.world()
	if w == null:
		h.fail("test_ui_layers: could not open %s" % TestHarness.RUN_DIR)
		return
	_kit_reads_items(h, w)
	_kit_names_a_death(h)
	_death_screen_follows_dead(h, w)
	_craft_panel_follows_craft_open(h, w)
	_hud_builds_the_pack(h, w)
	_hud_flies_a_pickup(h, w)
	_pause_menu_shows_the_help(h, w)
	_hurt_flash_bleeds_with_health(h, w)
	_warmth_veil_frosts_and_heats(h, w)
	_map_fills_the_window(h, w)
	_layers_take_a_scale(h, w)
	_args_carry_the_new_flags(h)


func _kit_reads_items(h: TestHarness, w: World) -> void:
	var m: Dictionary = w.manifest
	h.assert_eq(UiKit.item_name(m, "axe"), "Flint axe", "the display name")
	h.assert_eq(UiKit.item_name(m, "no_such_thing"), "no such thing", "an unknown id opens its underscores")
	h.assert_eq(UiKit.use_verb(UiKit.item_spec(m, "berry")), "eat", "berries are eaten")
	h.assert_eq(UiKit.use_verb(UiKit.item_spec(m, "poultice")), "apply", "a poultice is applied")
	h.assert_eq(UiKit.use_verb(UiKit.item_spec(m, "torch")), "light", "a torch is lit")
	h.assert_eq(UiKit.use_verb(UiKit.item_spec(m, "warm_stone")), "warm", "a stone is warmed")
	h.assert_eq(UiKit.use_verb(UiKit.item_spec(m, "axe")), "wear", "a tool is worn in the hand")
	h.assert_eq(UiKit.use_verb(UiKit.item_spec(m, "grass_cloak")), "wear", "a cloak is worn on the body")
	h.assert_eq(UiKit.use_verb(UiKit.item_spec(m, "backpack")), "wear", "a pack is worn on the back")
	h.assert_eq(UiKit.use_verb(UiKit.item_spec(m, "log")), "", "a material has no use button")
	h.assert_eq(UiKit.equip_kind(UiKit.item_spec(m, "axe")), "hand", "the axe's place")
	h.assert_eq(UiKit.equip_kind(UiKit.item_spec(m, "grass_cloak")), "body", "the cloak's place")
	h.assert_eq(UiKit.equip_kind(UiKit.item_spec(m, "backpack")), "back", "the pack's place")
	h.assert_eq(UiKit.equip_kind(UiKit.item_spec(m, "berry")), "", "berries are not worn")
	h.assert_eq(UiKit.use_hint(UiKit.item_spec(m, "axe"), {"item": "axe", "count": 1, "uses": 7}),
		"chops · 7 uses left", "a tool's hint counts its uses")
	h.assert_eq(UiKit.use_hint(UiKit.item_spec(m, "cooked_berry"), null),
		"+45 hunger · +10 warmth", "a food's hint lists what it gives")
	h.assert_eq(UiKit.use_hint(UiKit.item_spec(m, "log"), null), "a material", "a log is a material")
	h.assert_eq(UiKit.inv_count([{"item": "log", "count": 3}, null, {"item": "log", "count": 2}], "log"), 5,
		"the pack's count sums the stacks")
	h.assert_eq(UiKit.slot_capacity(m, {"back": {"item": "backpack", "count": 1, "uses": null}}, 12), 16,
		"a pack worn on the back adds its slots")
	h.assert_eq(UiKit.slot_capacity(m, {"back": null}, 12), 12, "nothing on the back adds none")
	h.assert_eq(UiKit.clock_text(125.0), "2:05", "the clock text")


func _kit_names_a_death(h: TestHarness) -> void:
	h.assert_eq(UiKit.death_headline("cold"), "You froze.", "the cold's headline")
	h.assert_eq(UiKit.death_headline("hunger"), "You starved.", "the hunger's headline")
	h.assert_eq(UiKit.death_headline("hurt"), "You did not last.", "the hound's headline")
	h.assert_eq(UiKit.death_headline(""), "You did not last.", "an unknown cause still has one")


func _death_screen_follows_dead(h: TestHarness, w: World) -> void:
	var screen := DeathScreen.new()
	screen.setup(SimFixture.package(), w, null)
	h.assert_false(screen.visible, "the sheet is down while the player lives")
	screen.handle_event({"type": "death", "cause": "cold"})
	w.dead = true
	screen.update(w, 0.0, {})
	h.assert_true(screen.visible, "and up once the world says dead")
	h.assert_eq(screen.cause, "cold", "with the event's cause")
	var count := [0]
	screen.restart_requested.connect(func() -> void: count[0] += 1)
	screen._on_begin_again()
	h.assert_eq(count[0], 1, "the button asks for a restart")
	w.dead = false
	screen.update(w, 0.0, {})
	h.assert_false(screen.visible, "a living world takes the sheet down")
	screen.free()


func _craft_panel_follows_craft_open(h: TestHarness, w: World) -> void:
	SimFixture.bare(w)
	w.craft_open = false
	w.dead = false
	var panel := CraftPanel.new()
	panel.setup(SimFixture.package(), w, null)
	h.assert_false(panel.visible, "the table is closed")
	w.craft_open = true
	panel.update(w, 0.0, {})
	h.assert_true(panel.visible, "and open with the world's flag")
	var recipes: Array = (w.manifest["crafting"] as Dictionary)["recipes"]
	h.assert_eq(panel._rows.get_child_count(), recipes.size(), "one row per recipe")
	panel._on_craft()
	h.assert_true(bool(w.input["menu_confirm"]), "the Craft button is the sim's confirm")
	panel._on_close()
	h.assert_true(bool(w.input["craft_toggle"]), "the close button is the sim's toggle")
	SimFixture.release(w)
	var click := InputEventMouseButton.new()
	click.button_index = MOUSE_BUTTON_LEFT
	click.pressed = true
	panel._on_row_input(click, 3)
	h.assert_eq(w.input["menu_select"], 3, "a clicked row is the sim's select")
	h.assert_false(bool(w.input["menu_confirm"]), "one click does not make")
	panel._on_row_input(click, 3)
	h.assert_true(bool(w.input["menu_confirm"]), "the second click on the same row makes")
	SimFixture.release(w)
	w.craft_open = false
	panel.update(w, 0.0, {})
	h.assert_false(panel.visible, "closed again")
	panel.free()


func _hud_builds_the_pack(h: TestHarness, w: World) -> void:
	SimFixture.bare(w)
	w.dead = false
	w.craft_open = false
	Inventory.inv_add(w, "berry", 3)
	Inventory.inv_add(w, "axe", 1)
	w.selected = 0
	var hud := Hud.new()
	hud.setup(SimFixture.package(), w, null)
	h.assert_eq(hud._slot_cells.size(), 12, "a slot per pack slot")
	h.assert_eq(hud._equip_cells.size(), 3, "and a cell per worn place")
	h.assert_false(hud._card_panel.visible, "no slot hovered, no card")
	# The card follows the hovered slot, not the selection.
	hud._on_slot_hover(0, true)
	hud.update(w, 0.0, {})
	h.assert_true(hud._card_panel.visible, "a hovered slot raises its card")
	h.assert_eq(hud._card_name.text, "Berries ×3", "the card names the hovered stack")
	h.assert_false(hud._use_button.disabled, "berries can be used")
	h.assert_eq(hud._use_button.text, "Eat", "and the button says how")
	hud._on_slot_hover(0, false)
	hud._on_slot_hover(1, true)
	hud.update(w, 0.0, {})
	h.assert_eq(hud._card_name.text, "Flint axe", "the card follows the hover")
	h.assert_false(hud._use_button.disabled, "a tool is worn")
	h.assert_eq(hud._use_button.text, "Wear", "and the button says so")
	h.assert_false(hud._drop_button.disabled, "and can be dropped")
	hud._on_use()
	h.assert_eq(w.input["select"], 1, "the card's Use selects its slot")
	h.assert_true(bool(w.input["use"]), "and uses it")
	SimFixture.release(w)
	hud._on_drop()
	h.assert_eq(w.input["select"], 1, "the card's Drop selects its slot")
	h.assert_true(bool(w.input["drop"]), "and drops it")
	SimFixture.release(w)
	hud._on_slot_hover(1, false)
	hud._on_slot_hover(5, true)
	hud.update(w, 0.0, {})
	h.assert_true(hud._drop_button.disabled, "an empty slot drops nothing")
	hud._on_slot_hover(5, false)
	hud.update(w, 0.0, {})
	h.assert_false(hud._card_panel.visible, "the card goes with the hover (no linger at delta 0)")
	# The worn places: the axe on, the hand's card, its Take off.
	Inventory.equip(w, 1)
	hud._on_equip_hover("hand", true)
	hud.update(w, 0.0, {})
	h.assert_true(hud._card_panel.visible, "a hovered worn place raises its card")
	h.assert_eq(hud._card_name.text, "Flint axe", "naming the worn axe")
	h.assert_eq(hud._use_button.text, "Take off", "with Take off")
	h.assert_false(hud._drop_button.visible, "and no Drop")
	hud._on_use()
	h.assert_eq(w.input["unequip"], "hand", "Take off is the sim's unequip")
	SimFixture.release(w)
	var click := InputEventMouseButton.new()
	click.button_index = MOUSE_BUTTON_LEFT
	click.pressed = true
	hud._on_equip_input(click, "hand")
	h.assert_eq(w.input["unequip"], "hand", "a click on the worn thing takes it off")
	SimFixture.release(w)
	hud._on_equip_hover("hand", false)
	hud._on_equip_hover("body", true)
	hud.update(w, 0.0, {})
	h.assert_eq(hud._card_name.text, "body · nothing worn", "an empty worn place says so")
	hud._on_equip_hover("body", false)
	# A pack worn grows the hotbar.
	Inventory.inv_add(w, "backpack", 1)
	hud.update(w, 0.0, {})
	h.assert_eq(hud._slot_cells.size(), 12, "a pack in a slot grows nothing")
	var pack_slot := -1
	for index in w.slots.size():
		if w.slots[index] != null and str((w.slots[index] as Dictionary)["item"]) == "backpack":
			pack_slot = index
	Inventory.equip(w, pack_slot)
	hud.update(w, 0.0, {})
	h.assert_eq(hud._slot_cells.size(), 16, "a pack worn on the back grows the hotbar")
	click.button_index = MOUSE_BUTTON_RIGHT
	hud._on_slot_input(click, 0)
	h.assert_eq(w.input["select"], 0, "a right-click selects the slot")
	h.assert_true(bool(w.input["use"]), "and uses it")
	SimFixture.release(w)
	hud._on_craft_button()
	h.assert_true(bool(w.input["craft_toggle"]), "the Craft button is the sim's toggle")
	SimFixture.release(w)
	var asked: Array = []
	hud.action.connect(func(name: String) -> void: asked.append(name))
	hud._on_map_button()
	hud._on_menu_button()
	h.assert_eq(asked, ["map", "menu"], "Map and Menu ask the frame owner")
	# The hover names the thing under the pointer, above the thing, in an
	# outlined label with no panel behind it.
	var pine := SimFixture.prop(w, "p2", "pine", "grown", 0.0, 1.0)
	w.entities.append(pine)
	hud.set_hover({"entity": pine, "target": Targeting.target_for(w, pine), "point": null}, Vector2(800.0, 300.0))
	hud.update(w, 0.0, {})
	h.assert_true(hud._hover_label.visible, "a hovered pine shows its name")
	h.assert_true(hud._hover_label.text.find("chop") >= 0, "naming the chop (%s)" % hud._hover_label.text)
	h.assert_true(hud._hover_label.get_theme_constant("outline_size") >= 3, "outlined")
	h.assert_true(hud._hover_label.get_parent() == hud._root, "with no panel behind it")
	var centre := hud._hover_label.position.x + hud._hover_label.size.x * 0.5
	h.assert_near(centre, 800.0, 1.0, "centred on the anchor")
	h.assert_true(hud._hover_label.position.y + hud._hover_label.size.y < 300.0, "and standing above it")
	hud.set_hover({})
	hud.update(w, 0.0, {})
	h.assert_false(hud._hover_label.visible, "and none off the world")
	# The key's target is named the same way, with what the key would do, and
	# the hover label yields to it when they are the same thing.
	var target: Variant = Targeting.target_for(w, pine)
	hud.set_focus(target, Vector2(640.0, 420.0))
	hud.update(w, 0.0, {})
	h.assert_true(hud._focus_label.visible, "the thing in reach is named")
	h.assert_true(hud._focus_label.text.find("chop") >= 0, "with the verb (%s)" % hud._focus_label.text)
	h.assert_true(hud._focus_label.position.y + hud._focus_label.size.y < 420.0, "above its anchor")
	hud.set_hover({"entity": pine, "target": target, "point": null}, Vector2(640.0, 420.0))
	hud.update(w, 0.0, {})
	h.assert_false(hud._hover_label.visible, "the hover says nothing twice")
	h.assert_false("prompt" in hud, "and there is no prompt strip any more")
	hud.set_focus(null)
	hud.set_hover({})
	hud.update(w, 0.0, {})
	h.assert_false(hud._focus_label.visible, "no target, no label")
	w.dead = true
	hud.update(w, 0.0, {})
	h.assert_false(hud._hotbar_panel.visible, "the dead have no hotbar")
	h.assert_false(hud._equip_panel.visible, "nor worn places")
	w.dead = false
	hud.free()


func _hud_flies_a_pickup(h: TestHarness, w: World) -> void:
	SimFixture.bare(w)
	w.dead = false
	w.craft_open = false
	Inventory.inv_add(w, "twig", 2)
	var hud := Hud.new()
	hud.setup(SimFixture.package(), w, null)
	# A pickup with a place in the world flies from it; the projector is the
	# frame owner's, here a fixed point.
	hud.set_projector(func(_point: Vector3) -> Vector2: return Vector2(400.0, 200.0))
	hud.handle_event({"type": "pickup", "item": "twig", "x": 1.0, "z": 1.0})
	h.assert_eq(hud.flights_in_air(), 1, "the pickup is in flight")
	hud.update(w, 0.25, {})
	h.assert_eq(hud.flights_in_air(), 1, "still in the air half way")
	hud.update(w, 0.3, {})
	h.assert_eq(hud.flights_in_air(), 0, "and landed after its half second")
	h.assert_true(float((hud._slot_cells[0] as Control).get("flash")) > 0.0, "the slot glows where it landed")
	# A drop leaving the pack does not fly in; nor does a thing behind the camera.
	hud.handle_event({"type": "pickup", "item": "twig", "x": 1.0, "z": 1.0, "out": true})
	h.assert_eq(hud.flights_in_air(), 0, "a drop flies nowhere")
	hud.set_projector(func(_point: Vector3) -> Vector2: return Vector2(-1.0, -1.0))
	hud.handle_event({"type": "pickup", "item": "twig", "x": 1.0, "z": 1.0})
	h.assert_eq(hud.flights_in_air(), 0, "a thing off the screen does not fly")
	hud.free()


func _pause_menu_shows_the_help(h: TestHarness, w: World) -> void:
	var menu := PauseMenu.new()
	menu.setup(SimFixture.package(), w, null)
	h.assert_false(menu.visible, "the menu is down")
	menu.set_open(true)
	h.assert_true(menu.visible, "and up when opened")
	h.assert_eq(menu.page, "menu", "on the menu page")
	menu.show_page("help")
	h.assert_eq(menu.page, "help", "How to play is the second page")
	h.assert_true(menu._help.visible and not menu._menu.visible, "and it is what shows")
	menu.set_open(false)
	menu.set_open(true)
	h.assert_eq(menu.page, "menu", "opening again lands on the menu")
	var asked: Array = []
	menu.action.connect(func(name: String) -> void: asked.append(name))
	menu._on_button("resume")
	menu._on_button("reset")
	menu._on_button("help")
	h.assert_eq(asked, ["resume", "reset"], "the buttons ask the frame owner; help is the menu's own page")
	# The help names the keys the frame owner binds.
	var text := ""
	for section in PauseMenu.help_sections():
		text += str(section[0]) + " " + str(section[1]) + "\n"
	for key in ["Esc", "WASD", "Space", "C", "M", "R", "F11", "hand", "body", "back"]:
		h.assert_true(text.find(" %s " % key) >= 0, "the help names %s" % key)
	h.assert_true(text.find("hold the") >= 0, "and the held-button walk")
	w.dead = true
	menu.update(w, 0.0, {})
	h.assert_eq(asked.back(), "resume", "a death while paused asks to resume")
	w.dead = false
	menu.free()


## The screen bleeds when health does: a bite floods and fades, a drain
## throbs while it lasts and lets go after, a held health shows nothing, and
## the dead are left to the death sheet.
func _hurt_flash_bleeds_with_health(h: TestHarness, w: World) -> void:
	var flash := HurtFlash.new()
	flash.setup(SimFixture.package(), w, null)
	h.assert_eq(flash.layer, 21, "above the vignette (20), under the HUD (30)")
	flash.update(w, 1.0 / 60.0, {})
	h.assert_near(flash.flash(), 0.0, 1e-6, "nothing at full health")
	h.assert_near(flash.throb(), 0.0, 1e-6, "and no throb")
	# The hound's bite: the sim's `hurt` event and a 10-point drop the same tick.
	w.player.health -= 10.0
	flash.handle_event({"type": "hurt", "x": 0.0, "z": 0.0})
	flash.update(w, 1.0 / 60.0, {})
	h.assert_true(flash.flash() > 0.9, "a bite floods the edges (%.2f)" % flash.flash())
	h.assert_near(flash.throb(), 0.0, 1e-6, "a bite is not a drain")
	for i in 60:
		flash.update(w, 1.0 / 60.0, {})
	h.assert_near(flash.flash(), 0.0, 1e-6, "and has faded a second later")
	# A drop the sim never named: a chunk still flashes, so a cause added later shows.
	w.player.health -= 5.0
	flash.update(w, 1.0 / 60.0, {})
	h.assert_true(flash.flash() > 0.9, "an unnamed chunk flashes too")
	# The drain: health going a little every frame, as the empty belly takes it.
	var before := flash.throb()
	for i in 60:
		w.player.health -= 2.0 / 60.0
		flash.update(w, 1.0 / 60.0, {})
	h.assert_true(flash.throb() > 0.9, "a second of drain raises the throb (%.2f)" % flash.throb())
	h.assert_true(flash.throb() > before, "from nothing")
	var rect := flash.rect as ColorRect
	var throb_alpha := float((rect.material as ShaderMaterial).get_shader_parameter("u_throb"))
	h.assert_true(throb_alpha > 0.2, "and the shader is handed it (%.2f)" % throb_alpha)
	for i in 120:
		flash.update(w, 1.0 / 60.0, {})
	h.assert_near(flash.throb(), 0.0, 1e-6, "two seconds of held health lets it go")
	# Healing is not hurt.
	w.player.health += 30.0
	flash.update(w, 1.0 / 60.0, {})
	h.assert_near(flash.flash(), 0.0, 1e-6, "eating shows nothing")
	# The dead bleed no more; the sheet has them.
	w.dead = true
	w.player.health -= 1.0 / 60.0
	flash.update(w, 1.0 / 60.0, {})
	h.assert_near(flash.throb(), 0.0, 1e-6, "no throb once dead")
	w.dead = false
	w.player.health = 100.0
	flash.free()


## The frost creeps in under 35 % warmth and is whole at none; the heat rises
## while `world.hot` holds and lets go after; a warm player in the open shows
## nothing; the dead show nothing.
func _warmth_veil_frosts_and_heats(h: TestHarness, w: World) -> void:
	var veil := WarmthVeil.new()
	veil.setup(SimFixture.package(), w, null)
	h.assert_eq(veil.layer, 22, "above the hurt flash (21), under the HUD (30)")
	w.player.warmth = 100.0
	w.hot = false
	for i in 60:
		veil.update(w, 1.0 / 60.0, {})
	h.assert_near(veil.cold(), 0.0, 1e-6, "a warm player in the open: no frost")
	h.assert_near(veil.hot(), 0.0, 1e-6, "and no heat")
	w.player.warmth = 40.0
	for i in 60:
		veil.update(w, 1.0 / 60.0, {})
	h.assert_near(veil.cold(), 0.0, 1e-6, "40 warmth is above the onset")
	w.player.warmth = 17.5
	for i in 120:
		veil.update(w, 1.0 / 60.0, {})
	h.assert_near(veil.cold(), 0.5, 0.02, "17.5 of 100 is half way to none: half the frost")
	w.player.warmth = 0.0
	for i in 120:
		veil.update(w, 1.0 / 60.0, {})
	h.assert_near(veil.cold(), 1.0, 1e-6, "no warmth is the whole frost")
	var rect := veil.rect as ColorRect
	var cold_alpha := float((rect.material as ShaderMaterial).get_shader_parameter("u_cold"))
	h.assert_true(cold_alpha > 0.5, "and the shader is handed it (%.2f)" % cold_alpha)
	w.player.warmth = 100.0
	veil.update(w, 1.0 / 60.0, {})
	h.assert_true(veil.cold() < 1.0 and veil.cold() > 0.9, "a bar refilled thaws over time, not at once (%.2f)" % veil.cold())
	for i in 120:
		veil.update(w, 1.0 / 60.0, {})
	h.assert_near(veil.cold(), 0.0, 1e-6, "and is clear two seconds later")
	w.hot = true
	for i in 30:
		veil.update(w, 1.0 / 60.0, {})
	h.assert_near(veil.hot(), 0.25, 0.02, "half a second at the fire is a quarter of the heat")
	for i in 120:
		veil.update(w, 1.0 / 60.0, {})
	h.assert_near(veil.hot(), 1.0, 1e-6, "two seconds is all of it")
	w.hot = false
	for i in 120:
		veil.update(w, 1.0 / 60.0, {})
	h.assert_near(veil.hot(), 0.0, 1e-6, "a step back cools in a second and a half")
	w.player.warmth = 0.0
	w.hot = true
	w.dead = true
	for i in 120:
		veil.update(w, 1.0 / 60.0, {})
	h.assert_near(veil.cold(), 0.0, 1e-6, "the dead are not cold")
	h.assert_near(veil.hot(), 0.0, 1e-6, "nor hot")
	w.dead = false
	w.hot = false
	w.player.warmth = 100.0
	veil.free()


## The map is the whole window: a scrim over it that takes the mouse, the map
## square as tall as the window less its margins, the column beside it, and a
## click on the scrim closing it.
func _map_fills_the_window(h: TestHarness, w: World) -> void:
	var map := WorldMap.new()
	map.setup(SimFixture.package(), w, null)
	h.assert_false(map.visible, "closed to begin with")
	map.set_open(true)
	map.update(w, 0.0, {"yaw": 0.0})
	h.assert_true(map.visible, "open shows it")
	var root: Control = map._root
	var scrim: ColorRect = map._scrim
	h.assert_eq(scrim.size, root.size, "the scrim covers the window")
	h.assert_eq(scrim.mouse_filter, Control.MOUSE_FILTER_STOP, "and takes the mouse, so no click walks")
	var frame: Control = map._frame
	var expected_side: float = root.size.y - 2.0 * WorldMap.MARGIN
	h.assert_near(frame.size.x, expected_side, 0.5, "the map is as tall as the window allows")
	h.assert_near(frame.size.y, frame.size.x, 0.5, "and square")
	h.assert_near(frame.position.y, WorldMap.MARGIN, 0.5, "from the top margin")
	var column: Control = map._column
	h.assert_near(column.position.x, frame.position.x + frame.size.x + WorldMap.GAP, 0.5, "the column stands beside it")
	h.assert_true(column.position.x + column.size.x <= root.size.x, "inside the window")
	h.assert_true(frame.position.x >= 0.0, "as is the map")
	var legend: VBoxContainer = map._legend
	h.assert_true(legend.get_child_count() >= 4, "the legend names the biomes, the road and the water (%d)" % legend.get_child_count())
	var click := InputEventMouseButton.new()
	click.button_index = MOUSE_BUTTON_LEFT
	click.pressed = true
	map._on_scrim_input(click)
	h.assert_false(map.open, "a click on the scrim closes it")
	h.assert_false(map.visible, "and hides it")
	# A wider window: the height still rules the square.
	map.set_open(true)
	root.size = Vector2(2560.0, 1440.0)
	map.update(w, 0.0, {"yaw": 0.0})
	h.assert_near(map._frame.size.x, 1440.0 - 2.0 * WorldMap.MARGIN, 0.5, "in a 2560x1440 window the height rules")
	# A narrow one: the width, less the column, rules.
	root.size = Vector2(900.0, 900.0)
	map.update(w, 0.0, {"yaw": 0.0})
	h.assert_near(map._frame.size.x, 900.0 - 2.0 * WorldMap.MARGIN - WorldMap.COLUMN_WIDTH - WorldMap.GAP, 0.5,
		"in a square window the width less the column rules")
	map.free()


func _layers_take_a_scale(h: TestHarness, w: World) -> void:
	for layer in [Hud.new(), CraftPanel.new(), DeathScreen.new(), WorldMap.new(), PauseMenu.new()]:
		layer.setup(SimFixture.package(), w, null)
		layer.set_ui_scale(2.0)
		h.assert_near(layer.transform.get_scale().x, 2.0, 1e-6, "%s scales as a whole" % layer.get_class())
		layer.set_ui_scale(1.0)
		h.assert_near(layer.transform.get_scale().x, 1.0, 1e-6, "and back")
		layer.free()


func _args_carry_the_new_flags(h: TestHarness) -> void:
	var args := RunArgs.parse(PackedStringArray(["--run", "/tmp/r", "--night-floor", "0.38", "--ui-scale", "1.5", "--fullscreen"]))
	h.assert_near(args.night_floor, 0.38, 1e-9, "--night-floor")
	h.assert_near(args.ui_scale, 1.5, 1e-9, "--ui-scale")
	h.assert_true(args.fullscreen, "--fullscreen as a bare flag")
	var plain := RunArgs.parse(PackedStringArray(["--run", "/tmp/r"]))
	h.assert_near(plain.night_floor, 0.0, 1e-9, "the game's night keeps nothing by default")
	h.assert_false(plain.fullscreen, "windowed by default")
	var off := RunArgs.parse(PackedStringArray(["--fullscreen=false", "--run", "/tmp/r"]))
	h.assert_false(off.fullscreen, "--fullscreen=false")
	h.assert_eq(off.run, "/tmp/r", "and the run still parses after it")
