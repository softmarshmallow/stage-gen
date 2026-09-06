extends RefCounted

## The run loader against the promoted run: what it accepts, what it refuses,
## and that the layout it hands out is the one the manifest counted.

const BAD_RUN := "user://test_bad_run"

func run(h: TestHarness) -> void:
	var pkg := h.package()
	if not h.assert_true(pkg != null, "the run did not open"):
		return

	h.assert_eq(pkg.manifest.get("kind"), RunPackage.MANIFEST_KIND, "manifest kind")
	h.assert_eq(
		int(pkg.manifest.get("schema_version", 0)),
		RunPackage.MANIFEST_SCHEMA_VERSION,
		"manifest schema_version",
	)
	h.assert_true(RunPackage.check_manifest(pkg.manifest).is_empty(), "the run was refused")

	# The layout comes from package/world/layout.json, and the manifest embeds
	# the same document.
	var embedded: Dictionary = pkg.manifest.get("layout", {})
	h.assert_true(not pkg.layout.is_empty(), "layout is empty")
	h.assert_eq(int(pkg.layout.get("seed", 0)), 7, "layout seed")
	h.assert_near(float(pkg.layout.get("size_meters", 0.0)), 512.0, 1e-9, "layout size_meters")
	h.assert_eq(pkg.layout.keys(), embedded.keys(), "layout.json and manifest.layout differ in shape")
	h.assert_eq(
		pkg.layout.get("entities", []).size(),
		embedded.get("entities", []).size(),
		"layout.json and manifest.layout differ in entity count",
	)

	# Every placed entity is counted, and the counts are the manifest's.
	var counts: Dictionary = pkg.layout.get("counts", {})
	var tallied: Dictionary = {}
	for raw: Dictionary in pkg.layout.get("entities", []):
		var key: String = String(raw["prop"]) if raw["kind"] == "prop" else String(raw["actor"])
		tallied[key] = int(tallied.get(key, 0)) + 1
	h.assert_eq(tallied.size(), counts.size(), "counted a different set of ids")
	for id: String in counts.keys():
		h.assert_eq(tallied.get(id, 0), counts[id], "layout count for %s" % id)
	h.assert_eq(pkg.layout.get("entities", []).size(), 2365, "entity rows")
	h.assert_eq(pkg.layout.get("forage", []).size(), 1524, "forage rows")

	# Package-relative references resolve; anything that would leave the run
	# directory does not.
	h.assert_eq(
		pkg.path("package/world/splat.png"),
		TestHarness.RUN_DIR + "/package/world/splat.png",
		"path() joined the run directory",
	)
	h.assert_eq(pkg.path("../secrets.json"), "", "path() allowed a traversal")
	h.assert_eq(pkg.path("/etc/passwd"), "", "path() allowed an absolute reference")
	h.assert_eq(pkg.path("res://main.gd"), "", "path() allowed a res:// reference")

	# The plates decode, and the same reference is handed back from the cache.
	var splat := pkg.image("package/world/splat.png")
	if h.assert_true(splat != null, "splat.png did not decode"):
		h.assert_eq(splat.get_width(), 1024, "splat width")
		h.assert_true(pkg.image("package/world/splat.png") == splat, "image() did not cache")

	# The spike's kind is no longer accepted: one host, one manifest identity.
	var legacy: Dictionary = pkg.manifest.duplicate()
	legacy["kind"] = "oblique_survival_v0_manifest"
	var legacy_problems := RunPackage.check_manifest(legacy)
	h.assert_eq(legacy_problems.size(), 1, "the spike kind raised more than the kind refusal")
	h.assert_true(
		String(legacy_problems[0]).contains("oblique_survival_v0_manifest")
			and String(legacy_problems[0]).contains(RunPackage.MANIFEST_KIND),
		"the refusal does not name the kind it got and the kind it wants",
	)

	# So is the right kind under the wrong schema version.
	var versioned: Dictionary = pkg.manifest.duplicate()
	versioned["schema_version"] = 2
	var version_problems := RunPackage.check_manifest(versioned)
	h.assert_eq(version_problems.size(), 1, "a wrong schema_version raised more than one problem")
	h.assert_true(
		String(version_problems[0]).contains("schema_version"),
		"the schema_version refusal does not name schema_version",
	)

	# A manifest of the wrong kind is refused, and open() answers null.
	var broken: Dictionary = pkg.manifest.duplicate()
	broken["kind"] = "something_else"
	broken.erase("scale")
	var problems := RunPackage.check_manifest(broken)
	h.assert_true(problems.size() >= 2, "a broken manifest was not refused")
	h.assert_true(String(problems[0]).contains("kind"), "the kind refusal is not first")
	h.assert_true(problems.size() <= RunPackage.MAX_PROBLEMS, "more than eight problems reported")

	h.note("the ERROR lines below are the refusal test's own; they are expected")
	_write_bad_run({"kind": "something_else", "ground": {"size_meters": 256.0}})
	h.assert_true(RunPackage.open(BAD_RUN) == null, "open() accepted a refused manifest")
	h.assert_true(RunPackage.open("user://test_no_such_run") == null, "open() accepted a missing run")
	_clear_bad_run()

func _write_bad_run(manifest: Dictionary) -> void:
	DirAccess.make_dir_recursive_absolute(BAD_RUN)
	var file := FileAccess.open(BAD_RUN + "/manifest.json", FileAccess.WRITE)
	if file != null:
		file.store_string(JSON.stringify(manifest))
		file.close()

func _clear_bad_run() -> void:
	DirAccess.remove_absolute(BAD_RUN + "/manifest.json")
	DirAccess.remove_absolute(BAD_RUN)
