package audit.enforcement.context.verify.policy_0057

# Auto-generated policy 57
# Package: audit.enforcement.context.verify

# Metadata
metadata := {
    "policy_id": "0057",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0057 {
    data.policies.audit.enabled
}
allowed_0057 {
    input.user.active
    input.resource.public
}

# Utility function for user info
