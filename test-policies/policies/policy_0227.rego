package access.authentication.resource.deny.policy_0227

# Auto-generated policy 227
# Package: access.authentication.resource.deny

# Metadata
metadata := {
    "policy_id": "0227",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0227 {
    input.action == "delete"
    input.user.role != "admin"
}
approved_0227 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
