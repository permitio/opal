package risk.authorization.context.validate.policy_0689

# Auto-generated policy 689
# Package: risk.authorization.context.validate

# Metadata
metadata := {
    "policy_id": "0689",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0689_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0689_allowed if {
    data.policies.risk.enabled
}
policy_0689_allowed if {
    input.user.role == "admin"
}
policy_0689_allowed if {
    input.user.active
    input.resource.public
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
