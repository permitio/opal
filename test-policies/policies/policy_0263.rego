package audit.enforcement.resource.deny.policy_0263

# Auto-generated policy 263
# Package: audit.enforcement.resource.deny

# Metadata
metadata := {
    "policy_id": "0263",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0263_allowed if {
    data.policies.audit.enabled
}
policy_0263_allowed if {
    input.user.active
    input.resource.public
}
default policy_0263_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
