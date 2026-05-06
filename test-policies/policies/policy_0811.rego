package risk.authorization.resource.verify.policy_0811

# Auto-generated policy 811
# Package: risk.authorization.resource.verify

# Metadata
metadata := {
    "policy_id": "0811",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0811_allowed if {
    data.policies.risk.enabled
}
policy_0811_allowed if {
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
