package security.authorization.context.deny.utils.policy_0299

# Auto-generated policy 299
# Package: security.authorization.context.deny.utils

# Metadata
metadata := {
    "policy_id": "0299",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0299_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0299_allowed if {
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
