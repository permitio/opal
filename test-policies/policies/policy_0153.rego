package audit.authorization.context.allow.policy_0153

# Auto-generated policy 153
# Package: audit.authorization.context.allow

# Metadata
metadata := {
    "policy_id": "0153",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0153 {
    input.user.role == "admin"
}
allowed_0153 {
    input.user.active
    input.resource.public
}
approved_0153 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0153 {
    data.policies.audit.enabled
}

# Utility function for user info
