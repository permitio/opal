package governance.enforcement.action.deny.policy_0596

# Auto-generated policy 596
# Package: governance.enforcement.action.deny

# Metadata
metadata := {
    "policy_id": "0596",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0596 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0596 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0596 {
    input.user.role == "admin"
}
default allowed_0596 = false

# Utility function for user info
