extends Node2D

const Player = preload("res://player.gd")
const START := Vector2(140, 500)
const TOKENS := [Vector2(210, 190), Vector2(490, 190), Vector2(560, 470)]
const WALLS := [Rect2(50, 130, 650, 12), Rect2(50, 580, 650, 12), Rect2(50, 130, 12, 462), Rect2(688, 130, 12, 462), Rect2(325, 275, 30, 180)]
const PROFILES := {
	"A": {"label": "A / Precise", "acceleration": 2600.0, "braking": 3200.0},
	"B": {"label": "B / Gliding", "acceleration": 650.0, "braking": 420.0}
}

var player: CharacterBody2D
var profile: String = "A"
var collected: Array[int] = []
var finished: bool = false
var elapsed: float = 0.0
var run_id: int = 0
var status_label: Label
var readout: Label
var feedback_label: Label
var feedback: Array[Dictionary] = []
var questions: Array[OptionButton] = []
var session_id: String = str(Time.get_unix_time_from_system())
var telemetry_clock: float = 0.0

func _ready() -> void:
	for rect in WALLS:
		var body := StaticBody2D.new()
		body.position = rect.get_center()
		var collision := CollisionShape2D.new()
		var shape := RectangleShape2D.new()
		shape.size = rect.size
		collision.shape = shape
		body.add_child(collision)
		add_child(body)
	player = Player.new()
	add_child(player)
	_build_ui()
	_reset("A")
	print("FEEL_LAB_READY")

func _label(text: String, x: float, y: float, width: float, font_size: int = 18) -> Label:
	var label := Label.new()
	label.text = text
	label.position = Vector2(x, y)
	label.size.x = width
	label.add_theme_font_size_override("font_size", font_size)
	label.add_theme_color_override("font_color", Color("dbe6ef"))
	add_child(label)
	return label

func _button(text: String, rect: Rect2, action: Callable) -> Button:
	var button := Button.new()
	button.text = text
	button.position = rect.position
	button.size = rect.size
	button.focus_mode = Control.FOCUS_NONE
	button.pressed.connect(action)
	add_child(button)
	return button

func _build_ui() -> void:
	_label("GAME FEEL LAB", 50, 24, 660, 30)
	_label("Move. Collect three signals. Reach the exit.", 50, 66, 660)
	_button("1  Precise", Rect2(750, 130, 155, 44), func(): _reset("A"))
	_button("2  Gliding", Rect2(920, 130, 155, 44), func(): _reset("B"))
	_label("SAME LEVEL / TWO PROFILES", 750, 93, 340, 16)
	readout = _label("", 750, 192, 340, 17)
	_label("TRY IT, THEN ANSWER", 750, 306, 340, 16)
	_label("Release the key while moving.\nDoes the stopping distance feel right?", 750, 342, 340, 17)
	questions.append(_choice(Vector2(750, 400)))
	_label("Can you tell where to go next\nwithout reading more instructions?", 750, 454, 340, 17)
	questions.append(_choice(Vector2(750, 512)))
	_button("Save this reaction", Rect2(750, 570, 325, 40), _save_feedback)
	feedback_label = _label("Answers apply to the current profile.", 750, 626, 350, 15)
	status_label = _label("", 50, 616, 660, 20)
	_label("WASD / arrows: move   |   R: reset   |   1 / 2: compare", 50, 659, 690, 17)
	_button("Download reactions", Rect2(750, 664, 325, 36), _export_feedback)

func _choice(at: Vector2) -> OptionButton:
	var choice := OptionButton.new()
	choice.position = at
	choice.size = Vector2(325, 36)
	for text in ["Choose after playing", "Yes", "No", "Not sure yet"]:
		choice.add_item(text)
	choice.focus_mode = Control.FOCUS_NONE
	add_child(choice)
	return choice

func _reset(next_profile: String) -> void:
	profile = next_profile
	run_id += 1
	player.position = START
	player.velocity = Vector2.ZERO
	player.enabled = true
	player.acceleration = PROFILES[profile].acceleration
	player.braking = PROFILES[profile].braking
	player.tint = Color("72e0be") if profile == "A" else Color("f1bd70")
	finished = false
	elapsed = 0.0
	collected.clear()
	for choice in questions:
		choice.select(0)
	readout.text = "%s\nSpeed: 240 px/s\nAcceleration: %.0f px/s²\nBraking: %.0f px/s²" % [PROFILES[profile].label, player.acceleration, player.braking]
	feedback_label.text = "Answers apply to profile %s, run %d." % [profile, run_id]
	_update_status()
	queue_redraw()

func _unhandled_key_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo:
		match event.physical_keycode:
			KEY_1: _reset("A")
			KEY_2: _reset("B")
			KEY_R: _reset(profile)

func _process(delta: float) -> void:
	if not finished:
		elapsed += delta
		for i in range(TOKENS.size()):
			if i not in collected and player.position.distance_to(TOKENS[i]) < 30:
				collected.append(i)
		if collected.size() == TOKENS.size() and player.position.distance_to(Vector2(620, 530)) < 30:
			finished = true
			player.enabled = false
	_update_status()
	queue_redraw()
	telemetry_clock += delta
	if telemetry_clock > 0.1:
		telemetry_clock = 0.0
		_publish_state()

func _update_status() -> void:
	status_label.text = "Complete in %.1fs / Try the other profile." % elapsed if finished else "Signals: %d / 3    |    Exit: %s" % [collected.size(), "OPEN" if collected.size() == 3 else "locked"]

func _draw() -> void:
	draw_style_box(_panel(Color("111d2c")), Rect2(50, 130, 650, 462))
	for x in range(70, 690, 40):
		draw_line(Vector2(x, 142), Vector2(x, 580), Color("192b3b"))
	for y in range(150, 580, 40):
		draw_line(Vector2(62, y), Vector2(688, y), Color("192b3b"))
	for rect in WALLS:
		draw_rect(rect, Color("496274"))
	for i in range(TOKENS.size()):
		if i not in collected:
			draw_circle(TOKENS[i], 17, Color("d2b466"))
			draw_circle(TOKENS[i], 7, Color("fff0c3"))
	var gate := Color("72e0be") if collected.size() == 3 else Color("5c6b7b")
	draw_rect(Rect2(595, 505, 50, 50), gate, false, 4)
	draw_line(Vector2(609, 530), Vector2(632, 530), gate, 3)
	draw_line(Vector2(625, 523), Vector2(632, 530), gate, 3)
	draw_line(Vector2(625, 537), Vector2(632, 530), gate, 3)

func _panel(color: Color) -> StyleBoxFlat:
	var style := StyleBoxFlat.new()
	style.bg_color = color
	return style

func _save_feedback() -> void:
	if questions[0].selected == 0 or questions[1].selected == 0:
		feedback_label.text = "Choose an answer for both questions."
		return
	var record := {"build": ProjectSettings.get_setting("application/config/version"), "session": session_id, "question_version": 1, "profile": profile, "parameters": {"speed": player.speed, "acceleration": player.acceleration, "braking": player.braking}, "run": run_id, "seconds_played": snappedf(elapsed, 0.1), "completed": finished, "answers": {"stopping-preference": questions[0].get_item_text(questions[0].selected), "goal-readability": questions[1].get_item_text(questions[1].selected)}}
	feedback.append(record)
	feedback_label.text = "Saved profile %s. Compare, or download." % profile
	print("FEEDBACK_RECORDED ", JSON.stringify(record))
	_publish_state()

func _export_feedback() -> void:
	var data := JSON.stringify({"schema_version": 1, "build": ProjectSettings.get_setting("application/config/version"), "reactions": feedback}, "\t")
	if OS.has_feature("web"):
		JavaScriptBridge.download_buffer(data.to_utf8_buffer(), "feel-lab-reactions.json", "application/json")
	else:
		var file := FileAccess.open("user://feel-lab-reactions.json", FileAccess.WRITE)
		if file == null:
			feedback_label.text = "Could not write the reactions file."
			return
		file.store_string(data)
	feedback_label.text = "Exported %d reactions." % feedback.size()

func _publish_state() -> void:
	if OS.has_feature("web"):
		var data := {"ready": true, "profile": profile, "position": [player.position.x, player.position.y], "speed": player.velocity.length(), "collected": collected.size(), "finished": finished, "feedback_count": feedback.size()}
		JavaScriptBridge.eval("window.feelLabState = " + JSON.stringify(data), true)
