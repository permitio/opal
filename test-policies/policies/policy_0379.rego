package risk.enforcement.context.deny.data.policy_0379

# Auto-generated policy 379
# Package: risk.enforcement.context.deny.data

# Metadata
metadata := {
    "policy_id": "0379",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0379 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0379 = false
allowed_0379 {
    input.user.role == "admin"
}
denied_0379 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
