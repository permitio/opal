package risk.authentication.resource.allow.policy_0933

# Auto-generated policy 933
# Package: risk.authentication.resource.allow

# Metadata
metadata := {
    "policy_id": "0933",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0933_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0933_allowed if {
    input.user.role == "admin"
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
