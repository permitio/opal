package access.authorization.action.check.policy_0671

# Auto-generated policy 671
# Package: access.authorization.action.check

# Metadata
metadata := {
    "policy_id": "0671",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0671 = false
allowed_0671 {
    input.user.active
    input.resource.public
}
approved_0671 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0671 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
