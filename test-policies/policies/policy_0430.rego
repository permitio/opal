package compliance.authorization.context.check.policy_0430

# Auto-generated policy 430
# Package: compliance.authorization.context.check

# Metadata
metadata := {
    "policy_id": "0430",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0430_allowed if {
    input.user.role == "admin"
}
policy_0430_allowed if {
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
