package audit.authentication.action.check.core.policy_0100

# Auto-generated policy 100
# Package: audit.authentication.action.check.core

# Metadata
metadata := {
    "policy_id": "0100",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0100_allowed = false
policy_0100_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0100_allowed if {
    data.policies.audit.enabled
}
policy_0100_allowed if {
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
