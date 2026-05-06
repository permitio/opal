package audit.authorization.context.validate.policy_0565

# Auto-generated policy 565
# Package: audit.authorization.context.validate

# Metadata
metadata := {
    "policy_id": "0565",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0565_allowed if {
    data.policies.audit.enabled
}
default policy_0565_allowed = false
policy_0565_allowed if {
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
