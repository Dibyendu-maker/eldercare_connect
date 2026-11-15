def test_medication_crud(client, elderly_user_token):
    profile_id = elderly_user_token["profile_id"]
    token = elderly_user_token["token"]

    # 1. Create medication
    res = client.post(
        f"/api/profiles/{profile_id}/medications",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Metformin",
            "dosage": "500mg",
            "form": "Tablet",
            "instructions": "Take with evening meal",
            "schedule_times": ["08:00", "20:00"],
            "frequency": "Twice daily",
            "prescribing_doctor": "Dr. Sarah Adams"
        }
    )
    assert res.status_code == 201
    med_data = res.json()
    assert med_data["name"] == "Metformin"
    assert med_data["schedule_times"] == ["08:00", "20:00"]
    assert med_data["next_dose"] is not None
    med_id = med_data["id"]

    # 2. Get medication
    get_res = client.get(
        f"/api/profiles/{profile_id}/medications/{med_id}",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert get_res.status_code == 200
    assert get_res.json()["name"] == "Metformin"

    # 3. Update medication
    up_res = client.put(
        f"/api/profiles/{profile_id}/medications/{med_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"dosage": "1000mg", "instructions": "Take with dinner and lots of water"}
    )
    assert up_res.status_code == 200
    assert up_res.json()["dosage"] == "1000mg"

    # 4. Delete (deactivate)
    del_res = client.delete(
        f"/api/profiles/{profile_id}/medications/{med_id}",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert del_res.status_code == 204

    # 5. List active excludes deleted
    list_res = client.get(
        f"/api/profiles/{profile_id}/medications",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert list_res.status_code == 200
    assert len(list_res.json()) == 0

def test_dose_tracking_and_duplicate_prevention(client, elderly_user_token):
    profile_id = elderly_user_token["profile_id"]
    token = elderly_user_token["token"]

    # Create medication
    med = client.post(
        f"/api/profiles/{profile_id}/medications",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Lisinopril",
            "dosage": "10mg",
            "schedule_times": ["09:00"]
        }
    ).json()
    med_id = med["id"]

    # Record first dose: TAKEN
    dose_res = client.post(
        f"/api/profiles/{profile_id}/medications/{med_id}/doses",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "scheduled_date": "2026-11-15",
            "scheduled_time": "09:00",
            "status": "taken",
            "notes": "Taken with glass of water"
        }
    )
    assert dose_res.status_code == 201
    assert dose_res.json()["status"] == "taken"

    # ATTEMPT DUPLICATE RECORD - MUST BE PREVENTED
    dup_res = client.post(
        f"/api/profiles/{profile_id}/medications/{med_id}/doses",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "scheduled_date": "2026-11-15",
            "scheduled_time": "09:00",
            "status": "missed"
        }
    )
    assert dup_res.status_code == 409
    assert "already recorded" in dup_res.json()["detail"]

    # Verify history
    hist_res = client.get(
        f"/api/profiles/{profile_id}/medications/doses/history",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert hist_res.status_code == 200
    history = hist_res.json()
    assert len(history) == 1
    assert history[0]["status"] == "taken"
