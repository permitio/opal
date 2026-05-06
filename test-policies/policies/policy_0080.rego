package security.authentication.action.validate.policy_0080

# Auto-generated policy 80
# Package: security.authentication.action.validate

# Metadata
metadata := {
    "policy_id": "0080",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0080_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0080_allowed if {
    input.user.active
    input.resource.public
}
policy_0080_allowed if {
    input.user.role == "admin"
}
policy_0080_allowed if {
    data.policies.security.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
