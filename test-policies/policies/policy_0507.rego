package risk.authorization.action.verify.policy_0507

# Auto-generated policy 507
# Package: risk.authorization.action.verify

# Metadata
metadata := {
    "policy_id": "0507",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0507 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0507 {
    input.user.role == "admin"
}
allowed_0507 {
    input.user.active
    input.resource.public
}

# Utility function for user info
