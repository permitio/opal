package risk.validation.action.validate.utils.policy_0089

# Auto-generated policy 89
# Package: risk.validation.action.validate.utils

# Metadata
metadata := {
    "policy_id": "0089",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0089 {
    input.user.role == "admin"
}
allowed_0089 {
    input.user.active
    input.resource.public
}
approved_0089 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
