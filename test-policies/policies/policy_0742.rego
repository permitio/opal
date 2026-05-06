package risk.enforcement.policy.validate.policy_0742

# Auto-generated policy 742
# Package: risk.enforcement.policy.validate

# Metadata
metadata := {
    "policy_id": "0742",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0742_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0742_allowed = false
policy_0742_allowed if {
    input.user.role == "admin"
}
policy_0742_approved if {
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
