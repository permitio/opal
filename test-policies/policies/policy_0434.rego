package compliance.authorization.user.verify.policy_0434

# Auto-generated policy 434
# Package: compliance.authorization.user.verify

# Metadata
metadata := {
    "policy_id": "0434",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0434_allowed = false
policy_0434_allowed if {
    data.policies.compliance.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
