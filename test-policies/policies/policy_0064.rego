package compliance.validation.action.check.core.policy_0064

# Auto-generated policy 64
# Package: compliance.validation.action.check.core

# Metadata
metadata := {
    "policy_id": "0064",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0064 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0064 {
    input.user.active
    input.resource.public
}
allowed_0064 {
    data.policies.compliance.enabled
}

# Utility function for user info
