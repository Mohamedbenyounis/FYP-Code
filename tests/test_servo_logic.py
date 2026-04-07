import pytest
import time
from unittest.mock import patch, MagicMock
from collections import namedtuple
from app.services.servo_service import ServoController

# Mock face bounding box matching SCRFD model output
BBox = namedtuple('BBox', ['x1', 'y1', 'x2', 'y2'])

@pytest.fixture
def controller():
    # Use a mock IP to prevent real network calls
    return ServoController(pi_ip="1.2.3.4", pi_port=5000)

def test_dead_zone_suppression(controller):
    """Verify that a face in the center zone does not trigger movement."""
    # Frame 640x480. Center is (320, 240).
    # With deadzone=0.35, the zone is [0.325, 0.675]
    # (0.5 +/- 0.175) -> X: [208, 432], Y: [156, 324]
    
    face_centered = BBox(300, 220, 340, 260) # Center: (320, 240)
    
    with patch('requests.get') as mock_get:
        moved = controller.compute_and_send(face_centered, 640, 480)
        assert moved is False
        mock_get.assert_not_called()

def test_direction_selection_pan(controller):
    """Verify correct pan direction selection for off-center faces."""
    # Face far left
    face_left = BBox(10, 220, 50, 260) # Center X: 30 / 640 = 0.046
    
    with patch('requests.get') as mock_get:
        mock_get.return_value.status_code = 200
        moved = controller.compute_and_send(face_left, 640, 480)
        assert moved is True
        mock_get.assert_called_once_with(
            "http://1.2.3.4:5000/move", params={"axis": "pan", "dir": "left"}, timeout=1.0
        )

def test_cooldown_enforcement(controller):
    """Verify that commands are blocked within the cooldown window."""
    face_left = BBox(10, 220, 50, 260)
    
    with patch('requests.get') as mock_get:
        mock_get.return_value.status_code = 200
        
        # First move success
        assert controller.compute_and_send(face_left, 640, 480) is True
        assert mock_get.call_count == 1
        
        # Immediate second move should fail (cooldown)
        assert controller.compute_and_send(face_left, 640, 480) is False
        assert mock_get.call_count == 1

def test_anti_oscillation_block(controller):
    """Verify that immediate reversals are blocked."""
    face_left = BBox(10, 220, 50, 260)
    # Face at X=0.75 (outside deadzone 0.675, but within extreme 0.85)
    face_right = BBox(460, 220, 500, 260) 
    
    with patch('requests.get') as mock_get:
        mock_get.return_value.status_code = 200
        
        # Move left
        controller.compute_and_send(face_left, 640, 480)
        
        # Fast-forward past cooldown but still within oscillation window
        # (Default lockout is 1.2s, default cooldown 0.5s)
        with patch('time.monotonic', return_value=time.monotonic() + 0.6):
            # Attempt to move right should be blocked
            moved = controller.compute_and_send(face_right, 640, 480)
            assert moved is False
            # Check mock_get wasn't called a second time
            assert mock_get.call_count == 1

def test_anti_oscillation_override_extreme(controller):
    """Verify that extreme errors override the anti-oscillation block."""
    face_left = BBox(10, 220, 50, 260)
    # Face at the far right edge (Extreme > 0.85)
    face_extreme_right = BBox(630, 220, 640, 260) 
    
    with patch('requests.get') as mock_get:
        mock_get.return_value.status_code = 200
        
        # Move left
        controller.compute_and_send(face_left, 640, 480)
        
        # Within oscillation window
        with patch('time.monotonic', return_value=time.monotonic() + 0.6):
            # Extreme right should override the lockout
            moved = controller.compute_and_send(face_extreme_right, 640, 480)
            assert moved is True
            assert mock_get.call_count == 2
            assert mock_get.call_args[1]['params']['dir'] == "right"

def test_http_timeout_handling(controller):
    """Verify resilient handling of network timeouts."""
    import requests
    face_left = BBox(10, 220, 50, 260)
    
    with patch('requests.get', side_effect=requests.exceptions.Timeout):
        moved = controller.compute_and_send(face_left, 640, 480)
        assert moved is False

def test_http_error_response(controller):
    """Verify handling of 5xx errors from the Pi service."""
    face_left = BBox(10, 220, 50, 260)
    
    with patch('requests.get') as mock_get:
        mock_get.return_value.status_code = 500
        moved = controller.compute_and_send(face_left, 640, 480)
        assert moved is False
