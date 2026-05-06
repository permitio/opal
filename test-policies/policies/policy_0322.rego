package security.authorization.action.verify.data.policy_0322

# Auto-generated policy 322
# Package: security.authorization.action.verify.data

# Metadata
metadata := {
    "policy_id": "0322",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0322 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0322 {
    data.policies.security.enabled
}
approved_0322 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0322 = false

# Utility function for user info
