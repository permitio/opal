package access.enforcement.action.validate.policy_0056

# Auto-generated policy 56
# Package: access.enforcement.action.validate

# Metadata
metadata := {
    "policy_id": "0056",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0056_allowed if {
    data.policies.access.enabled
}
policy_0056_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0056_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0056_allowed if {
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
