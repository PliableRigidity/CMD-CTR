from backend.app.services.core_calendar_service import CalendarAuthError, _provider_error


def test_expired_google_grant_is_safe_auth_error():
    error = _provider_error(Exception(("invalid_grant: Bad Request", {"error": "invalid_grant"})))
    assert isinstance(error, CalendarAuthError)
    assert "reconnect Google Calendar" in str(error)
    assert "invalid_grant" not in str(error)
