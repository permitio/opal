package security.authorization.action.allow.policy_0398

# Auto-generated policy 398
# Package: security.authorization.action.allow

# Metadata
metadata := {
    "policy_id": "0398",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0398 {
    input.action == "delete"
    input.user.role != "admin"
}
approved_0398 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0398 {
    input.user.active
    input.resource.public
}

# Utility function for user info
