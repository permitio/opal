package access.authentication.action.allow.core.policy_0558

# Auto-generated policy 558
# Package: access.authentication.action.allow.core

# Metadata
metadata := {
    "policy_id": "0558",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0558 {
    input.user.active
    input.resource.public
}
approved_0558 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0558 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0558 {
    data.policies.access.enabled
}

# Utility function for user info
