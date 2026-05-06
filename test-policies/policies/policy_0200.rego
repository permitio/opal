package governance.authorization.action.check.data.policy_0200

# Auto-generated policy 200
# Package: governance.authorization.action.check.data

# Metadata
metadata := {
    "policy_id": "0200",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0200 {
    input.user.role == "admin"
}
allowed_0200 {
    input.user.active
    input.resource.public
}
approved_0200 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0200 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
