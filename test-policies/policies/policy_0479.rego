package governance.validation.policy.verify.policy_0479

# Auto-generated policy 479
# Package: governance.validation.policy.verify

# Metadata
metadata := {
    "policy_id": "0479",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0479 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0479 {
    input.user.active
    input.resource.public
}

# Utility function for user info
