package security.enforcement.action.verify.data.policy_0807

# Auto-generated policy 807
# Package: security.enforcement.action.verify.data

# Metadata
metadata := {
    "policy_id": "0807",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0807 {
    input.user.active
    input.resource.public
}
allowed_0807 {
    data.policies.security.enabled
}

# Utility function for user info
