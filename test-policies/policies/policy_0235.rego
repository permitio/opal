package compliance.authorization.user.check.helpers.policy_0235

# Auto-generated policy 235
# Package: compliance.authorization.user.check.helpers

# Metadata
metadata := {
    "policy_id": "0235",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0235_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0235_allowed = false
policy_0235_allowed if {
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
