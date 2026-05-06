package governance.validation.user.validate.data.policy_0348

# Auto-generated policy 348
# Package: governance.validation.user.validate.data

# Metadata
metadata := {
    "policy_id": "0348",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0348 {
    input.user.active
    input.resource.public
}
allowed_0348 {
    input.user.role == "admin"
}

# Utility function for user info
