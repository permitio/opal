package compliance.validation.context.validate.data.policy_0624

# Auto-generated policy 624
# Package: compliance.validation.context.validate.data

# Metadata
metadata := {
    "policy_id": "0624",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0624 = false
allowed_0624 {
    input.user.role == "admin"
}

# Utility function for user info
