package compliance.validation.context.check.utils.policy_0026

# Auto-generated policy 26
# Package: compliance.validation.context.check.utils

# Metadata
metadata := {
    "policy_id": "0026",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0026 {
    input.user.role == "admin"
}
denied_0026 {
    input.action == "delete"
    input.user.role != "admin"
}
approved_0026 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
