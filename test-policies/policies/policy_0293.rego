package audit.validation.context.allow.policy_0293

# Auto-generated policy 293
# Package: audit.validation.context.allow

# Metadata
metadata := {
    "policy_id": "0293",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0293 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0293 {
    data.policies.audit.enabled
}
allowed_0293 {
    input.user.active
    input.resource.public
}

# Utility function for user info
