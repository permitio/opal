package security.enforcement.policy.verify.policy_0362

# Auto-generated policy 362
# Package: security.enforcement.policy.verify

# Metadata
metadata := {
    "policy_id": "0362",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0362 {
    input.user.active
    input.resource.public
}
denied_0362 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
