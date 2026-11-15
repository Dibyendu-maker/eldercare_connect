def test_unrelated_user_cannot_access_profile(client, elderly_user_token, unrelated_user_token):
    profile_id = elderly_user_token["profile_id"]
    unrelated_token = unrelated_user_token["token"]

    # Try to view dashboard
    res = client.get(
        f"/api/profiles/{profile_id}/dashboard",
        headers={"Authorization": f"Bearer {unrelated_token}"}
    )
    assert res.status_code == 403
    assert "Access denied" in res.json()["detail"]

    # Try to view medications
    res = client.get(
        f"/api/profiles/{profile_id}/medications",
        headers={"Authorization": f"Bearer {unrelated_token}"}
    )
    assert res.status_code == 403

def test_care_circle_invite_accept_and_access(client, elderly_user_token, caretaker_user_token, unrelated_user_token):
    profile_id = elderly_user_token["profile_id"]
    elderly_token = elderly_user_token["token"]
    caretaker_token = caretaker_user_token["token"]

    # 1. Elderly creates invite passcode
    invite_res = client.post(
        f"/api/profiles/{profile_id}/invites",
        headers={"Authorization": f"Bearer {elderly_token}"},
        json={
            "intended_role": "caretaker",
            "intended_relationship": "Home Care Nurse",
            "permissions": "full_access"
        }
    )
    assert invite_res.status_code == 201
    invite_code = invite_res.json()["invite_code"]

    # 2. Caretaker joins using passcode
    join_res = client.post(
        "/api/profiles/join",
        headers={"Authorization": f"Bearer {caretaker_token}"},
        json={"invite_code": invite_code}
    )
    assert join_res.status_code == 200
    assert join_res.json()["role"] == "caretaker"

    # 3. Caretaker now has access to the profile dashboard
    dash_res = client.get(
        f"/api/profiles/{profile_id}/dashboard",
        headers={"Authorization": f"Bearer {caretaker_token}"}
    )
    assert dash_res.status_code == 200

    # 4. Attempting to reuse passcode fails
    reuse_res = client.post(
        "/api/profiles/join",
        headers={"Authorization": f"Bearer {unrelated_user_token['token']}"},
        json={"invite_code": invite_code}
    )
    assert reuse_res.status_code == 400
    assert "already been used" in reuse_res.json()["detail"]

def test_revocation_removes_access(client, elderly_user_token, family_user_token):
    profile_id = elderly_user_token["profile_id"]
    elderly_token = elderly_user_token["token"]
    family_token = family_user_token["token"]

    # Generate invite & join
    inv = client.post(
        f"/api/profiles/{profile_id}/invites",
        headers={"Authorization": f"Bearer {elderly_token}"},
        json={"intended_role": "family", "intended_relationship": "Son"}
    ).json()

    client.post(
        "/api/profiles/join",
        headers={"Authorization": f"Bearer {family_token}"},
        json={"invite_code": inv["invite_code"]}
    )

    # Check members
    members = client.get(
        f"/api/profiles/{profile_id}/circle/members",
        headers={"Authorization": f"Bearer {elderly_token}"}
    ).json()
    member_id = [m["id"] for m in members if m["user_id"] == family_user_token["user"]["id"]][0]

    # Revoke member
    rev_res = client.delete(
        f"/api/profiles/{profile_id}/circle/members/{member_id}",
        headers={"Authorization": f"Bearer {elderly_token}"}
    )
    assert rev_res.status_code == 204

    # Access is now forbidden
    denied_res = client.get(
        f"/api/profiles/{profile_id}/dashboard",
        headers={"Authorization": f"Bearer {family_token}"}
    )
    assert denied_res.status_code == 403
