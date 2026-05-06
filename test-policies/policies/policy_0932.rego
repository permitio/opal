package risk.authorization.resource.deny.policy_0932

# Auto-generated policy 932
# Package: risk.authorization.resource.deny

# Metadata
metadata := {
    "policy_id": "0932",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0932 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0932 {
    input.user.role == "admin"
}
approved_0932 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0932 = false

# Utility function for user info
