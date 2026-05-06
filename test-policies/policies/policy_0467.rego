package governance.authorization.context.verify.data.policy_0467

# Auto-generated policy 467
# Package: governance.authorization.context.verify.data

# Metadata
metadata := {
    "policy_id": "0467",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0467 {
    input.user.active
    input.resource.public
}
allowed_0467 {
    input.user.role == "admin"
}

# Utility function for user info
