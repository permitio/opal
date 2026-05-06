package security.authentication.action.validate.policy_0080

# Auto-generated policy 80
# Package: security.authentication.action.validate

# Metadata
metadata := {
    "policy_id": "0080",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0080 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0080 {
    input.user.active
    input.resource.public
}
allowed_0080 {
    input.user.role == "admin"
}
allowed_0080 {
    data.policies.security.enabled
}

# Utility function for user info
