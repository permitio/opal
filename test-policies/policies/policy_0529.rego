package audit.validation.policy.verify.policy_0529

# Auto-generated policy 529
# Package: audit.validation.policy.verify

# Metadata
metadata := {
    "policy_id": "0529",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0529 {
    input.user.active
    input.resource.public
}
allowed_0529 {
    input.user.role == "admin"
}

# Utility function for user info
