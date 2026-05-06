package security.monitoring.policy.validate.utils.policy_0701

# Auto-generated policy 701
# Package: security.monitoring.policy.validate.utils

# Metadata
metadata := {
    "policy_id": "0701",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0701 {
    data.policies.security.enabled
}
allowed_0701 {
    input.user.active
    input.resource.public
}
approved_0701 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
