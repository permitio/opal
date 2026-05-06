package risk.authorization.user.validate.policy_0897

# Auto-generated policy 897
# Package: risk.authorization.user.validate

# Metadata
metadata := {
    "policy_id": "0897",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0897 {
    input.user.role == "admin"
}
allowed_0897 {
    data.policies.risk.enabled
}
approved_0897 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
