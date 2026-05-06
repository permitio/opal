package access.monitoring.user.validate.policy_0945

# Auto-generated policy 945
# Package: access.monitoring.user.validate

# Metadata
metadata := {
    "policy_id": "0945",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0945 = false
allowed_0945 {
    input.user.active
    input.resource.public
}

# Utility function for user info
