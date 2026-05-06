package security.authentication.context.validate.helpers.policy_0081

# Auto-generated policy 81
# Package: security.authentication.context.validate.helpers

# Metadata
metadata := {
    "policy_id": "0081",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0081 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0081 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0081 {
    input.user.role == "admin"
}

# Utility function for user info
