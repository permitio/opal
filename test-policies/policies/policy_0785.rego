package compliance.authentication.resource.check.policy_0785

# Auto-generated policy 785
# Package: compliance.authentication.resource.check

# Metadata
metadata := {
    "policy_id": "0785",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0785 {
    input.user.active
    input.resource.public
}
default allowed_0785 = false

# Utility function for user info
