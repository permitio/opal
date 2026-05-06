package governance.enforcement.resource.verify.policy_0959

# Auto-generated policy 959
# Package: governance.enforcement.resource.verify

# Metadata
metadata := {
    "policy_id": "0959",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0959 {
    data.policies.governance.enabled
}
default allowed_0959 = false
approved_0959 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0959 {
    input.user.active
    input.resource.public
}

# Utility function for user info
