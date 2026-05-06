package access.authentication.resource.deny.policy_0101

# Auto-generated policy 101
# Package: access.authentication.resource.deny

# Metadata
metadata := {
    "policy_id": "0101",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0101 {
    input.action == "delete"
    input.user.role != "admin"
}
approved_0101 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
