package compliance.authorization.context.verify.policy_0332

# Auto-generated policy 332
# Package: compliance.authorization.context.verify

# Metadata
metadata := {
    "policy_id": "0332",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0332_allowed = false
policy_0332_allowed if {
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
