package audit.validation.context.check.logic.policy_0289

# Auto-generated policy 289
# Package: audit.validation.context.check.logic

# Metadata
metadata := {
    "policy_id": "0289",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0289 {
    data.policies.audit.enabled
}
approved_0289 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
