package governance.validation.context.deny.helpers.policy_0488

# Auto-generated policy 488
# Package: governance.validation.context.deny.helpers

# Metadata
metadata := {
    "policy_id": "0488",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0488_allowed if {
    input.user.role == "admin"
}
policy_0488_allowed if {
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
