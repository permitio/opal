package risk.validation.policy.allow.policy_0910

# Auto-generated policy 910
# Package: risk.validation.policy.allow

# Metadata
metadata := {
    "policy_id": "0910",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0910_allowed if {
    input.user.active
    input.resource.public
}
policy_0910_allowed if {
    data.policies.risk.enabled
}
policy_0910_allowed if {
    input.user.role == "admin"
}
default policy_0910_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
