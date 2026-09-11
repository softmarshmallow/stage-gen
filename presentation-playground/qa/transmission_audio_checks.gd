extends SceneTree

## Runtime mixer measurements and lifecycle checks, never a listening verdict.
const PROCESSOR = preload("res://addons/game_presentation/audio/voice_effects.gd")
const TEXT_AUDIO = preload("res://addons/game_presentation/audio/text_reveal_audio.gd")
const OUTPUT := "res://qa/transmission-audio"
var _errors: Array[String] = []
var _evidence := {"listening_verdict": "not_performed", "tones": {}, "recordings": [], "errors": []}
var _processor: Node
var _dry_capture: AudioEffectCapture
var _wet_capture: AudioEffectCapture
var _dry_bus: StringName
var _sink_bus: StringName
var _initial_bus_count := 0


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	_initial_bus_count = AudioServer.bus_count
	_contract_checks()
	await _routing_checks()
	await _mixer_checks()
	await create_timer(0.2).timeout
	_expect(AudioServer.bus_count == _initial_bus_count, "All test and processor buses must be removed.")
	_evidence["errors"] = _errors
	_evidence["driver"] = AudioServer.get_driver_name()
	_evidence["mix_rate"] = AudioServer.get_mix_rate()
	DirAccess.make_dir_recursive_absolute(OUTPUT)
	var report := FileAccess.open(OUTPUT.path_join("validation.json"), FileAccess.WRITE)
	if report != null: report.store_string(JSON.stringify(_evidence, "  ", true) + "\n")
	for issue: String in _errors: printerr("FAIL Transmission Voice: " + issue)
	if _errors.is_empty(): print("PASS Transmission Voice: isolated buses, atomic validation, dry typing, lifecycle, true dry/zero PCM, native band response, EN/KO recorded-source DSP, no clipping or source changes; listening not performed")
	quit(0 if _errors.is_empty() else 1)


func _contract_checks() -> void:
	var a: Node = PROCESSOR.new()
	var b: Node = PROCESSOR.new()
	root.add_child(a)
	root.add_child(b)
	for invalid: Dictionary in [{"strength": "0.5"}, {"strength": NAN}, {"strength": -0.1}, {"strength": 1.1}, {"strength": true}, {"bypass": 1}, {"parent_bus": []}, {"parent_bus": "MissingVoiceBus"}, {"preset": "hologram"}, {"unknown": true}]:
		_expect(not a.configure(invalid).is_empty() and AudioServer.bus_count == _initial_bus_count, "Invalid configuration must reject before allocating: " + str(invalid))
	_expect(a.configure({"bypass": false}).is_empty() and b.configure().is_empty(), "Independent processors must initialize.")
	var bus_a: StringName = a.get_output_bus()
	var bus_b: StringName = b.get_output_bus()
	_expect(bus_a != bus_b and AudioServer.bus_count == _initial_bus_count + 2, "Each processor must own exactly one unique bus.")
	var before: Dictionary = a.get_state()
	_expect(not a.configure({"parent_bus": bus_a}).is_empty() and not a.configure({"parent_bus": bus_b}).is_empty(), "Self-send and rightward sends must reject.")
	_expect(not a.set_strength(INF).is_empty() and not a.set_bypassed("true").is_empty() and a.get_state() == before, "Invalid controls must preserve live settings.")
	_expect(b.get_state()["bypass"] and not b.get_state()["processing"], "An independent processor must remain dry by default.")
	a.set_bypassed(true)
	for index in 3: _expect(not AudioServer.is_bus_effect_enabled(AudioServer.get_bus_index(bus_a), index), "Bypass must disable every processor effect.")
	a.set_bypassed(false)
	a.set_strength(0.0)
	for index in 3: _expect(not AudioServer.is_bus_effect_enabled(AudioServer.get_bus_index(bus_a), index), "Zero strength must disable every processor effect.")
	a.set_strength(0.8)
	a.reset()
	_expect(a.get_output_bus() == bus_a and a.get_state()["processing"], "Reset must keep routing and settings.")
	a.cleanup()
	a.cleanup()
	_expect(AudioServer.get_bus_index(bus_a) < 0 and AudioServer.get_bus_index(bus_b) >= 0, "Repeated cleanup must preserve another live processor.")
	_expect(a.configure().is_empty(), "A cleaned-up processor must be reusable.")
	a.free()
	b.free()
	var detached: Node = PROCESSOR.new()
	detached.configure()
	detached.free()
	_expect(AudioServer.bus_count == _initial_bus_count, "Deletion must clean up even without tree attachment.")


func _routing_checks() -> void:
	var processor: Node = PROCESSOR.new()
	var audio: Node = TEXT_AUDIO.new()
	root.add_child(processor)
	root.add_child(audio)
	processor.configure({"bypass": false})
	var bus: StringName = processor.get_output_bus()
	_expect(audio.configure({"voice_bus": bus}).is_empty(), "Text audio must accept a separate voice route.")
	audio.begin("Typing stays dry.")
	audio.update_reveal(1, 0.1)
	_expect(audio.get_state()["bus"] == &"Master" and audio.get_state()["voice_bus"] == bus and audio.get_state()["typing_play_count"] == 1, "Typing must retain its own route while voice is processed.")
	audio.begin("Voice", _tone(1000.0, 0.8))
	await create_timer(0.12).timeout
	var before: Dictionary = audio.get_state()
	_expect(not audio.configure({"voice_bus": "MissingVoiceBus"}).is_empty() and audio.get_state()["voice_playing"] and audio.get_state()["voice_bus"] == bus, "Invalid voice route must preserve actual playback and routing.")
	audio.set_paused(true)
	await create_timer(0.12).timeout
	_expect(audio.get_state()["paused"] and not audio.get_state()["voice_finished"] and float(audio.get_state()["voice_position_seconds"]) >= float(before["voice_position_seconds"]), "Pause must retain the current voice cursor.")
	audio.set_paused(false)
	audio.stop()
	processor.reset()
	_expect(not audio.get_state()["voice_playing"], "Stopping before reset must interrupt the old source.")
	audio.begin("Replacement language", _tone(800.0, 0.1))
	await create_timer(0.24).timeout
	_expect(audio.get_state()["voice_finished"], "Replacement source must complete through the same route.")
	audio.configure({"bus": bus})
	_expect(audio.get_state()["bus"] == bus and audio.get_state()["voice_bus"] == bus, "Omitting voice_bus must preserve the existing shared-bus behavior.")
	audio.stop()
	audio.free()
	processor.free()


func _mixer_checks() -> void:
	_sink_bus = _add_bus("TransmissionProofSink", &"Master")
	AudioServer.set_bus_mute(AudioServer.get_bus_index(_sink_bus), true)
	_dry_bus = _add_bus("TransmissionProofDry", _sink_bus)
	_dry_capture = AudioEffectCapture.new()
	_dry_capture.buffer_length = 30.0
	AudioServer.add_bus_effect(AudioServer.get_bus_index(_dry_bus), _dry_capture)
	_processor = PROCESSOR.new()
	root.add_child(_processor)
	_processor.configure({"parent_bus": _sink_bus, "strength": 1.0, "bypass": false})
	_wet_capture = AudioEffectCapture.new()
	_wet_capture.buffer_length = 30.0
	AudioServer.add_bus_effect(AudioServer.get_bus_index(_processor.get_output_bus()), _wet_capture)
	for frequency: float in [80.0, 1000.0, 12000.0]:
		var pair := await _capture_pair(_tone(frequency, 0.5))
		var dry_rms := _steady_rms(pair["dry"])
		var wet_rms := _steady_rms(pair["wet"])
		var gain := wet_rms / maxf(dry_rms, 0.000001)
		_evidence["tones"][str(int(frequency))] = {"dry_rms": dry_rms, "wet_rms": wet_rms, "gain": gain}
		_expect(dry_rms > 0.01 and wet_rms > 0.0000001, "The actual mixer must capture the test tone.")
		if frequency == 1000.0: _expect(gain > 0.4 and gain < 1.1, "The voice band must remain audible without excessive gain.")
		else: _expect(gain < 0.12, "Transmission must attenuate bass and high-frequency energy: " + str(frequency))
		_expect(_peak(pair["wet"]) < 0.99, "Processed tones must not clip.")
	_processor.set_bypassed(true)
	var bypass_pair := await _capture_pair(_tone(1000.0, 0.4))
	var bypass_difference := _aligned_difference(bypass_pair["dry"], bypass_pair["wet"])
	_expect(bypass_difference < 0.000001, "Bypass PCM must match the direct dry source.")
	_processor.set_bypassed(false)
	_processor.set_strength(0.0)
	var zero_pair := await _capture_pair(_tone(1000.0, 0.4))
	var zero_difference := _aligned_difference(zero_pair["dry"], zero_pair["wet"])
	_expect(zero_difference < 0.000001, "Zero-strength PCM must match the direct dry source.")
	_evidence["bypass_max_sample_difference"] = bypass_difference
	_evidence["zero_max_sample_difference"] = zero_difference
	await _typing_mixer_check()
	_processor.set_strength(0.65)
	await _recording_checks()
	_processor.cleanup()
	_processor.free()
	AudioServer.remove_bus(AudioServer.get_bus_index(_dry_bus))
	AudioServer.remove_bus(AudioServer.get_bus_index(_sink_bus))


func _typing_mixer_check() -> void:
	_processor.set_strength(1.0)
	_processor.reset()
	var audio: Node = TEXT_AUDIO.new()
	root.add_child(audio)
	audio.configure({"bus": _dry_bus, "voice_bus": _processor.get_output_bus()})
	_dry_capture.clear_buffer()
	_wet_capture.clear_buffer()
	audio.begin("Dry typing")
	audio.update_reveal(1, 0.1)
	await create_timer(0.15).timeout
	var dry := _dry_capture.get_buffer(_dry_capture.get_frames_available())
	var wet := _wet_capture.get_buffer(_wet_capture.get_frames_available())
	_expect(_peak(dry) > 0.0001 and _peak(wet) < 0.000001, "Actual typing PCM must appear only on its dry bus.")
	audio.free()


func _recording_checks() -> void:
	var manifest: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://games/bishoujo_afterlight/voice/manifest.json"))
	for language: String in ["en", "ko"]:
		for line_id: String in manifest["lines"][language]:
			var record: Dictionary = manifest["lines"][language][line_id]
			if record.get("speaker_id", "") != "eira" or record.get("status", "") != "ready": continue
			var source_path: String = record["path"]
			_expect(FileAccess.get_sha256(source_path) == record["audio_sha256"], "Every selected Eira source must match its recording manifest.")
		var record: Dictionary = manifest["lines"][language]["episode.eira_on_the_relay"]
		var source_path: String = record["path"]
		var source_hash := FileAccess.get_sha256(source_path)
		var stream := AudioStreamMP3.new()
		stream.data = FileAccess.get_file_as_bytes(source_path)
		_expect(stream != null and stream.get_length() > 0.0, "Existing Eira recording must decode: " + language)
		if stream == null: continue
		var pair := await _capture_pair(stream)
		var dry_peak := _peak(pair["dry"])
		var wet_peak := _peak(pair["wet"])
		_expect(dry_peak > 0.01 and wet_peak > 0.01 and wet_peak < 0.99, "Existing EN/KO recorded voice must remain nonzero and unclipped after processing.")
		_expect(absf(_steady_rms(pair["dry"]) - _steady_rms(pair["wet"])) > 0.0001, "Transmission must measurably change the existing voice PCM.")
		_expect(FileAccess.get_sha256(source_path) == source_hash, "Runtime processing must not mutate source recordings.")
		_save_audio(pair["dry"], language + "-dry.wav")
		_save_audio(pair["wet"], language + "-transmission.wav")
		_evidence["recordings"].append({"language": language, "line_id": "episode.eira_on_the_relay", "source_path": source_path, "source_sha256": source_hash, "dry_peak": dry_peak, "wet_peak": wet_peak, "dry_rms": _steady_rms(pair["dry"]), "wet_rms": _steady_rms(pair["wet"]), "duration_seconds": stream.get_length()})


func _capture_pair(stream: AudioStream) -> Dictionary:
	_processor.reset()
	var dry := AudioStreamPlayer.new()
	var wet := AudioStreamPlayer.new()
	dry.stream = stream
	wet.stream = stream
	dry.bus = _dry_bus
	wet.bus = _processor.get_output_bus()
	root.add_child(dry)
	root.add_child(wet)
	_dry_capture.clear_buffer()
	_wet_capture.clear_buffer()
	dry.play()
	wet.play()
	await create_timer(stream.get_length() + 0.12).timeout
	dry.stop()
	wet.stop()
	var result := {"dry": _dry_capture.get_buffer(_dry_capture.get_frames_available()), "wet": _wet_capture.get_buffer(_wet_capture.get_frames_available())}
	dry.free()
	wet.free()
	return result


func _add_bus(base: String, parent: StringName) -> StringName:
	var name := StringName(base + "_" + str(get_instance_id()))
	var index := AudioServer.bus_count
	AudioServer.add_bus(index)
	AudioServer.set_bus_name(index, name)
	AudioServer.set_bus_send(index, parent)
	return name


func _tone(frequency: float, duration: float) -> AudioStreamWAV:
	var stream := AudioStreamWAV.new()
	stream.mix_rate = int(AudioServer.get_mix_rate())
	stream.format = AudioStreamWAV.FORMAT_16_BITS
	var count := int(stream.mix_rate * duration)
	var data := PackedByteArray()
	data.resize(count * 2)
	for index in count:
		var envelope := minf(1.0, minf(float(index) / 100.0, float(count - 1 - index) / 100.0))
		data.encode_s16(index * 2, int(sin(TAU * frequency * index / stream.mix_rate) * 8000.0 * envelope))
	stream.data = data
	return stream


func _steady_rms(frames: PackedVector2Array) -> float:
	if frames.is_empty(): return 0.0
	var total := 0.0
	var first := int(frames.size() * 0.25)
	var end := int(frames.size() * 0.65)
	for index in range(first, end): total += frames[index].length_squared() * 0.5
	return sqrt(total / maxi(1, end - first))


func _peak(frames: PackedVector2Array) -> float:
	var peak := 0.0
	for frame: Vector2 in frames: peak = maxf(peak, maxf(absf(frame.x), absf(frame.y)))
	return peak


func _aligned_difference(a: PackedVector2Array, b: PackedVector2Array) -> float:
	var first_a := _first_signal(a)
	var first_b := _first_signal(b)
	if first_a < 0 or first_b < 0: return INF
	var length := mini(a.size() - first_a, b.size() - first_b)
	var difference := 0.0
	for offset in length: difference = maxf(difference, (a[first_a + offset] - b[first_b + offset]).length())
	return difference


func _first_signal(frames: PackedVector2Array) -> int:
	for index in frames.size():
		if frames[index].length_squared() > 0.0000000001: return index
	return -1


func _save_audio(frames: PackedVector2Array, filename: String) -> void:
	var pcm := PackedByteArray()
	pcm.resize(frames.size() * 4)
	for index in frames.size():
		pcm.encode_s16(index * 4, int(clampf(frames[index].x, -1.0, 1.0) * 32767.0))
		pcm.encode_s16(index * 4 + 2, int(clampf(frames[index].y, -1.0, 1.0) * 32767.0))
	var stream := AudioStreamWAV.new()
	stream.format = AudioStreamWAV.FORMAT_16_BITS
	stream.stereo = true
	stream.mix_rate = int(AudioServer.get_mix_rate())
	stream.data = pcm
	DirAccess.make_dir_recursive_absolute(OUTPUT)
	_expect(stream.save_to_wav(OUTPUT.path_join(filename)) == OK, "Native capture must save for optional audition: " + filename)


func _expect(condition: bool, message: String) -> void:
	if not condition: _errors.append(message)
