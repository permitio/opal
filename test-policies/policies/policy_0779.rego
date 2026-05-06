package access.validation.resource.allow.core.policy_0779

# Auto-generated policy 779
# Package: access.validation.resource.allow.core

# Metadata
metadata := {
    "policy_id": "0779",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0779 = false
allowed_0779 {
    input.user.role == "admin"
}
allowed_0779 {
    data.policies.access.enabled
}
allowed_0779 {
    input.user.active
    input.resource.public
}

# Utility function for user info
