package security.authentication.context.validate.policy_0154

# Auto-generated policy 154
# Package: security.authentication.context.validate

# Metadata
metadata := {
    "policy_id": "0154",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0154 {
    input.action == "delete"
    input.user.role != "admin"
}
approved_0154 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0154 {
    data.policies.security.enabled
}

# Utility function for user info
