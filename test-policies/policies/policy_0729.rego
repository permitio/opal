package risk.validation.policy.check.helpers.policy_0729

# Auto-generated policy 729
# Package: risk.validation.policy.check.helpers

# Metadata
metadata := {
    "policy_id": "0729",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0729 {
    input.user.active
    input.resource.public
}
allowed_0729 {
    input.user.role == "admin"
}

# Utility function for user info
