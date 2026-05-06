package access.validation.policy.verify.policy_0621

# Auto-generated policy 621
# Package: access.validation.policy.verify

# Metadata
metadata := {
    "policy_id": "0621",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0621 {
    data.policies.access.enabled
}
approved_0621 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
