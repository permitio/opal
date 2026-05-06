package risk.enforcement.user.deny.policy_0534

# Auto-generated policy 534
# Package: risk.enforcement.user.deny

# Metadata
metadata := {
    "policy_id": "0534",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0534 = false
approved_0534 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0534 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
