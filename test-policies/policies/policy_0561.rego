package risk.enforcement.policy.verify.policy_0561

# Auto-generated policy 561
# Package: risk.enforcement.policy.verify

# Metadata
metadata := {
    "policy_id": "0561",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0561 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0561 {
    input.user.active
    input.resource.public
}

# Utility function for user info
