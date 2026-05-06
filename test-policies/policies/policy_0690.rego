package compliance.authorization.policy.verify.policy_0690

# Auto-generated policy 690
# Package: compliance.authorization.policy.verify

# Metadata
metadata := {
    "policy_id": "0690",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0690 {
    input.user.active
    input.resource.public
}
default allowed_0690 = false
allowed_0690 {
    input.user.role == "admin"
}
denied_0690 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
