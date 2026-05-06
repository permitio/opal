package governance.validation.user.check.policy_0878

# Auto-generated policy 878
# Package: governance.validation.user.check

# Metadata
metadata := {
    "policy_id": "0878",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0878 {
    input.user.role == "admin"
}
default allowed_0878 = false
allowed_0878 {
    input.user.active
    input.resource.public
}

# Utility function for user info
