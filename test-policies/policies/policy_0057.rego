package audit.enforcement.context.verify.policy_0057

# Auto-generated policy 57
# Package: audit.enforcement.context.verify

# Metadata
metadata := {
    "policy_id": "0057",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0057_allowed if {
    data.policies.audit.enabled
}
policy_0057_allowed if {
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
