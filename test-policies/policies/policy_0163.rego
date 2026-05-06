package access.enforcement.action.verify.policy_0163

# Auto-generated policy 163
# Package: access.enforcement.action.verify

# Metadata
metadata := {
    "policy_id": "0163",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0163 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0163 {
    input.user.active
    input.resource.public
}
allowed_0163 {
    data.policies.access.enabled
}

# Utility function for user info
