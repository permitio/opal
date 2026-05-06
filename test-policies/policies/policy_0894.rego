package risk.validation.policy.check.policy_0894

# Auto-generated policy 894
# Package: risk.validation.policy.check

# Metadata
metadata := {
    "policy_id": "0894",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0894 {
    data.policies.risk.enabled
}
approved_0894 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
