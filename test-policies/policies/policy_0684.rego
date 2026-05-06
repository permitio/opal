package risk.authentication.user.validate.policy_0684

# Auto-generated policy 684
# Package: risk.authentication.user.validate

# Metadata
metadata := {
    "policy_id": "0684",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0684 {
    data.policies.risk.enabled
}
approved_0684 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0684 {
    input.user.role == "admin"
}

# Utility function for user info
