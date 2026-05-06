package risk.enforcement.user.deny.policy_0157

# Auto-generated policy 157
# Package: risk.enforcement.user.deny

# Metadata
metadata := {
    "policy_id": "0157",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0157 {
    input.user.active
    input.resource.public
}
default allowed_0157 = false

# Utility function for user info
