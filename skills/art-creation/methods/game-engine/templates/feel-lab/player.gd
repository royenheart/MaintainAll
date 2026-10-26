extends CharacterBody2D

var speed: float = 240.0
var acceleration: float = 2600.0
var braking: float = 3200.0
var enabled: bool = true
var tint: Color = Color("72e0be")

func _ready() -> void:
	var collision := CollisionShape2D.new()
	var circle := CircleShape2D.new()
	circle.radius = 13.0
	collision.shape = circle
	add_child(collision)
	motion_mode = CharacterBody2D.MOTION_MODE_FLOATING

func _physics_process(delta: float) -> void:
	if not enabled:
		velocity = Vector2.ZERO
		return
	var direction := Vector2(
		float(Input.is_physical_key_pressed(KEY_D) or Input.is_physical_key_pressed(KEY_RIGHT)) - float(Input.is_physical_key_pressed(KEY_A) or Input.is_physical_key_pressed(KEY_LEFT)),
		float(Input.is_physical_key_pressed(KEY_S) or Input.is_physical_key_pressed(KEY_DOWN)) - float(Input.is_physical_key_pressed(KEY_W) or Input.is_physical_key_pressed(KEY_UP))
	).normalized()
	var rate: float = acceleration if direction != Vector2.ZERO else braking
	velocity = velocity.move_toward(direction * speed, rate * delta)
	move_and_slide()
	queue_redraw()

func _draw() -> void:
	draw_circle(Vector2.ZERO, 18.0, Color(tint, 0.12))
	draw_circle(Vector2.ZERO, 13.0, tint)
	if velocity.length() > 2.0:
		draw_line(Vector2.ZERO, velocity.normalized() * 19.0, Color("172c34"), 3.0, true)
