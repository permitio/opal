package governance.enforcement.resource.allow.policy_0442

# Auto-generated policy 442
# Package: governance.enforcement.resource.allow

# Metadata
metadata := {
    "policy_id": "0442",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0442 {
    data.policies.governance.enabled
}
allowed_0442 {
    input.user.active
    input.resource.public
}
approved_0442 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
