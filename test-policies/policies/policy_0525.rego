package access.validation.user.allow.policy_0525

# Auto-generated policy 525
# Package: access.validation.user.allow

# Metadata
metadata := {
    "policy_id": "0525",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0525_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0525_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
