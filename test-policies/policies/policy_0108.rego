package risk.enforcement.policy.check.policy_0108

# Auto-generated policy 108
# Package: risk.enforcement.policy.check

# Metadata
metadata := {
    "policy_id": "0108",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0108_allowed = false
policy_0108_allowed if {
    input.user.active
    input.resource.public
}
policy_0108_allowed if {
    input.user.role == "admin"
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
