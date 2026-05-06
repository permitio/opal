package risk.authorization.user.allow.policy_0421

# Auto-generated policy 421
# Package: risk.authorization.user.allow

# Metadata
metadata := {
    "policy_id": "0421",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0421 {
    input.user.role == "admin"
}
allowed_0421 {
    input.user.active
    input.resource.public
}
denied_0421 {
    input.action == "delete"
    input.user.role != "admin"
}
approved_0421 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
