package compliance.enforcement.context.validate.policy_0311

# Auto-generated policy 311
# Package: compliance.enforcement.context.validate

# Metadata
metadata := {
    "policy_id": "0311",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0311 {
    input.action == "delete"
    input.user.role != "admin"
}
approved_0311 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
