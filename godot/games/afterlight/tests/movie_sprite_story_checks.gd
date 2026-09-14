extends SceneTree

var errors: Array[String] = []

func _initialize() -> void:
	_run.call_deferred()

func _run() -> void:
	root.size = Vector2i(1280, 900)
	var app = load("res://main.tscn").instantiate()
	root.add_child(app)
	await process_frame
	var game = app.active_scene
	game.set_process(false)
	_expect(game._load_errors.is_empty(), "Main story initializes.")
	_expect(game._movie_cast.textures.size() == 2, "Default story binds both movie actors.")
	for tick in 1500:
		game._movie_cast.advance(0.0, "", false)
		var states: Dictionary = game._movie_cast.snapshot().actors
		if states.size() == 2 and states.yuzu.state == "ready" and states.riko.state == "ready": break
		await create_timer(0.003).timeout
	for id: String in ["yuzu", "riko"]:
		_expect(game._stage._textures[id] is ViewportTexture, id + " uses the composed movie texture in the actual story renderer.")
		_expect(game._movie_cast.snapshot().actors[id].state == "ready", id + " becomes drawable.")
	game._movie_cast.advance(0.2, "yuzu", true)
	_expect(game._movie_cast.snapshot().actors.yuzu.mouth == "mouth_a", "Only the directed speaker animates her mouth.")
	_expect(game._movie_cast.snapshot().actors.riko.mouth == "rest", "Other speaker remains at rest.")
	game._movie_cast.set_paused(true)
	var before: Dictionary = game._movie_cast.snapshot()
	game._movie_cast.advance(1.0, "yuzu", false)
	_expect(game._movie_cast.snapshot().actors.yuzu.clock_seconds == before.actors.yuzu.clock_seconds, "Pause holds body time.")
	game._movie_cast.set_paused(false)
	for step in 20:
		if game.current_beat().get("id") == "a_glass_record": break
		game._advance_clocks(20.0)
		game._reveal.request_advance()
		game._next()
	_expect(game.current_beat().get("id") == "a_glass_record", "Normal episode reaches Yuzu's introduction.")
	for tick in 15:
		game._process(0.016)
		await process_frame
	if DisplayServer.get_name() != "headless":
		await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png("res://tests/movie-sprite/main-story.png")
	var movie_reference: WeakRef = weakref(game._movie_cast)
	game._text_audio.stop()
	await create_timer(0.08).timeout
	app.queue_free()
	for frame in 3: await process_frame
	_expect(movie_reference.get_ref() == null, "Story exit frees the movie adapter and its children.")
	if errors.is_empty(): print("PASS Movie Sprite Story: default route, texture bridge, speaking, pause, natural introduction and cleanup.")
	else: printerr(errors)
	quit(0 if errors.is_empty() else 1)

func _expect(condition: bool, message: String) -> void:
	if not condition: errors.append(message)
