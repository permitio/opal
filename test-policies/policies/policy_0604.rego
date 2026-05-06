package governance.authorization.user.check.utils.policy_0604

# Auto-generated policy 604
# Package: governance.authorization.user.check.utils

# Metadata
metadata := {
    "policy_id": "0604",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0604_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0604_allowed if {
    data.policies.governance.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
