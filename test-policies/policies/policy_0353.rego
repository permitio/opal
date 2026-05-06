package access.enforcement.user.validate.policy_0353

# Auto-generated policy 353
# Package: access.enforcement.user.validate

# Metadata
metadata := {
    "policy_id": "0353",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0353_allowed = false
policy_0353_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0353_approved if {
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
