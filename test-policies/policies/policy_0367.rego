package compliance.authentication.action.verify.policy_0367

# Auto-generated policy 367
# Package: compliance.authentication.action.verify

# Metadata
metadata := {
    "policy_id": "0367",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0367 {
    data.policies.compliance.enabled
}
approved_0367 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0367 = false
allowed_0367 {
    input.user.active
    input.resource.public
}

# Utility function for user info
