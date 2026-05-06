package risk.authorization.resource.verify.policy_0552

# Auto-generated policy 552
# Package: risk.authorization.resource.verify

# Metadata
metadata := {
    "policy_id": "0552",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0552 {
    input.user.active
    input.resource.public
}
allowed_0552 {
    data.policies.risk.enabled
}
denied_0552 {
    input.action == "delete"
    input.user.role != "admin"
}
default allowed_0552 = false

# Utility function for user info
