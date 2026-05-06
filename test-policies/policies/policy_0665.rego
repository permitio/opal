package security.validation.policy.check.policy_0665

# Auto-generated policy 665
# Package: security.validation.policy.check

# Metadata
metadata := {
    "policy_id": "0665",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0665 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0665 {
    data.policies.security.enabled
}

# Utility function for user info
