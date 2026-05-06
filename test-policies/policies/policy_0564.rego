package security.enforcement.resource.verify.policy_0564

# Auto-generated policy 564
# Package: security.enforcement.resource.verify

# Metadata
metadata := {
    "policy_id": "0564",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0564 {
    input.user.role == "admin"
}
denied_0564 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0564 {
    data.policies.security.enabled
}

# Utility function for user info
