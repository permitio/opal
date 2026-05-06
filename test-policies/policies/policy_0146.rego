package access.validation.user.validate.policy_0146

# Auto-generated policy 146
# Package: access.validation.user.validate

# Metadata
metadata := {
    "policy_id": "0146",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0146 {
    data.policies.access.enabled
}
approved_0146 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0146 {
    input.user.role == "admin"
}

# Utility function for user info
