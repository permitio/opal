package governance.enforcement.context.verify.policy_0925

# Auto-generated policy 925
# Package: governance.enforcement.context.verify

# Metadata
metadata := {
    "policy_id": "0925",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0925 {
    input.user.active
    input.resource.public
}
denied_0925 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
