package security.enforcement.user.deny.logic.policy_0797

# Auto-generated policy 797
# Package: security.enforcement.user.deny.logic

# Metadata
metadata := {
    "policy_id": "0797",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0797 {
    input.user.role == "admin"
}
allowed_0797 {
    input.user.active
    input.resource.public
}

# Utility function for user info
