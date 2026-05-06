package governance.authentication.policy.allow.policy_0270

# Auto-generated policy 270
# Package: governance.authentication.policy.allow

# Metadata
metadata := {
    "policy_id": "0270",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0270 {
    input.action == "delete"
    input.user.role != "admin"
}
approved_0270 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0270 {
    data.policies.governance.enabled
}
allowed_0270 {
    input.user.active
    input.resource.public
}

# Utility function for user info
