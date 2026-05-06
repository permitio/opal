package risk.monitoring.user.validate.policy_0327

# Auto-generated policy 327
# Package: risk.monitoring.user.validate

# Metadata
metadata := {
    "policy_id": "0327",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0327_allowed = false
policy_0327_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0327_allowed if {
    data.policies.risk.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
