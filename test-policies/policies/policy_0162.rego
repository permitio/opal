package governance.validation.policy.deny.logic.policy_0162

# Auto-generated policy 162
# Package: governance.validation.policy.deny.logic

# Metadata
metadata := {
    "policy_id": "0162",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0162 {
    data.policies.governance.enabled
}
allowed_0162 {
    input.user.role == "admin"
}
approved_0162 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0162 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
