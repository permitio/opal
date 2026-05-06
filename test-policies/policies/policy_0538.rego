package compliance.authorization.policy.check.policy_0538

# Auto-generated policy 538
# Package: compliance.authorization.policy.check

# Metadata
metadata := {
    "policy_id": "0538",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0538_allowed if {
    input.user.active
    input.resource.public
}
default policy_0538_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
