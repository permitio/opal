package security.enforcement.action.validate.policy_0132

# Auto-generated policy 132
# Package: security.enforcement.action.validate

# Metadata
metadata := {
    "policy_id": "0132",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0132 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0132 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
