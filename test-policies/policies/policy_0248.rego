package compliance.authentication.policy.allow.helpers.policy_0248

# Auto-generated policy 248
# Package: compliance.authentication.policy.allow.helpers

# Metadata
metadata := {
    "policy_id": "0248",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0248 {
    data.policies.compliance.enabled
}
approved_0248 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0248 {
    input.user.active
    input.resource.public
}

# Utility function for user info
