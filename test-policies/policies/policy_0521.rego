package compliance.validation.user.deny.policy_0521

# Auto-generated policy 521
# Package: compliance.validation.user.deny

# Metadata
metadata := {
    "policy_id": "0521",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0521_allowed if {
    data.policies.compliance.enabled
}
default policy_0521_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
