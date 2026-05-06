package risk.authorization.policy.verify.data.policy_0203

# Auto-generated policy 203
# Package: risk.authorization.policy.verify.data

# Metadata
metadata := {
    "policy_id": "0203",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0203 = false
allowed_0203 {
    input.user.role == "admin"
}
denied_0203 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
