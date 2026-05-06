package governance.authentication.user.verify.policy_0127

# Auto-generated policy 127
# Package: governance.authentication.user.verify

# Metadata
metadata := {
    "policy_id": "0127",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0127 {
    data.policies.governance.enabled
}
approved_0127 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0127 = false
denied_0127 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
