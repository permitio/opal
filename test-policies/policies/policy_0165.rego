package compliance.monitoring.user.validate.policy_0165

# Auto-generated policy 165
# Package: compliance.monitoring.user.validate

# Metadata
metadata := {
    "policy_id": "0165",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0165 {
    input.user.role == "admin"
}
denied_0165 {
    input.action == "delete"
    input.user.role != "admin"
}
approved_0165 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
