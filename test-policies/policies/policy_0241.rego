package risk.authentication.context.deny.policy_0241

# Auto-generated policy 241
# Package: risk.authentication.context.deny

# Metadata
metadata := {
    "policy_id": "0241",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0241_allowed if {
    input.user.role == "admin"
}
policy_0241_allowed if {
    input.user.active
    input.resource.public
}
policy_0241_allowed if {
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
