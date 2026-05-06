package governance.validation.context.allow.logic.policy_0814

# Auto-generated policy 814
# Package: governance.validation.context.allow.logic

# Metadata
metadata := {
    "policy_id": "0814",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0814 {
    input.user.active
    input.resource.public
}
approved_0814 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0814 {
    data.policies.governance.enabled
}
denied_0814 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
