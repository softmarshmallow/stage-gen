extends RefCounted

var checks := 0
var failures: Array[String] = []
var finished := false

func assert_true(value: bool, message: String) -> bool:
	checks += 1
	if not value:
		failures.append(message)
	return value

func assert_false(value: bool, message: String) -> bool:
	return assert_true(not value, message)

func assert_eq(actual: Variant, expected: Variant, message: String) -> bool:
	return assert_true(actual == expected, "%s: expected %s, got %s" % [message, expected, actual])

func assert_near(actual: float, expected: float, epsilon: float, message: String) -> bool:
	return assert_true(is_finite(actual) and absf(actual - expected) <= epsilon, message)

func done() -> void:
	finished = true
