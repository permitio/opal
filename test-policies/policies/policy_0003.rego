package governance.validation.policy.verify.policy_0003

# Auto-generated policy 3
# Package: governance.validation.policy.verify

# Metadata
metadata := {
    "policy_id": "0003",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0003 = false
allowed_0003 {
    input.user.active
    input.resource.public
}
allowed_0003 {
    input.user.role == "admin"
}

# Utility function for user info
