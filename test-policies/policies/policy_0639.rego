package audit.validation.context.check.data.policy_0639

# Auto-generated policy 639
# Package: audit.validation.context.check.data

# Metadata
metadata := {
    "policy_id": "0639",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0639_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0639_allowed if {
    data.policies.audit.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
