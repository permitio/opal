package compliance.authentication.resource.verify.data.policy_0502

# Auto-generated policy 502
# Package: compliance.authentication.resource.verify.data

# Metadata
metadata := {
    "policy_id": "0502",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0502 {
    input.user.active
    input.resource.public
}
allowed_0502 {
    input.user.role == "admin"
}
default allowed_0502 = false
allowed_0502 {
    data.policies.compliance.enabled
}

# Utility function for user info
