package risk.authorization.context.validate.core.policy_0992

# Auto-generated policy 992
# Package: risk.authorization.context.validate.core

# Metadata
metadata := {
    "policy_id": "0992",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0992 {
    data.policies.risk.enabled
}
allowed_0992 {
    input.user.role == "admin"
}
approved_0992 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
