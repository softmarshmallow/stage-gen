extends RefCounted

## An original synthetic program. No assets, game identity or generation needed.
static func document() -> Dictionary:
	return {
		"kind": "scenario-program-v2", "schema_version": 2,
		"scenario_id": "signal", "entry": "start",
		"flags": [{"flag_id": "heard"}],
		"endings": [{"outcome_id": "received", "label": "Signal received"}],
		"blocks": [
			{"label": "start", "statements": [
				{"kind": "line", "text": "A distant signal arrives."},
				{"kind": "choice", "options": [{"text": "Acknowledge", "target": "reply"}]},
			]},
			{"label": "reply", "statements": [
				{"kind": "set", "flag": "heard", "value": true},
				{"kind": "end", "outcome": "received"},
			]},
		],
	}
