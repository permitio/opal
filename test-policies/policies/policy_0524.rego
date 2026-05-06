package compliance.enforcement.policy.deny.policy_0524

# Auto-generated policy 524
# Package: compliance.enforcement.policy.deny

# Metadata
metadata := {
    "policy_id": "0524",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0524 {
    input.user.active
    input.resource.public
}
approved_0524 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0524 = false
allowed_0524 {
    data.policies.compliance.enabled
}

# Utility function for user info
