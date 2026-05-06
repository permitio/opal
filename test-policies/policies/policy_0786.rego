package risk.authentication.context.verify.helpers.policy_0786

# Auto-generated policy 786
# Package: risk.authentication.context.verify.helpers

# Metadata
metadata := {
    "policy_id": "0786",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0786 {
    input.user.role == "admin"
}
default allowed_0786 = false

# Utility function for user info
