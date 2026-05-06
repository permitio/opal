package audit.authentication.user.deny.policy_0438

# Auto-generated policy 438
# Package: audit.authentication.user.deny

# Metadata
metadata := {
    "policy_id": "0438",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0438_allowed if {
    input.user.active
    input.resource.public
}
policy_0438_allowed if {
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
