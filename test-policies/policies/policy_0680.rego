package security.validation.resource.verify.policy_0680

# Auto-generated policy 680
# Package: security.validation.resource.verify

# Metadata
metadata := {
    "policy_id": "0680",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0680_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0680_allowed if {
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
