package risk.authentication.resource.deny.policy_0908

# Auto-generated policy 908
# Package: risk.authentication.resource.deny

# Metadata
metadata := {
    "policy_id": "0908",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0908 {
    input.user.active
    input.resource.public
}
allowed_0908 {
    input.user.role == "admin"
}

# Utility function for user info
