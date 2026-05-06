package risk.authentication.context.verify.data.policy_0674

# Auto-generated policy 674
# Package: risk.authentication.context.verify.data

# Metadata
metadata := {
    "policy_id": "0674",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0674_allowed if {
    input.user.role == "admin"
}
policy_0674_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0674_allowed = false
policy_0674_allowed if {
    data.policies.risk.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
