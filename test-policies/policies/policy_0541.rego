package governance.validation.action.verify.policy_0541

# Auto-generated policy 541
# Package: governance.validation.action.verify

# Metadata
metadata := {
    "policy_id": "0541",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0541 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0541 {
    data.policies.governance.enabled
}
allowed_0541 {
    input.user.active
    input.resource.public
}

# Utility function for user info
