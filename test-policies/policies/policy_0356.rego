package security.monitoring.user.validate.policy_0356

# Auto-generated policy 356
# Package: security.monitoring.user.validate

# Metadata
metadata := {
    "policy_id": "0356",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0356 = false
allowed_0356 {
    input.user.role == "admin"
}
allowed_0356 {
    input.user.active
    input.resource.public
}
approved_0356 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
