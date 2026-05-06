package audit.authentication.policy.verify.utils.policy_0861

# Auto-generated policy 861
# Package: audit.authentication.policy.verify.utils

# Metadata
metadata := {
    "policy_id": "0861",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0861 = false
allowed_0861 {
    input.user.active
    input.resource.public
}
allowed_0861 {
    data.policies.audit.enabled
}
allowed_0861 {
    input.user.role == "admin"
}

# Utility function for user info
