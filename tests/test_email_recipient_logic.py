import pytest
import time
from unittest.mock import MagicMock, patch, ANY
from app.services.alert_service import AlertService
from app.services.email_service import EmailService
from app.core.models import Event
from app.db.repo import SQLiteAlertRepository, UserRepository

@pytest.fixture
def mock_repo():
    return MagicMock(spec=SQLiteAlertRepository)

@pytest.fixture
def mock_email_svc():
    return MagicMock(spec=EmailService)

@pytest.fixture
def mock_admin_repo():
    repo = MagicMock(spec=UserRepository)
    repo.list_users.return_value = []
    return repo

def test_alert_recipient_logic_fallback(mock_repo, mock_email_svc, mock_admin_repo):
    """If no users have emails, it should fall back to config.EMAIL_RECIPIENT."""
    with patch("app.config.EMAIL_RECIPIENT", "fallback@example.com"), \
         patch("app.config.EMAIL_ALERTS_ENABLED", True):
        
        svc = AlertService(mock_repo, mock_email_svc, mock_admin_repo)
        evt = Event(event_id="test", created_at="now", status="unauthorised", person_name=None, person_id=None, score=0.0, bbox_json=None, snapshot_path=None, clip_path=None, track_key=None)
        
        svc.trigger_unauthorised_alert(evt)
        time.sleep(0.1) # allow async thread to process 
        
        # Check that send_email was called with the fallback recipient
        mock_email_svc.send_email.assert_any_call(
            to="fallback@example.com",
            subject=ANY,
            body=ANY,
            sender=ANY,
            image_path=ANY
        )

def test_alert_recipient_logic_users(mock_repo, mock_email_svc, mock_admin_repo):
    """If users have emails, it should send to them and NOT use fallback."""
    mock_admin_repo.list_users.return_value = [
        {"username": "admin", "email": "admin@example.com"},
        {"username": "op", "email": "op@example.com"},
        {"username": "no-email", "email": None}
    ]
    
    with patch("app.config.EMAIL_RECIPIENT", "fallback@example.com"), \
         patch("app.config.EMAIL_ALERTS_ENABLED", True):
        
        svc = AlertService(mock_repo, mock_email_svc, mock_admin_repo)
        evt = Event(event_id="test", created_at="now", status="unauthorised", person_name=None, person_id=None, score=0.0, bbox_json=None, snapshot_path=None, clip_path=None, track_key=None)
        
        svc.trigger_unauthorised_alert(evt)
        time.sleep(0.1) # allow async thread to process 
        
        # Verify recipients
        calls = [call.kwargs['to'] for call in mock_email_svc.send_email.call_args_list]
        assert "admin@example.com" in calls
        assert "op@example.com" in calls
        assert "fallback@example.com" not in calls

def test_alert_recipient_logic_deduplication(mock_repo, mock_email_svc, mock_admin_repo):
    """Duplicate emails should be ignored."""
    mock_admin_repo.list_users.return_value = [
        {"username": "u1", "email": "same@example.com"},
        {"username": "u2", "email": "SAME@example.com "}, # Case and whitespace
    ]
    
    with patch("app.config.EMAIL_RECIPIENT", "fallback@example.com"), \
         patch("app.config.EMAIL_ALERTS_ENABLED", True):
        
        svc = AlertService(mock_repo, mock_email_svc, mock_admin_repo)
        evt = Event(event_id="test", created_at="now", status="unauthorised", person_name=None, person_id=None, score=0.0, bbox_json=None, snapshot_path=None, clip_path=None, track_key=None)
        
        svc.trigger_unauthorised_alert(evt)
        time.sleep(0.1) # allow async thread to process 
        
        # Should only be called once because they are the same recipient (strip and case-insensitive)
        assert mock_email_svc.send_email.call_count == 1
