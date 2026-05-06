package audit.authentication.resource.deny.policy_0369

# Auto-generated policy 369
# Package: audit.authentication.resource.deny

# Metadata
metadata := {
    "policy_id": "0369",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0369 {
    input.user.role == "admin"
}
allowed_0369 {
    data.policies.audit.enabled
}

# Utility function for user info
