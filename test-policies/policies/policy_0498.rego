package audit.authorization.action.check.core.policy_0498

# Auto-generated policy 498
# Package: audit.authorization.action.check.core

# Metadata
metadata := {
    "policy_id": "0498",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0498_allowed if {
    data.policies.audit.enabled
}
policy_0498_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0498_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0498_allowed if {
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
