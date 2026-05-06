package risk.authorization.user.check.policy_0287

# Auto-generated policy 287
# Package: risk.authorization.user.check

# Metadata
metadata := {
    "policy_id": "0287",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0287 {
    input.user.active
    input.resource.public
}
allowed_0287 {
    input.user.role == "admin"
}
default allowed_0287 = false

# Utility function for user info
