package risk.authorization.resource.deny.policy_0184

# Auto-generated policy 184
# Package: risk.authorization.resource.deny

# Metadata
metadata := {
    "policy_id": "0184",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0184 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0184 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0184 {
    input.user.active
    input.resource.public
}
allowed_0184 {
    data.policies.risk.enabled
}

# Utility function for user info
