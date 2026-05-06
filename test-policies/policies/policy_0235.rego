package compliance.authorization.user.check.helpers.policy_0235

# Auto-generated policy 235
# Package: compliance.authorization.user.check.helpers

# Metadata
metadata := {
    "policy_id": "0235",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0235 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0235 = false
allowed_0235 {
    data.policies.compliance.enabled
}

# Utility function for user info
