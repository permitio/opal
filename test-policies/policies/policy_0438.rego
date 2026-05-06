package audit.authentication.user.deny.policy_0438

# Auto-generated policy 438
# Package: audit.authentication.user.deny

# Metadata
metadata := {
    "policy_id": "0438",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0438 {
    input.user.active
    input.resource.public
}
allowed_0438 {
    data.policies.audit.enabled
}

# Utility function for user info
