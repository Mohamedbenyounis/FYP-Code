import time
import requests
import logging
from app import config

class ServoController:
    """
    Latency-tolerant servo controller for coarse face re-centering.
    Implements Step-Wait logic to handle RTSP delay with enhanced logging
    and anti-oscillation safeguards.
    """

    def __init__(self, pi_ip: str = None, pi_port: int = None):
        self.pi_ip = pi_ip or config.SERVO_PI_IP
        self.pi_port = pi_port or config.SERVO_PI_PORT
        self.base_url = f"http://{self.pi_ip}:{self.pi_port}"
        self.logger = logging.getLogger("ServoController")
        
        # Configuration from app.config
        self.dead_zone_ratio = config.SERVO_DEADZONE_RATIO
        self.cooldown_period = config.SERVO_COOLDOWN_MS / 1000.0
        self.oscillation_window = config.SERVO_OPPOSITE_LOCKOUT_MS / 1000.0

        # Derived dead zone bounds (centered)
        half_zone = self.dead_zone_ratio / 2
        self.dead_zone_min = 0.5 - half_zone
        self.dead_zone_max = 0.5 + half_zone
        
        # Error threshold for overriding anti-oscillation (extreme edges)
        # Allows immediate recovery if the face is nearly out of view
        self.extreme_threshold_min = 0.15
        self.extreme_threshold_max = 0.85

        # Timing state
        self.last_command_time = 0
        
        # Anti-oscillation state
        self.last_move_dir_pan = None   # 'left' or 'right'
        self.last_move_dir_tilt = None  # 'up' or 'down'
        self.last_move_time_pan = 0
        self.last_move_time_tilt = 0

    def compute_and_send(self, face_bbox, frame_w: int, frame_h: int) -> bool:
        """
        Takes a face bounding box and decides whether to send a movement command.
        Decisions are based on normalized coordinates, dead zones, and timing locks.
        """
        if face_bbox is None:
            return False

        now = time.monotonic()
        
        # 1. Global Cooldown Check
        if now - self.last_command_time < self.cooldown_period:
            self.logger.debug("SERVO_SUPPRESS [COOLDOWN] Wait time remaining: %.2fs", 
                              self.cooldown_period - (now - self.last_command_time))
            return False

        # 2. Extract and Normalize Face Center
        # face_bbox is a Detection object, which has a .bbox (BoundingBox)
        bbox = face_bbox.bbox
        center_x, center_y = bbox.center
        
        # Normalize to [0.0, 1.0]
        center_x = center_x / frame_w
        center_y = center_y / frame_h
        
        cmd_axis = None
        cmd_dir = None

        # 3. Decision Logic - Pan (Horizontal)
        if center_x < self.dead_zone_min:
            # Face is to the LEFT from camera view, move camera LEFT to center it
            target_dir = "left"
            if self._is_move_allowed("pan", target_dir, center_x, now):
                cmd_axis = "pan"
                cmd_dir = "left"
        elif center_x > self.dead_zone_max:
            target_dir = "right"
            if self._is_move_allowed("pan", target_dir, center_x, now):
                cmd_axis = "pan"
                cmd_dir = "right"

        # 4. Decision Logic - Tilt (Vertical)
        # We prioritize horizontal correction to avoid simultaneous axis noise,
        # but check Tilt if Pan didn't trigger.
        if not cmd_axis:
            if center_y < self.dead_zone_min:
                # Face is UP from camera view (low Y), move camera to correct it
                target_dir = "down"
                if self._is_move_allowed("tilt", target_dir, center_y, now):
                    cmd_axis = "tilt"
                    cmd_dir = "down"
            elif center_y > self.dead_zone_max:
                # Face is DOWN from camera view (high Y), move camera to correct it
                target_dir = "up"
                if self._is_move_allowed("tilt", target_dir, center_y, now):
                    cmd_axis = "tilt"
                    cmd_dir = "up"

        # 5. Deadzone check (if neither axis triggered)
        if not cmd_axis:
            self.logger.debug("SERVO_SUPPRESS [DEADZONE] Face at (%.2f, %.2f) is within center zone.", 
                              center_x, center_y)
            return False

        # 6. Execute Command
        success = self._send_request(cmd_axis, cmd_dir)
        if success:
            self.last_command_time = now
            if cmd_axis == "pan":
                self.last_move_dir_pan = cmd_dir
                self.last_move_time_pan = now
            else:
                self.last_move_dir_tilt = cmd_dir
                self.last_move_time_tilt = now
            return True
        
        return False

    def _is_move_allowed(self, axis: str, target_dir: str, normalized_val: float, now: float) -> bool:
        """
        Anti-oscillation safeguard. Prevents immediate reversals unless the error is extreme.
        """
        if axis == "pan":
            last_dir = self.last_move_dir_pan
            last_time = self.last_move_time_pan
        else:
            last_dir = self.last_move_dir_tilt
            last_time = self.last_move_time_tilt

        # If no previous move or enough time passed, allow
        if last_dir is None or (now - last_time > self.oscillation_window):
            return True

        # If same direction, allow (incremental tracking)
        if target_dir == last_dir:
            return True

        # If reversal, check if it's an extreme error (e.g. face at furthest edge)
        is_extreme = normalized_val < self.extreme_threshold_min or normalized_val > self.extreme_threshold_max
        if is_extreme:
            self.logger.warning("SERVO_OVERRIDE [EXTREME] Reversal gap too large (%.2f). Moving %s %s.", 
                                normalized_val, axis, target_dir)
            return True

        self.logger.info("SERVO_SUPPRESS [OSCILLATION] Ignoring reversed %s command to %s.", 
                         axis, target_dir)
        return False

    def _send_request(self, axis: str, direction: str) -> bool:
        """Sends the HTTP movement command to the Raspberry Pi service."""
        try:
            url = f"{self.base_url}/move"
            params = {"axis": axis, "dir": direction}
            
            self.logger.info("SERVO_SEND [%s %s] Target: %s", axis.upper(), direction.upper(), self.base_url)
            
            resp = requests.get(url, params=params, timeout=1.0)
            if resp.status_code == 200:
                return True
            else:
                self.logger.error("SERVO_ERROR [HTTP %d] Pi service rejected command: %s", 
                                  resp.status_code, resp.text)
        except requests.exceptions.Timeout:
            self.logger.error("SERVO_ERROR [TIMEOUT] Pi service at %s timed out.", self.base_url)
        except requests.exceptions.ConnectionError:
            self.logger.error("SERVO_ERROR [CONN] Could not reach Pi service at %s.", self.base_url)
        except Exception as e:
            self.logger.error("SERVO_ERROR [UNEXPECTED] %s", str(e))
        
        return False
