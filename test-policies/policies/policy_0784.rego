package compliance.monitoring.action.validate.policy_0784

# Auto-generated policy 784
# Package: compliance.monitoring.action.validate

# Metadata
metadata := {
    "policy_id": "0784",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0784 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0784 {
    data.policies.compliance.enabled
}
allowed_0784 {
    input.user.active
    input.resource.public
}

# Utility function for user info
