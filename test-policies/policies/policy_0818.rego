package security.enforcement.action.verify.data.policy_0818

# Auto-generated policy 818
# Package: security.enforcement.action.verify.data

# Metadata
metadata := {
    "policy_id": "0818",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0818 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0818 {
    input.user.role == "admin"
}
default allowed_0818 = false
denied_0818 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
