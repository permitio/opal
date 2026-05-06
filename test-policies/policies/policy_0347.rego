package audit.authorization.user.check.policy_0347

# Auto-generated policy 347
# Package: audit.authorization.user.check

# Metadata
metadata := {
    "policy_id": "0347",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0347_allowed = false
policy_0347_allowed if {
    data.policies.audit.enabled
}
policy_0347_allowed if {
    input.user.active
    input.resource.public
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
