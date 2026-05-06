package risk.authentication.context.verify.policy_0548

# Auto-generated policy 548
# Package: risk.authentication.context.verify

# Metadata
metadata := {
    "policy_id": "0548",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0548_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0548_allowed if {
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
