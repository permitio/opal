package audit.enforcement.action.validate.policy_0221

# Auto-generated policy 221
# Package: audit.enforcement.action.validate

# Metadata
metadata := {
    "policy_id": "0221",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0221_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0221_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0221_allowed if {
    input.user.role == "admin"
}
default policy_0221_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
