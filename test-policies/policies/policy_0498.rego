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
allowed_0498 {
    data.policies.audit.enabled
}
approved_0498 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0498 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0498 {
    input.user.active
    input.resource.public
}

# Utility function for user info
