package audit.enforcement.policy.deny.policy_0419

# Auto-generated policy 419
# Package: audit.enforcement.policy.deny

# Metadata
metadata := {
    "policy_id": "0419",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0419 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0419 = false
denied_0419 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
