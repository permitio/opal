package security.authentication.user.verify.helpers.policy_0285

# Auto-generated policy 285
# Package: security.authentication.user.verify.helpers

# Metadata
metadata := {
    "policy_id": "0285",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0285 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0285 = false
allowed_0285 {
    data.policies.security.enabled
}

# Utility function for user info
