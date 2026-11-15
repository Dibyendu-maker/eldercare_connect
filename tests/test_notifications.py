def test_notification_status_truthful(client):
    res = client.get("/api/notifications/status")
    assert res.status_code == 200
    data = res.json()
    assert "configured" in data
    assert "provider" in data
    assert data["provider"] == "Resend"
    # If not configured, message must state unconfigured mock mode
    if not data["configured"]:
        assert "not provided" in data["status_message"]

def test_trigger_notification_check(client, elderly_user_token):
    profile_id = elderly_user_token["profile_id"]
    token = elderly_user_token["token"]

    # Add medication with scheduled time
    client.post(
        f"/api/profiles/{profile_id}/medications",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Amlodipine",
            "dosage": "5mg",
            "schedule_times": ["08:00", "20:00"]
        }
    )

    # Trigger background evaluation check
    check_res = client.post(
        f"/api/notifications/trigger-check/{profile_id}",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert check_res.status_code == 200
    res_data = check_res.json()
    assert res_data["status"] == "check_completed"
    assert "total_evaluated" in res_data

    # Query notification logs
    logs_res = client.get(
        f"/api/notifications/logs/{profile_id}",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert logs_res.status_code == 200
    logs = logs_res.json()
    assert len(logs) > 0
