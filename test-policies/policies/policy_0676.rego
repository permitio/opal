package security.enforcement.policy.validate.policy_0676

# Auto-generated policy 676
# Package: security.enforcement.policy.validate

# Metadata
metadata := {
    "policy_id": "0676",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0676_allowed if {
    input.user.role == "admin"
}
policy_0676_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0676_allowed if {
    data.policies.security.enabled
}
default policy_0676_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
