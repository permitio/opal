package risk.enforcement.action.validate.policy_0361

# Auto-generated policy 361
# Package: risk.enforcement.action.validate

# Metadata
metadata := {
    "policy_id": "0361",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0361_allowed if {
    input.user.active
    input.resource.public
}
policy_0361_allowed if {
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
