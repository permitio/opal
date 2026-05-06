package access.authentication.action.verify.policy_0012

# Auto-generated policy 12
# Package: access.authentication.action.verify

# Metadata
metadata := {
    "policy_id": "0012",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0012 {
    input.user.role == "admin"
}
approved_0012 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0012 {
    input.user.active
    input.resource.public
}
denied_0012 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
