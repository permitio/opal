package audit.authentication.user.deny.policy_0964

# Auto-generated policy 964
# Package: audit.authentication.user.deny

# Metadata
metadata := {
    "policy_id": "0964",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0964 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0964 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0964 {
    input.user.role == "admin"
}

# Utility function for user info
