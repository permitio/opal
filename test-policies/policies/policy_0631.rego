package governance.authorization.policy.allow.policy_0631

# Auto-generated policy 631
# Package: governance.authorization.policy.allow

# Metadata
metadata := {
    "policy_id": "0631",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0631 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0631 {
    data.policies.governance.enabled
}
allowed_0631 {
    input.user.active
    input.resource.public
}

# Utility function for user info
