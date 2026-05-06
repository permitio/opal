package risk.enforcement.action.validate.policy_0757

# Auto-generated policy 757
# Package: risk.enforcement.action.validate

# Metadata
metadata := {
    "policy_id": "0757",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0757_allowed if {
    input.user.role == "admin"
}
policy_0757_allowed if {
    data.policies.risk.enabled
}
policy_0757_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0757_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
