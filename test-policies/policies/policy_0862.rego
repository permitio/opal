package governance.validation.context.validate.policy_0862

# Auto-generated policy 862
# Package: governance.validation.context.validate

# Metadata
metadata := {
    "policy_id": "0862",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0862 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0862 {
    input.user.role == "admin"
}
allowed_0862 {
    input.user.active
    input.resource.public
}

# Utility function for user info
