extends RefCounted

## This episode is authored for Afterlight's own host. These cues are not a
## public scenario language or a universal game contract. Text stays in the
## paired English/Korean sets; stable beat IDs survive wording revisions.
const BEATS := [
	{
		"id": "undeliverable",
		"type": "monologue",
		"text": "episode.undeliverable",
		"speaker": "",
		"background": 0,
		"cast": []
	},
	{
		"id": "across_the_threshold",
		"type": "walk",
		"text": "episode.across_the_threshold",
		"speaker": "",
		"background": 0,
		"cast": []
	},
	{
		"id": "eyes_on_nami",
		"type": "eye",
		"eye_mode": "waking_opening",
		"text": "episode.eyes_on_nami",
		"speaker": "nami",
		"cast": [
			"nami"
		]
	},
	{
		"id": "no_ordinary_post",
		"type": "dialogue",
		"text": "episode.no_ordinary_post",
		"speaker": "nami",
		"cast": [
			"nami",
			"yuzu"
		],
		"camera": "wide",
		"mark": "sweat_drop",
		"mark_preset": "step_loop"
	},
	{
		"id": "a_glass_record",
		"type": "dialogue",
		"text": "episode.a_glass_record",
		"speaker": "yuzu",
		"camera": "close"
	},
	{
		"id": "no_forwarding_address",
		"type": "dialogue",
		"text": "episode.no_forwarding_address",
		"speaker": "nami",
		"camera": "wide",
		"manpu_events": [{"actor": "nami", "id": "sigh_puff", "preset": "sigh_puff"}],
		"manpu_timing": "after_reveal"
	},
	{
		"id": "courier_offer",
		"type": "choice",
		"autoplay": {"default_choice": "help_first"},
		"text": "episode.courier_offer",
		"speaker": "nami",
		"camera": "wide",
		"choices": [
			{"id": "help_first", "text": "episode.choice.help_first"},
			{"id": "tea_first", "text": "episode.choice.tea_first"}
		]
	},
	{
		"id": "courier_reply",
		"type": "dialogue",
		"text": "episode.courier_reply.help_first",
		"speaker": "nami",
		"camera": "close",
		"choice_from": "courier_offer",
		"responses": {
			"help_first": "episode.courier_reply.help_first",
			"tea_first": "episode.courier_reply.tea_first"
		},
		"mark": "sparkle",
		"manpu_events": [{"actor": "nami", "id": "sigh_puff", "preset": "sigh_puff"}],
		"manpu_timing": "after_reveal"
	},
	{
		"id": "one_more_minute",
		"type": "monologue",
		"text": "episode.one_more_minute",
		"speaker": ""
	},
	{
		"id": "a_second_line",
		"type": "dialogue",
		"text": "episode.a_second_line",
		"speaker": "yuzu",
		"camera": "close",
		"mark": "confusion"
	},
	{
		"id": "caught_in_the_light",
		"type": "detail",
		"text": "episode.caught_in_the_light",
		"speaker": "nami"
	},
	{
		"id": "the_warning",
		"type": "dialogue",
		"text": "episode.the_warning",
		"speaker": "yuzu",
		"cast": ["yuzu"],
		"camera": "close",
		"focus": "none",
		"background_blackout": {"delay_seconds": 1.0},
		"mark": "surprise"
	},
	{
		"id": "verified_trouble",
		"type": "dialogue",
		"text": "episode.verified_trouble",
		"speaker": "nami",
		"cast": ["nami", "yuzu"],
		"camera": "wide"
	},
	{
		"id": "keep_the_wards_lit",
		"type": "dialogue",
		"text": "episode.keep_the_wards_lit",
		"speaker": "yuzu",
		"camera": "close"
	},
	{
		"id": "divide_the_work",
		"type": "dialogue",
		"text": "episode.divide_the_work",
		"speaker": "nami",
		"camera": "wide"
	},
	{
		"id": "sena_takes_over",
		"type": "handoff",
		"exit_preset": "walk_away",
		"text": "episode.sena_takes_over",
		"speaker": "sena",
		"cast": [
			"nami",
			"yuzu",
			"sena"
		],
		"camera": "wide",
		"mark": "sparkle"
	},
	{
		"id": "the_useful_kind",
		"type": "dialogue",
		"text": "episode.the_useful_kind",
		"speaker": "yuzu",
		"camera": "wide",
		"focus": "none",
		"mark": "sweat_drop",
		"quick_approach": {"actor": "yuzu", "target": "sena", "delay_seconds": 0.25}
	},
	{
		"id": "reading_room",
		"type": "establish",
		"text": "episode.reading_room",
		"speaker": "",
		"background": 1,
		"cast": []
	},
	{
		"id": "a_live_line",
		"type": "dialogue",
		"text": "episode.a_live_line",
		"speaker": "sena",
		"cast": [
			"yuzu",
			"sena"
		],
		"camera": "wide"
	},
	{
		"id": "riko_on_the_glass",
		"type": "dialogue",
		"focus": "restless_bounce",
		"text": "episode.riko_on_the_glass",
		"speaker": "riko",
		"cast": [
			"yuzu",
			"sena",
			"riko"
		],
		"physical": ["riko"],
		"camera": "wide",
		"cast_pan": {"actor": "riko", "anchor_x": 640.0, "delay_seconds": 0.35},
		"mark": "anger_vein",
		"mark_preset": "step_loop"
	},
	{
		"id": "two_green_lamps",
		"type": "dialogue",
		"text": "episode.two_green_lamps",
		"speaker": "yuzu",
		"camera": "wide",
		"cast_pan": {"actor": "yuzu", "anchor_x": 640.0}
	},
	{
		"id": "waiting_for_the_signal",
		"type": "dialogue",
		"text": "episode.waiting_for_the_signal",
		"speaker": "riko",
		"camera": "wide",
		"cast_pan": {"actor": "riko", "anchor_x": 640.0},
		"mark": "sweat_drop"
	},
	{
		"id": "hold_the_message",
		"type": "monologue",
		"text": "episode.hold_the_message",
		"speaker": "",
		"background": 3,
		"cast": []
	},
	{
		"id": "eira_on_the_relay",
		"type": "projection",
		"text": "episode.eira_on_the_relay",
		"speaker": "eira",
		"cast": ["eira"],
		"camera": "wide"
	},
	{
		"id": "a_voice_in_the_glass",
		"type": "dialogue",
		"text": "episode.a_voice_in_the_glass",
		"speaker": ""
	},
	{
		"id": "the_return_channel",
		"type": "dialogue",
		"text": "episode.the_return_channel",
		"speaker": "eira",
		"camera": "close"
	},
	{
		"id": "one_private_question",
		"type": "dialogue",
		"text": "episode.one_private_question",
		"speaker": ""
	},
	{
		"id": "follow_the_pulse",
		"type": "dialogue",
		"text": "episode.follow_the_pulse",
		"speaker": "eira"
	},
	{
		"id": "eira_signs_off",
		"type": "dialogue",
		"text": "episode.eira_signs_off",
		"speaker": "eira",
		"camera": "wide"
	},
	{
		"id": "relay_return",
		"type": "monologue",
		"text": "episode.relay_return",
		"speaker": "",
		"background": 1,
		"cast": [],
		"physical": ["eira"]
	},
	{
		"id": "follow_the_diagram",
		"type": "dialogue",
		"text": "episode.follow_the_diagram",
		"speaker": "sena",
		"cast": ["yuzu", "sena", "riko"],
		"camera": "close"
	},
	{
		"id": "checked_twice",
		"type": "dialogue",
		"text": "episode.checked_twice",
		"speaker": "yuzu",
		"camera": "wide"
	},
	{
		"id": "the_signal",
		"type": "dialogue",
		"text": "episode.the_signal",
		"speaker": "riko",
		"camera": "close",
		"mark": "surprise"
	},
	{
		"id": "the_reroute",
		"type": "dialogue",
		"text": "episode.the_reroute",
		"speaker": "sena",
		"camera": "wide",
		"sprite_burst": {"actor": "sena", "sprites": ["sparkle"], "delay_seconds": 0.85, "origin_uv": Vector2(0.5, 0.25)}
	},
	{
		"id": "the_seal_answers", "type": "dialogue", "text": "episode.the_seal_answers",
		"speaker": "nami", "cast": ["nami", "yuzu", "sena"], "camera": "wide",
		"background": 1
	},
	{
		"id": "scarlet_pressure", "type": "rift", "duration_seconds": 2.0,
		"text": "episode.scarlet_pressure", "speaker": "", "cast": [], "camera": "wide",
		"heat": 0.8, "barrier": 0.88, "scene_corruption": 0.68,
		"shake": {"amplitude_x": 56.0, "amplitude_y": 42.0, "duration": 1.85, "frequency": 10.5}
	},
	{
		"id": "between_addresses", "type": "monologue",
		"text": "episode.between_addresses", "speaker": "", "background": 2, "cast": []
	},
	{
		"id": "the_unlit_house", "type": "eye", "eye_mode": "waking_opening", "eye_portrait": false,
		"text": "episode.the_unlit_house", "speaker": "", "cast": [], "camera": "wide",
		"place_name": "episode.place.beyond", "scene_corruption": 0.9, "heat": 0.92,
		"corruption": {"area": Rect2(750, 170, 280, 460), "strength": 0.85}
	},
	{
		"id": "the_keeper", "type": "dialogue",
		"text": "episode.the_keeper", "speaker": "keeper", "speaker_name": "episode.speaker.keeper",
		"cast": ["keeper"], "camera": "wide", "place_name": "episode.place.beyond",
		"scene_corruption": 0.85, "heat": 0.85, "barrier": 0.32,
		"corruption": {"actor": "keeper", "strength": 0.98},
		"shake": {"amplitude_x": 26.0, "amplitude_y": 20.0, "duration": 1.25, "frequency": 9.5, "seed": 3}
	},
	{
		"id": "the_price_of_return", "type": "dialogue",
		"text": "episode.the_price_of_return", "speaker": "keeper", "speaker_name": "episode.speaker.keeper",
		"camera": "close", "place_name": "episode.place.beyond",
		"scene_corruption": 0.82, "heat": 0.8, "barrier": 0.28,
		"corruption": {"actor": "keeper", "strength": 0.93}
	},
	{
		"id": "a_name_is_not_consent", "type": "dialogue",
		"text": "episode.a_name_is_not_consent", "speaker": "", "camera": "wide",
		"place_name": "episode.place.beyond", "scene_corruption": 0.88, "heat": 0.9, "barrier": 0.42,
		"corruption": {"actor": "keeper", "strength": 0.98},
		"shake": {"amplitude_x": 22.0, "amplitude_y": 16.0, "duration": 1.25, "frequency": 8.0, "seed": 5}
	},
	{
		"id": "the_room_refuses", "type": "rift", "duration_seconds": 2.2,
		"text": "episode.the_room_refuses", "speaker": "", "camera": "wide",
		"place_name": "episode.place.beyond", "scene_corruption": 1.0, "heat": 1.0, "barrier": 0.97,
		"corruption": {"actor": "keeper", "strength": 1.0},
		"shake": {"amplitude_x": 72.0, "amplitude_y": 54.0, "duration": 1.95, "frequency": 12.0, "seed": 7}
	},
	{
		"id": "nami_beyond_the_wall", "type": "dialogue",
		"text": "episode.nami_beyond_the_wall", "speaker": "", "speaker_name": "guest.nami.name",
		"place_name": "episode.place.beyond", "scene_corruption": 0.8, "heat": 0.75, "barrier": 0.38,
		"corruption": {"actor": "keeper", "strength": 0.9}
	},
	{
		"id": "follow_the_warmth", "type": "dialogue",
		"text": "episode.follow_the_warmth", "speaker": "", "cast": [],
		"place_name": "episode.place.beyond", "scene_corruption": 0.68, "heat": 0.62, "barrier": 0.58,
		"corruption": {"area": Rect2(750, 170, 280, 460), "strength": 0.82}
	},
	{
		"id": "the_return", "type": "rift", "duration_seconds": 1.8,
		"text": "episode.the_return", "speaker": "", "background": 1, "cast": [], "camera": "wide",
		"scene_corruption": 0.82, "heat": 0.85, "barrier": 0.95, "vfx_fade_out": true,
		"shake": {"amplitude_x": 54.0, "amplitude_y": 42.0, "duration": 1.6, "frequency": 11.0, "seed": 11}
	},
	{
		"id": "a_hand_to_hold", "type": "eye", "eye_mode": "waking_opening", "text": "episode.a_hand_to_hold",
		"speaker": "nami", "background": 1, "cast": ["nami"]
	},
	{
		"id": "a_touch_that_stays", "type": "contact", "text": "episode.a_touch_that_stays",
		"speaker": "nami", "cast": ["nami"], "camera": "wide", "focus": "none"
	},
	{
		"id": "only_a_second", "type": "dialogue", "text": "episode.only_a_second",
		"speaker": "nami", "cast": ["nami", "yuzu", "sena", "riko"], "camera": "wide",
		"manpu_events": [{"actor": "nami", "id": "sigh_puff", "preset": "sigh_puff"}],
		"manpu_timing": "after_reveal"
	},
	{
		"id": "steady_at_last",
		"type": "dialogue",
		"text": "episode.steady_at_last",
		"speaker": "yuzu",
		"camera": "close"
	},
	{
		"id": "all_clear",
		"type": "dialogue",
		"text": "episode.all_clear",
		"speaker": "riko",
		"camera": "wide",
		"manpu_events": [{"actor": "riko", "id": "sigh_puff", "preset": "sigh_puff"}],
		"manpu_timing": "after_reveal"
	},
	{
		"id": "riko_signs_off",
		"type": "exit",
		"text": "episode.riko_signs_off",
		"speaker": "riko",
		"camera": "wide"
	},
	{
		"id": "a_modest_name",
		"type": "dialogue",
		"text": "episode.a_modest_name",
		"speaker": "sena",
		"camera": "wide",
		"manpu_events": [{"actor": "sena", "id": "sweat_drop", "preset": "sweat_drop_fall"}],
		"manpu_timing": "after_reveal"
	},
	{
		"id": "back_to_the_house",
		"type": "establish",
		"text": "episode.back_to_the_house",
		"speaker": "",
		"background": 0,
		"cast": []
	},
	{
		"id": "everyone_accounted_for",
		"type": "dialogue",
		"text": "episode.everyone_accounted_for",
		"speaker": "nami",
		"cast": [
			"nami",
			"yuzu",
			"sena",
			"riko"
		],
		"physical": ["nami", "yuzu", "sena", "riko"],
		"camera": "wide",
		"mark": "sparkle",
		"mark_preset": "step_loop"
	},
	{
		"id": "a_proper_hello",
		"type": "dialogue",
		"text": "episode.a_proper_hello",
		"speaker": "riko",
		"camera": "close",
		"manpu_events": [{"actor": "riko", "id": "sweat_drop", "preset": "sweat_drop_fall"}],
		"manpu_timing": "after_reveal"
	},
	{
		"id": "the_unsigned_entry",
		"type": "dialogue",
		"text": "episode.the_unsigned_entry",
		"speaker": "yuzu",
		"camera": "wide",
		"mark": "confusion"
	},
	{
		"id": "the_next_arrival",
		"type": "ending",
		"text": "episode.the_next_arrival",
		"speaker": ""
	}
]
