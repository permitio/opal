package governance.enforcement.resource.check.policy_0169

# Auto-generated policy 169
# Package: governance.enforcement.resource.check

# Metadata
metadata := {
    "policy_id": "0169",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0169 = false
approved_0169 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0169 {
    data.policies.governance.enabled
}

# Utility function for user info
