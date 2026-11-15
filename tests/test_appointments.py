def test_appointment_crud_and_cancellation(client, elderly_user_token):
    profile_id = elderly_user_token["profile_id"]
    token = elderly_user_token["token"]

    # 1. Create appointment
    res = client.post(
        f"/api/profiles/{profile_id}/appointments",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "doctor_name": "Dr. Emily Watson",
            "specialty": "Cardiology",
            "appointment_date": "2026-11-20",
            "appointment_time": "14:30",
            "location": "City General Hospital, Suite 402",
            "contact_number": "+1-555-8888",
            "notes": "Follow-up echocardiogram review"
        }
    )
    assert res.status_code == 201
    apt = res.json()
    assert apt["doctor_name"] == "Dr. Emily Watson"
    assert apt["status"] == "scheduled"
    apt_id = apt["id"]

    # 2. List appointments
    list_res = client.get(
        f"/api/profiles/{profile_id}/appointments",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert list_res.status_code == 200
    assert len(list_res.json()) >= 1

    # 3. Update appointment
    up_res = client.put(
        f"/api/profiles/{profile_id}/appointments/{apt_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"notes": "Bring prior bloodwork results"}
    )
    assert up_res.status_code == 200
    assert up_res.json()["notes"] == "Bring prior bloodwork results"

    # 4. Cancel appointment
    can_res = client.post(
        f"/api/profiles/{profile_id}/appointments/{apt_id}/cancel",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert can_res.status_code == 200
    assert can_res.json()["status"] == "cancelled"

def test_appointment_reminder_dispatch(client, elderly_user_token):
    profile_id = elderly_user_token["profile_id"]
    token = elderly_user_token["token"]

    apt = client.post(
        f"/api/profiles/{profile_id}/appointments",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "doctor_name": "Dr. Davis",
            "specialty": "Geriatrics",
            "appointment_date": "2026-11-22",
            "appointment_time": "10:00",
            "location": "Main Clinic"
        }
    ).json()

    # Trigger reminder
    rem_res = client.post(
        f"/api/profiles/{profile_id}/appointments/{apt['id']}/send-reminder",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert rem_res.status_code == 200
    # Because RESEND_API_KEY is not configured in local test, it truthfully returns mocked_no_key
    data = rem_res.json()
    assert data["status"] in ("mocked_no_key", "sent")

    # Repeat should be skipped due to duplicate prevention
    dup_res = client.post(
        f"/api/profiles/{profile_id}/appointments/{apt['id']}/send-reminder",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert dup_res.status_code == 200
    assert dup_res.json()["status"] == "duplicate_skipped"
