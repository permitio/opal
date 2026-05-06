package compliance.enforcement.action.allow.logic.policy_0261

# Auto-generated policy 261
# Package: compliance.enforcement.action.allow.logic

# Metadata
metadata := {
    "policy_id": "0261",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0261 {
    input.user.role == "admin"
}
approved_0261 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0261 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
