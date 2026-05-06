package audit.validation.action.deny.core.policy_0397

# Auto-generated policy 397
# Package: audit.validation.action.deny.core

# Metadata
metadata := {
    "policy_id": "0397",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0397_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0397_allowed if {
    input.user.active
    input.resource.public
}
policy_0397_allowed if {
    input.user.role == "admin"
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
