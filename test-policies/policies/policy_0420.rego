package risk.authentication.action.allow.policy_0420

# Auto-generated policy 420
# Package: risk.authentication.action.allow

# Metadata
metadata := {
    "policy_id": "0420",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0420_allowed = false
policy_0420_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0420_allowed if {
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
