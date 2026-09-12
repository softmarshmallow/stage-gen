extends "res://addons/demo_support/testing/run_tests.gd"

func _initialize() -> void:
	TestHarness.VALIDATE_MANIFEST = Callable(SurvivalDocument, "check_manifest")
	TestHarness.LAYOUT_REF = SurvivalDocument.LAYOUT_REF
	super._initialize()
