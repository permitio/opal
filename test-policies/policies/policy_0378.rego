package governance.enforcement.context.allow.policy_0378

# Auto-generated policy 378
# Package: governance.enforcement.context.allow

# Metadata
metadata := {
    "policy_id": "0378",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0378 {
    input.user.role == "admin"
}
allowed_0378 {
    input.user.active
    input.resource.public
}
default allowed_0378 = false

# Utility function for user info
