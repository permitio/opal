package governance.authorization.context.verify.policy_0603

# Auto-generated policy 603
# Package: governance.authorization.context.verify

# Metadata
metadata := {
    "policy_id": "0603",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0603 {
    input.user.active
    input.resource.public
}
default allowed_0603 = false

# Utility function for user info
