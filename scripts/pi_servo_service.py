#!/usr/bin/env python3
"""
SecureVision - Pi-Side Servo Service
To be run on the Raspberry Pi with pigpio daemon active.
"""

import time
import pigpio
from flask import Flask, request, jsonify

app = Flask(__name__)

# --- Configuration ---
PAN_PIN = 18
TILT_PIN = 19
MIN_ANGLE = 20
MAX_ANGLE = 160
STEP_SIZE = 1  # Degrees per command

# --- State ---
# Start both at center
pan_angle = 90
tilt_angle = 90

# --- Pigpio Setup ---
pi = pigpio.pi()
if not pi.connected:
    print("Error: Could not connect to pigpiod. Is the daemon running? (sudo pigpiod)")
    exit(1)

def angle_to_pulse(angle):
    """Convert 0-180 angle to 500-2500 pulse width (standard servos)."""
    return 500 + (angle / 180.0) * 2000

def set_servo_angle(pin, angle):
    """Set the pulse width for a given pin based on angle."""
    pulse = angle_to_pulse(angle)
    pi.set_servo_pulsewidth(pin, pulse)

# Initialize positions
set_servo_angle(PAN_PIN, pan_angle)
set_servo_angle(TILT_PIN, tilt_angle)

@app.route('/status', methods=['GET'])
def get_status():
    return jsonify({
        "pan": pan_angle,
        "tilt": tilt_angle,
        "min_limit": MIN_ANGLE,
        "max_limit": MAX_ANGLE
    })

@app.route('/move', methods=['GET'])
def move_servo():
    global pan_angle, tilt_angle
    
    axis = request.args.get('axis', '').lower()
    direction = request.args.get('dir', '').lower()
    
    if not axis or not direction:
        return jsonify({"error": "Missing axis or dir"}), 400

    moved = False
    if axis == 'pan':
        if direction == 'left':
            pan_angle = min(MAX_ANGLE, pan_angle + STEP_SIZE)
            moved = True
        elif direction == 'right':
            pan_angle = max(MIN_ANGLE, pan_angle - STEP_SIZE)
            moved = True
            
    elif axis == 'tilt':
        if direction == 'up':
            tilt_angle = min(MAX_ANGLE, tilt_angle + STEP_SIZE)
            moved = True
        elif direction == 'down':
            tilt_angle = max(MIN_ANGLE, tilt_angle - STEP_SIZE)
            moved = True

    if moved:
        if axis == 'pan':
            set_servo_angle(PAN_PIN, pan_angle)
        else:
            set_servo_angle(TILT_PIN, tilt_angle)
            
        return jsonify({
            "status": "moved",
            "axis": axis,
            "new_angle": pan_angle if axis == 'pan' else tilt_angle
        })
    
    return jsonify({"status": "no_change", "reason": "invalid_axis_or_dir"}), 400

if __name__ == '__main__':
    print(f"SecureVision Servo Service starting...")
    print(f"Pan Pin: {PAN_PIN}, Tilt Pin: {TILT_PIN}")
    print(f"Limits: {MIN_ANGLE} to {MAX_ANGLE}")
    try:
        # Listen on all interfaces so the laptop can reach it
        app.run(host='0.0.0.0', port=5000, debug=False)
    finally:
        # Clean shutdown: stop pulses
        pi.set_servo_pulsewidth(PAN_PIN, 0)
        pi.set_servo_pulsewidth(TILT_PIN, 0)
        pi.stop()
