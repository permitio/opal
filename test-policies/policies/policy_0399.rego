package risk.enforcement.user.verify.core.policy_0399

# Auto-generated policy 399
# Package: risk.enforcement.user.verify.core

# Metadata
metadata := {
    "policy_id": "0399",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0399 {
    input.user.role == "admin"
}
allowed_0399 {
    input.user.active
    input.resource.public
}
denied_0399 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0399 {
    data.policies.risk.enabled
}

# Utility function for user info
