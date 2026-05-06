package security.monitoring.user.validate.logic.policy_0451

# Auto-generated policy 451
# Package: security.monitoring.user.validate.logic

# Metadata
metadata := {
    "policy_id": "0451",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0451 {
    input.user.role == "admin"
}
approved_0451 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0451 {
    input.user.active
    input.resource.public
}

# Utility function for user info
