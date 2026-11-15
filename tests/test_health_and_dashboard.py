def test_health_profile_and_emergency_card(client, elderly_user_token):
    profile_id = elderly_user_token["profile_id"]
    token = elderly_user_token["token"]

    # 1. Fetch initial health profile
    res = client.get(
        f"/api/profiles/{profile_id}/health",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert res.status_code == 200
    hp = res.json()
    assert "disclaimer" in hp
    assert "diagnostic or prescribing" in hp["disclaimer"]

    # 2. Update health profile with allergies and emergency contacts
    up_res = client.put(
        f"/api/profiles/{profile_id}/health",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "blood_type": "O+",
            "allergies": ["Penicillin", "Sulfa drugs"],
            "medical_conditions": ["Type 2 Diabetes", "Mild Hypertension"],
            "emergency_notes": "Carries glucose tablets in purse.",
            "emergency_contacts": [
                {
                    "name": "Jane Cooper",
                    "relationship": "Daughter",
                    "phone": "+1-555-0999",
                    "priority": 1
                }
            ]
        }
    )
    assert up_res.status_code == 200
    updated = up_res.json()
    assert updated["blood_type"] == "O+"
    assert "Penicillin" in updated["allergies"]
    assert len(updated["emergency_contacts"]) == 1

def test_dashboard_summary_calculation(client, elderly_user_token):
    profile_id = elderly_user_token["profile_id"]
    token = elderly_user_token["token"]

    # Add 2 medications
    med1 = client.post(
        f"/api/profiles/{profile_id}/medications",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Aspirin", "dosage": "81mg", "schedule_times": ["08:00"]}
    ).json()

    med2 = client.post(
        f"/api/profiles/{profile_id}/medications",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Multivitamin", "dosage": "1 Tab", "schedule_times": ["12:00"]}
    ).json()

    # Log 1 as taken
    client.post(
        f"/api/profiles/{profile_id}/medications/{med1['id']}/doses",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "scheduled_date": "2026-11-15",
            "scheduled_time": "08:00",
            "status": "taken"
        }
    )

    # Check dashboard
    dash_res = client.get(
        f"/api/profiles/{profile_id}/dashboard",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert dash_res.status_code == 200
    dash = dash_res.json()
    assert dash["total_today_doses"] == 2
    assert dash["taken_count"] == 1
    assert dash["pending_count"] == 1
    assert dash["missed_count"] == 0
    assert len(dash["today_doses"]) == 2
