package risk.enforcement.policy.deny.policy_0087

# Auto-generated policy 87
# Package: risk.enforcement.policy.deny

# Metadata
metadata := {
    "policy_id": "0087",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0087_allowed if {
    data.policies.risk.enabled
}
policy_0087_allowed if {
    input.user.role == "admin"
}
policy_0087_allowed if {
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
