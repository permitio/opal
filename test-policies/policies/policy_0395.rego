package risk.enforcement.resource.verify.policy_0395

# Auto-generated policy 395
# Package: risk.enforcement.resource.verify

# Metadata
metadata := {
    "policy_id": "0395",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0395 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0395 {
    data.policies.risk.enabled
}
allowed_0395 {
    input.user.active
    input.resource.public
}
default allowed_0395 = false

# Utility function for user info
