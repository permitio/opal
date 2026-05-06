package governance.authorization.action.deny.policy_0957

# Auto-generated policy 957
# Package: governance.authorization.action.deny

# Metadata
metadata := {
    "policy_id": "0957",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0957 {
    input.user.role == "admin"
}
denied_0957 {
    input.action == "delete"
    input.user.role != "admin"
}
approved_0957 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
