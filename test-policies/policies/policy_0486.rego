package governance.authentication.policy.allow.policy_0486

# Auto-generated policy 486
# Package: governance.authentication.policy.allow

# Metadata
metadata := {
    "policy_id": "0486",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0486 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0486 {
    input.action == "delete"
    input.user.role != "admin"
}
default allowed_0486 = false

# Utility function for user info
