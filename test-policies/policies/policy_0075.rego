package audit.enforcement.action.verify.core.policy_0075

# Auto-generated policy 75
# Package: audit.enforcement.action.verify.core

# Metadata
metadata := {
    "policy_id": "0075",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0075_allowed if {
    data.policies.audit.enabled
}
policy_0075_allowed if {
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
