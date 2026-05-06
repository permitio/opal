package audit.enforcement.context.deny.core.policy_0493

# Auto-generated policy 493
# Package: audit.enforcement.context.deny.core

# Metadata
metadata := {
    "policy_id": "0493",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0493_allowed if {
    input.user.active
    input.resource.public
}
default policy_0493_allowed = false
policy_0493_allowed if {
    data.policies.audit.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
